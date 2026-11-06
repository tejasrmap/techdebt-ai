import os
import re
import hashlib
import ipaddress
import socket
import zipfile
import shutil
import tempfile
import logging
import uuid
from datetime import datetime
from threading import Lock
from urllib.parse import urlparse, urljoin, quote, quote_plus
from typing import Dict, Any, List, Optional, Tuple
import httpx
from sqlalchemy import func

from app.services.source_code_analyzer import SourceCodeAnalyzer
from app.services.parsers.dependency_parser import DependencyParser

logger = logging.getLogger(__name__)


class UnsafeRepositoryURLError(ValueError):
    """Raised when repository URL violates SSRF or security constraints."""
    pass


class ArchiveSecurityError(ValueError):
    """Raised when an uploaded repository archive violates safety limits or path traversal rules."""
    pass


class RepositorySyncError(RuntimeError):
    """Raised when remote repository metadata retrieval or archive download fails."""
    pass


# Explicit repository sync state machine (Phase 1.4)
SYNC_STATE_QUEUED = "QUEUED"
SYNC_STATE_CLONING = "CLONING_OR_DOWNLOADING"
SYNC_STATE_ANALYSING = "ANALYSING"
SYNC_STATE_PERSISTING = "PERSISTING"
SYNC_STATE_COMPLETED = "COMPLETED"
SYNC_STATE_FAILED = "FAILED"
SYNC_STATE_CANCELLED = "CANCELLED"

VALID_SYNC_STATES = {
    SYNC_STATE_QUEUED,
    SYNC_STATE_CLONING,
    SYNC_STATE_ANALYSING,
    SYNC_STATE_PERSISTING,
    SYNC_STATE_COMPLETED,
    SYNC_STATE_FAILED,
    SYNC_STATE_CANCELLED,
}

_LEGACY_TO_SYNC_STATE = {
    "pending": SYNC_STATE_QUEUED,
    "queued": SYNC_STATE_QUEUED,
    "cloning": SYNC_STATE_CLONING,
    "cloning_or_downloading": SYNC_STATE_CLONING,
    "downloading": SYNC_STATE_CLONING,
    "parsing": SYNC_STATE_ANALYSING,
    "analyzing": SYNC_STATE_ANALYSING,
    "analysing": SYNC_STATE_ANALYSING,
    "persisting": SYNC_STATE_PERSISTING,
    "completed": SYNC_STATE_COMPLETED,
    "failed": SYNC_STATE_FAILED,
    "cancelled": SYNC_STATE_CANCELLED,
}

_SYNC_STATE_TO_LEGACY = {
    SYNC_STATE_QUEUED: "pending",
    SYNC_STATE_CLONING: "cloning",
    SYNC_STATE_ANALYSING: "analyzing",
    SYNC_STATE_PERSISTING: "persisting",
    SYNC_STATE_COMPLETED: "completed",
    SYNC_STATE_FAILED: "failed",
    SYNC_STATE_CANCELLED: "cancelled",
}


FRAMEWORK_DEPENDENCY_SIGNATURES = {
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "starlette": "Starlette",
    "tornado": "Tornado",
    "react": "React",
    "next": "Next.js",
    "vue": "Vue.js",
    "@angular/core": "Angular",
    "svelte": "Svelte",
    "express": "Express",
    "@nestjs/core": "NestJS",
    "fastify": "Fastify",
    "spring-boot-starter": "Spring Boot",
    "spring-boot-starter-web": "Spring Boot",
    "laravel/framework": "Laravel",
    "symfony/framework-bundle": "Symfony",
    "github.com/gin-gonic/gin": "Gin",
    "github.com/gofiber/fiber": "Fiber",
    "github.com/labstack/echo": "Echo",
    "microsoft.aspnetcore": "ASP.NET Core",
    "rails": "Ruby on Rails",
    "actix-web": "Actix Web",
    "axum": "Axum",
}


class RepositoryIngestionService:
    """
    Commercial-grade repository intelligence & ingestion pipeline (v3.1.0).
    Safely connects, downloads, inspects, and persists repository snapshots from
    GitHub, GitLab, Bitbucket, or manual ZIP uploads with strict SSRF, redirect,
    symlink, decompression-bomb, and path-traversal protections.
    """

    ANALYZER_VERSION = "v3.1.0"
    MAX_REPO_SIZE_BYTES = 100 * 1024 * 1024   # 100 MB archive limit
    MAX_EXTRACTED_BYTES = 200 * 1024 * 1024   # 200 MB uncompressed ceiling
    MAX_FILE_COUNT = 5000
    MAX_SINGLE_FILE_BYTES = 5 * 1024 * 1024    # 5 MB per source file
    TIMEOUT_SECONDS = 60
    MAX_REDIRECTS = 5
    STREAM_CHUNK_BYTES = 64 * 1024

    BLOCKED_CIDRS = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("100.64.0.0/10"),     # CGNAT / shared address space
        ipaddress.ip_network("198.18.0.0/15"),     # Benchmarking space
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("224.0.0.0/4"),       # Multicast
        ipaddress.ip_network("240.0.0.0/4"),       # Reserved
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("::/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
        ipaddress.ip_network("ff00::/8"),
    ]

    BLOCKED_HOSTNAMES = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "[::1]",
        "metadata.google.internal",
        "metadata",
        "169.254.169.254",
        "100.100.100.200",
        "instance-data",
    }

    KNOWN_PUBLIC_PROVIDER_HOSTS = {
        "github.com",
        "api.github.com",
        "codeload.github.com",
        "gitlab.com",
        "bitbucket.org",
        "api.bitbucket.org",
    }

    MANIFEST_FILENAMES = {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "pyproject.toml",
        "poetry.lock",
        "pipfile",
        "pipfile.lock",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "cargo.toml",
        "cargo.lock",
        "go.mod",
        "go.sum",
        "composer.json",
        "composer.lock",
        "gemfile",
        "gemfile.lock",
        "packages.config",
    }

    @classmethod
    def _validate_ip_obj(cls, ip_obj: ipaddress._BaseAddress, hostname: str) -> None:
        """Check IPv4, IPv6, and IPv4-mapped IPv6 addresses against private/internal ranges."""
        candidates = [ip_obj]
        if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
            candidates.append(ip_obj.ipv4_mapped)

        for candidate in candidates:
            for cidr in cls.BLOCKED_CIDRS:
                if candidate in cidr:
                    raise UnsafeRepositoryURLError(
                        f"SSRF security violation: Host '{hostname}' resolves to private/internal IP {candidate}."
                    )
            if (
                candidate.is_loopback
                or candidate.is_private
                or candidate.is_link_local
                or candidate.is_multicast
                or candidate.is_reserved
                or candidate.is_unspecified
            ):
                raise UnsafeRepositoryURLError(
                    f"SSRF security violation: Host '{hostname}' resolves to non-public IP {candidate}."
                )

    @classmethod
    def validate_repository_url(cls, url: str) -> str:
        """
        Validates URL against SSRF, dangerous protocols, embedded credentials,
        IPv4-mapped IPv6 bypasses, and private/internal IP spaces.
        """
        if not url or not isinstance(url, str):
            raise UnsafeRepositoryURLError("Repository URL cannot be empty.")

        url = url.strip()
        parsed = urlparse(url)

        if parsed.scheme.lower() not in ("http", "https"):
            raise UnsafeRepositoryURLError(
                f"Disallowed URL scheme '{parsed.scheme}'. Only HTTPS and HTTP are supported."
            )

        if parsed.username or parsed.password:
            raise UnsafeRepositoryURLError(
                "Embedded credentials in repository URLs are forbidden; pass tokens via encrypted authorization."
            )

        hostname = (parsed.hostname or "").lower().strip(".")
        if not hostname:
            raise UnsafeRepositoryURLError(f"Invalid repository URL '{url}': hostname is missing.")

        if (
            hostname in cls.BLOCKED_HOSTNAMES
            or hostname.endswith(".internal")
            or hostname.endswith(".local")
            or hostname.endswith(".localhost")
            or hostname.endswith(".arpa")
        ):
            raise UnsafeRepositoryURLError(
                f"SSRF violation: Access to private/internal host '{hostname}' is strictly forbidden."
            )

        # Direct IP literal check (including IPv4-mapped IPv6 like ::ffff:127.0.0.1)
        try:
            literal_ip = ipaddress.ip_address(hostname)
            cls._validate_ip_obj(literal_ip, hostname)
            return url
        except ValueError:
            pass

        # Resolve hostname and inspect all returned A/AAAA records
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            if not addr_info:
                raise UnsafeRepositoryURLError(f"Unable to resolve repository host '{hostname}'.")
            for _, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0].split("%")[0]
                ip_obj = ipaddress.ip_address(ip_str)
                cls._validate_ip_obj(ip_obj, hostname)
        except socket.gaierror as e:
            # Fail closed for arbitrary/custom hosts to prevent DNS rebinding / blind probing;
            # allow static URL syntax check for canonical public VCS hosts when running offline tests.
            if hostname not in cls.KNOWN_PUBLIC_PROVIDER_HOSTS:
                raise UnsafeRepositoryURLError(
                    f"DNS resolution failed for untrusted repository host '{hostname}': {e}"
                )

        return url

    @classmethod
    def validate_repo_url(cls, url: str) -> Tuple[bool, str]:
        """Convenience validation returning (is_safe, reason_or_url)."""
        try:
            cleaned = cls.validate_repository_url(url)
            return True, cleaned
        except Exception as e:
            return False, str(e)

    @classmethod
    def _is_manifest_file(cls, filename: str) -> bool:
        f_lower = filename.lower()
        if f_lower in cls.MANIFEST_FILENAMES:
            return True
        if f_lower.endswith(".csproj"):
            return True
        if f_lower.startswith("requirements") and f_lower.endswith(".txt"):
            return True
        return False

    @classmethod
    def process_zip_upload(cls, zip_bytes: bytes, project_id: str) -> Dict[str, Any]:
        """Processes an uploaded ZIP repository archive, validates security, and extracts it to storage."""
        safe_project_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(project_id))
        storage_dir = os.path.abspath(os.path.join("storage", "repos", safe_project_id))
        if os.path.exists(storage_dir):
            shutil.rmtree(storage_dir, ignore_errors=True)
        os.makedirs(storage_dir, exist_ok=True)

        try:
            stats = cls.extract_zip_repository_safely(zip_bytes, storage_dir)
        except Exception:
            shutil.rmtree(storage_dir, ignore_errors=True)
            raise

        languages: Dict[str, int] = {}
        manifest_files: List[str] = []
        name_map = {
            "python": "Python",
            "javascript": "JavaScript",
            "typescript": "TypeScript",
            "csharp": "C#",
            "cpp": "C++",
            "c": "C",
            "go": "Go",
            "java": "Java",
            "php": "PHP",
        }

        for root, dirs, files in os.walk(storage_dir):
            dirs[:] = [d for d in dirs if d not in SourceCodeAnalyzer.IGNORE_DIRS and not d.startswith(".")]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in SourceCodeAnalyzer.SUPPORTED_EXTENSIONS:
                    raw_lang = SourceCodeAnalyzer.SUPPORTED_EXTENSIONS[ext]
                    lang = name_map.get(raw_lang, raw_lang.title())
                    languages[lang] = languages.get(lang, 0) + 1
                if cls._is_manifest_file(f):
                    manifest_files.append(os.path.join(root, f))

        return {
            "file_count": stats["file_count"],
            "excluded_files": stats.get("excluded_files", 0),
            "total_size_bytes": stats["uncompressed_bytes"],
            "extracted_path": storage_dir,
            "languages": languages,
            "manifest_files": manifest_files,
        }

    @classmethod
    def extract_zip_repository_safely(cls, zip_file_bytes: bytes, target_dir: str) -> Dict[str, Any]:
        """
        Extracts ZIP repository archive with strict Zip-Slip, symlink, encrypted-entry,
        and streamed byte-counted decompression-bomb protections.
        """
        if not isinstance(zip_file_bytes, (bytes, bytearray)) or len(zip_file_bytes) == 0:
            raise ArchiveSecurityError("Uploaded archive is empty or unreadable.")

        if len(zip_file_bytes) > cls.MAX_REPO_SIZE_BYTES:
            raise ArchiveSecurityError(
                f"Repository archive exceeds maximum allowed size ({len(zip_file_bytes)} > {cls.MAX_REPO_SIZE_BYTES} bytes)."
            )

        target_dir_abs = os.path.abspath(target_dir)
        os.makedirs(target_dir_abs, exist_ok=True)
        total_extracted_size = 0
        extracted_file_count = 0
        excluded_file_count = 0

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
            tmp_zip_path = tmp_zip.name
            tmp_zip.write(zip_file_bytes)

        try:
            if not zipfile.is_zipfile(tmp_zip_path):
                raise ArchiveSecurityError("Uploaded file is not a valid ZIP archive or contains corrupted headers.")

            with zipfile.ZipFile(tmp_zip_path, "r") as zf:
                infolist = zf.infolist()
                if len(infolist) > cls.MAX_FILE_COUNT:
                    raise ArchiveSecurityError(
                        f"Archive contains too many entries ({len(infolist)} > {cls.MAX_FILE_COUNT} files limit)."
                    )

                for member in infolist:
                    filename = member.filename

                    # 1. Reject dangerous characters, null bytes, drive prefixes, and path traversal
                    if "\0" in filename:
                        raise ArchiveSecurityError(f"Null byte detected in archive filename: '{filename}'")

                    normalized_parts = filename.replace("\\", "/").split("/")
                    if (
                        filename.startswith(("/", "\\"))
                        or re.match(r"^[a-zA-Z]:", filename)
                        or ".." in normalized_parts
                    ):
                        raise ArchiveSecurityError(
                            f"Zip-Slip path traversal attempt detected in filename: '{filename}'"
                        )

                    # 2. Reject password-encrypted archive entries
                    if member.flag_bits & 0x1:
                        raise ArchiveSecurityError(
                            f"Encrypted ZIP entries are not permitted: '{filename}'"
                        )

                    # 3. Reject Unix symlinks and special device/FIFO entries
                    unix_mode = (member.external_attr >> 16) & 0o170000
                    if unix_mode == 0o120000:
                        raise ArchiveSecurityError(
                            f"Symbolic links inside repository archives are forbidden: '{filename}'"
                        )
                    if unix_mode not in (0, 0o100000, 0o040000):
                        raise ArchiveSecurityError(
                            f"Unsupported special file mode in archive entry: '{filename}'"
                        )

                    # 4. Pre-check declared size for obvious decompression bombs before streaming
                    if member.file_size > cls.MAX_EXTRACTED_BYTES:
                        raise ArchiveSecurityError(
                            "Archive expansion ratio exceeded safe threshold (decompression bomb detected)."
                        )

                    # 5. Path canonicalization check
                    dest_path = os.path.abspath(os.path.join(target_dir_abs, filename))
                    if not dest_path.startswith(target_dir_abs + os.sep) and dest_path != target_dir_abs:
                        raise ArchiveSecurityError(
                            f"Path traversal detected: '{dest_path}' escapes '{target_dir_abs}'"
                        )

                    if member.is_dir():
                        os.makedirs(dest_path, exist_ok=True)
                        continue

                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    member_bytes = 0
                    oversized_regular_file = False

                    with zf.open(member, "r") as src_f, open(dest_path, "wb") as dst_f:
                        while True:
                            chunk = src_f.read(cls.STREAM_CHUNK_BYTES)
                            if not chunk:
                                break
                            member_bytes += len(chunk)
                            total_extracted_size += len(chunk)

                            if total_extracted_size > cls.MAX_EXTRACTED_BYTES:
                                raise ArchiveSecurityError(
                                    "Archive expansion ratio exceeded safe threshold (decompression bomb detected)."
                                )

                            if member_bytes > cls.MAX_SINGLE_FILE_BYTES:
                                comp_size = max(1, member.compress_size)
                                if (member_bytes / comp_size) > 50.0:
                                    raise ArchiveSecurityError(
                                        f"Decompression bomb suspected in entry '{filename}' (compression ratio > 50x)."
                                    )
                                oversized_regular_file = True
                                break

                            dst_f.write(chunk)

                    if oversized_regular_file:
                        try:
                            os.remove(dest_path)
                        except OSError:
                            pass
                        excluded_file_count += 1
                    else:
                        extracted_file_count += 1

            return {
                "file_count": extracted_file_count,
                "excluded_files": excluded_file_count,
                "uncompressed_bytes": total_extracted_size,
            }
        except zipfile.BadZipFile as e:
            raise ArchiveSecurityError(f"Corrupted or invalid ZIP archive: {str(e)}")
        finally:
            if os.path.exists(tmp_zip_path):
                try:
                    os.remove(tmp_zip_path)
                except OSError:
                    pass

    @classmethod
    async def _safe_http_get(
        cls,
        client: httpx.AsyncClient,
        url: str,
        headers: Dict[str, str],
        max_redirects: Optional[int] = None,
    ) -> httpx.Response:
        """
        Executes an HTTP GET with SSRF validation on every redirect hop and
        automatic Authorization header stripping on cross-origin redirects.
        """
        redirect_limit = cls.MAX_REDIRECTS if max_redirects is None else max_redirects
        current_url = cls.validate_repository_url(url)
        current_headers = dict(headers)

        for hop in range(redirect_limit + 1):
            res = await client.get(current_url, headers=current_headers)
            if res.status_code in (301, 302, 303, 307, 308):
                if hop >= redirect_limit:
                    raise UnsafeRepositoryURLError(
                        f"Exceeded maximum allowed HTTP redirects ({redirect_limit}) while fetching repository."
                    )
                location = res.headers.get("location")
                if not location:
                    raise RepositorySyncError(
                        f"Redirect HTTP {res.status_code} missing Location header from '{current_url}'."
                    )
                next_url = urljoin(current_url, location)
                next_url = cls.validate_repository_url(next_url)

                orig_host = (urlparse(current_url).hostname or "").lower()
                next_host = (urlparse(next_url).hostname or "").lower()
                if orig_host != next_host:
                    # Never forward provider tokens to external CDN/object-storage redirect hosts
                    current_headers.pop("Authorization", None)
                    current_headers.pop("PRIVATE-TOKEN", None)

                current_url = next_url
                continue
            return res

        raise UnsafeRepositoryURLError("Unexpected redirect loop termination.")

    async def ingest_repository(
        self,
        repo_url: Optional[str] = None,
        zip_bytes: Optional[bytes] = None,
        auth_token: Optional[str] = None,
        branch: str = "main",
        provider: str = "github",
        excluded_paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes end-to-end ingestion pipeline in an isolated temporary workspace:
        1. Validates source, SSRF boundaries, and authorization.
        2. Retrieves commit metadata + archive into isolated temp workspace.
        3. Identifies frameworks, languages, build configs, and ecosystem manifests.
        4. Parses dependency manifests and lockfiles across all ecosystems.
        5. Runs static SourceCodeAnalyzer.
        6. Returns complete analysis payload before temporary directory cleanup.
        """
        with tempfile.TemporaryDirectory(prefix="techdebt_ingest_") as temp_dir:
            extraction_stats: Dict[str, Any] = {"file_count": 0, "excluded_files": 0, "uncompressed_bytes": 0}

            if zip_bytes is not None:
                extraction_stats = self.extract_zip_repository_safely(zip_bytes, temp_dir)
                digest = hashlib.sha256(zip_bytes).hexdigest()[:36]
                commit_sha = f"zip:{digest}"
                commit_message = f"Manual ZIP archive upload ({extraction_stats['file_count']} files)"
                commit_author = "ZIP Upload"
                effective_provider = provider or "local_upload"
            elif repo_url:
                validated_url = self.validate_repository_url(repo_url)
                download_res = await self._download_remote_repository(
                    repo_url=validated_url,
                    auth_token=auth_token,
                    branch=branch,
                    target_dir=temp_dir,
                    provider=provider,
                )
                commit_sha = download_res["commit_sha"]
                commit_message = download_res["commit_message"]
                commit_author = download_res["commit_author"]
                extraction_stats = download_res.get("extraction_stats", extraction_stats)
                effective_provider = download_res.get("provider", provider)
            else:
                raise ValueError("Either repository URL or ZIP file bytes must be provided.")

            # Unpack nested root directory if archive had a single top-level wrapper folder
            analysis_root = self._resolve_effective_root(temp_dir)

            # Parse dependencies and lockfiles across all supported ecosystems
            dep_parser = DependencyParser()
            dependencies, parse_errors = self._discover_and_parse_dependencies_with_errors(
                analysis_root, dep_parser, excluded_paths=excluded_paths
            )

            # Discover languages, frameworks, and build systems (combining structure + dependencies)
            repo_profile = self._profile_repository_structure(
                analysis_root, dependencies=dependencies, excluded_paths=excluded_paths
            )

            # Run static source code analysis
            code_analyzer = SourceCodeAnalyzer(analysis_root)
            if hasattr(code_analyzer, "excluded_paths") or excluded_paths:
                code_analyzer.excluded_paths = excluded_paths or []
            code_analysis = code_analyzer.analyze_repository()

            files_analyzed = code_analysis.get("files_analyzed", 0)
            files_examined = max(files_analyzed, extraction_stats.get("file_count", 0))
            files_excluded = (
                extraction_stats.get("excluded_files", 0)
                + code_analysis.get("files_excluded", max(0, files_examined - files_analyzed))
            )

            return {
                "provider": effective_provider,
                "branch": branch,
                "analyzer_version": self.ANALYZER_VERSION,
                "commit_sha": commit_sha,
                "commit_message": commit_message,
                "commit_author": commit_author,
                "files_examined": files_examined,
                "files_analyzed": files_analyzed,
                "files_excluded": files_excluded,
                "uncompressed_bytes": extraction_stats.get("uncompressed_bytes", 0),
                "profile": repo_profile,
                "dependencies": dependencies,
                "code_analysis": code_analysis,
                "analysis_errors": parse_errors + code_analysis.get("parser_errors", []),
            }

    @staticmethod
    def _extract_sha_from_zip_bytes(zip_bytes: bytes) -> Optional[str]:
        """Attempt to infer git commit SHA from provider zipball top-level folder or comment."""
        try:
            with tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024) as spooled:
                spooled.write(zip_bytes)
                spooled.seek(0)
                with zipfile.ZipFile(spooled, "r") as zf:
                    if zf.comment:
                        comment_str = zf.comment.decode("utf-8", errors="ignore").strip()
                        if re.fullmatch(r"[0-9a-fA-F]{40}", comment_str):
                            return comment_str.lower()
                    names = zf.namelist()
                    if names:
                        top_folder = names[0].split("/")[0]
                        m = re.search(r"-([0-9a-fA-F]{7,40})$", top_folder)
                        if m:
                            return m.group(1).lower()
        except Exception:
            pass
        return None

    async def _download_remote_repository(
        self,
        repo_url: str,
        auth_token: Optional[str],
        branch: str,
        target_dir: str,
        provider: str = "github",
    ) -> Dict[str, Any]:
        """
        Retrieves authentic commit metadata and archive from GitHub, GitLab, Bitbucket,
        or verified HTTPS archive URLs. Raises RepositorySyncError on any HTTP/network failure
        so failed downloads NEVER masquerade as successful syncs.
        """
        parsed = urlparse(repo_url)
        host = (parsed.hostname or "").lower()
        provider_lower = (provider or "").lower()
        clean_path = parsed.path.strip("/")
        if clean_path.endswith(".git"):
            clean_path = clean_path[:-4]
        path_parts = [p for p in clean_path.split("/") if p]

        base_headers: Dict[str, str] = {
            "User-Agent": "TechDebtAI-Ingestion-Engine/3.1.0",
            "Accept": "application/json",
        }
        clean_token = auth_token.strip() if auth_token and auth_token.strip() else None

        commit_sha: Optional[str] = None
        commit_message: str = ""
        commit_author: str = ""
        detected_provider = provider_lower or "other"

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS, follow_redirects=False) as client:
                # 1. GitHub (github.com)
                if "github.com" in host or provider_lower == "github":
                    if len(path_parts) < 2:
                        raise RepositorySyncError(f"Invalid GitHub repository URL path: '{repo_url}'")
                    owner, repo = path_parts[0], path_parts[1]
                    detected_provider = "github"
                    gh_headers = {
                        **base_headers,
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    }
                    if clean_token:
                        gh_headers["Authorization"] = f"Bearer {clean_token}"

                    commit_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{quote(branch, safe='')}"
                    commit_res = await self._safe_http_get(client, commit_url, gh_headers)
                    if commit_res.status_code in (404, 422) and branch == "main":
                        repo_meta_res = await self._safe_http_get(
                            client, f"https://api.github.com/repos/{owner}/{repo}", gh_headers
                        )
                        if repo_meta_res.status_code == 200:
                            def_branch = (repo_meta_res.json().get("default_branch") or "").strip()
                            if def_branch and def_branch != branch:
                                branch = def_branch
                                commit_url = (
                                    f"https://api.github.com/repos/{owner}/{repo}/commits/{quote(branch, safe='')}"
                                )
                                commit_res = await self._safe_http_get(client, commit_url, gh_headers)
                    if commit_res.status_code == 200:
                        c_data = commit_res.json()
                        commit_sha = (c_data.get("sha") or "").strip()
                        commit_obj = c_data.get("commit") or {}
                        commit_message = (commit_obj.get("message") or f"GitHub branch '{branch}' sync").strip()
                        commit_author = (
                            (commit_obj.get("author") or {}).get("name")
                            or (c_data.get("author") or {}).get("login")
                            or "GitHub Author"
                        )
                    elif commit_res.status_code in (401, 403, 404):
                        raise RepositorySyncError(
                            f"GitHub commit lookup failed (HTTP {commit_res.status_code}) for {owner}/{repo}@{branch}. "
                            "Verify repository existence, branch name, and credentials."
                        )
                    else:
                        raise RepositorySyncError(
                            f"GitHub API error (HTTP {commit_res.status_code}) retrieving commit metadata."
                        )

                    ref_for_zip = commit_sha or branch
                    archive_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{quote(ref_for_zip, safe='')}"
                    dl_headers = {**gh_headers, "Accept": "application/vnd.github+json, application/zip, */*"}
                    archive_res = await self._safe_http_get(client, archive_url, dl_headers)
                    if archive_res.status_code != 200:
                        raise RepositorySyncError(
                            f"GitHub archive download failed with HTTP {archive_res.status_code} for {owner}/{repo}@{ref_for_zip}."
                        )

                # 2. GitLab (gitlab.com or self-hosted GitLab)
                elif "gitlab" in host or provider_lower == "gitlab":
                    if len(path_parts) < 2:
                        raise RepositorySyncError(f"Invalid GitLab project URL path: '{repo_url}'")
                    detected_provider = "gitlab"
                    gitlab_base = f"{parsed.scheme}://{parsed.netloc}"
                    project_path_encoded = quote_plus("/".join(path_parts))
                    gl_headers = dict(base_headers)
                    if clean_token:
                        gl_headers["Authorization"] = f"Bearer {clean_token}"

                    commit_url = (
                        f"{gitlab_base}/api/v4/projects/{project_path_encoded}/repository/commits/{quote_plus(branch)}"
                    )
                    commit_res = await self._safe_http_get(client, commit_url, gl_headers)
                    if commit_res.status_code == 200:
                        c_data = commit_res.json()
                        commit_sha = (c_data.get("id") or "").strip()
                        commit_message = (c_data.get("message") or f"GitLab branch '{branch}' sync").strip()
                        commit_author = c_data.get("author_name") or "GitLab Author"
                    else:
                        raise RepositorySyncError(
                            f"GitLab commit lookup failed (HTTP {commit_res.status_code}) for {'/'.join(path_parts)}@{branch}."
                        )

                    ref_for_zip = commit_sha or branch
                    archive_url = (
                        f"{gitlab_base}/api/v4/projects/{project_path_encoded}/repository/archive.zip?sha={quote_plus(ref_for_zip)}"
                    )
                    dl_headers = {**gl_headers, "Accept": "application/octet-stream, application/zip, */*"}
                    archive_res = await self._safe_http_get(client, archive_url, dl_headers)
                    if archive_res.status_code != 200:
                        raise RepositorySyncError(
                            f"GitLab archive download failed with HTTP {archive_res.status_code}."
                        )

                # 3. Bitbucket Cloud (bitbucket.org)
                elif "bitbucket.org" in host or provider_lower == "bitbucket":
                    if len(path_parts) < 2:
                        raise RepositorySyncError(f"Invalid Bitbucket repository URL path: '{repo_url}'")
                    detected_provider = "bitbucket"
                    workspace, repo_slug = path_parts[0], path_parts[1]
                    bb_headers = dict(base_headers)
                    if clean_token:
                        bb_headers["Authorization"] = f"Bearer {clean_token}"

                    commit_url = (
                        f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/commit/{quote(branch, safe='')}"
                    )
                    commit_res = await self._safe_http_get(client, commit_url, bb_headers)
                    if commit_res.status_code == 200:
                        c_data = commit_res.json()
                        commit_sha = (c_data.get("hash") or "").strip()
                        commit_message = (c_data.get("message") or f"Bitbucket branch '{branch}' sync").strip()
                        commit_author = ((c_data.get("author") or {}).get("raw") or "Bitbucket Author").strip()
                    else:
                        raise RepositorySyncError(
                            f"Bitbucket commit lookup failed (HTTP {commit_res.status_code}) for {workspace}/{repo_slug}@{branch}."
                        )

                    ref_for_zip = commit_sha or branch
                    archive_url = f"https://bitbucket.org/{workspace}/{repo_slug}/get/{quote(ref_for_zip, safe='')}.zip"
                    dl_headers = {**bb_headers, "Accept": "application/zip, application/octet-stream, */*"}
                    archive_res = await self._safe_http_get(client, archive_url, dl_headers)
                    if archive_res.status_code != 200:
                        raise RepositorySyncError(
                            f"Bitbucket archive download failed with HTTP {archive_res.status_code}."
                        )

                # 4. Generic HTTPS ZIP archive endpoint
                else:
                    generic_headers = dict(base_headers)
                    if clean_token:
                        generic_headers["Authorization"] = f"Bearer {clean_token}"
                    archive_url = (
                        repo_url if repo_url.lower().endswith(".zip")
                        else f"{repo_url.rstrip('/')}/archive/{quote(branch, safe='')}.zip"
                    )
                    archive_res = await self._safe_http_get(client, archive_url, generic_headers)
                    if archive_res.status_code != 200:
                        raise RepositorySyncError(
                            f"Remote archive download failed with HTTP {archive_res.status_code} from '{archive_url}'."
                        )
                    commit_message = f"Synchronized archive from {host} ({branch})"
                    commit_author = host

        except (UnsafeRepositoryURLError, ArchiveSecurityError, RepositorySyncError):
            raise
        except httpx.TimeoutException as e:
            raise RepositorySyncError(f"Repository download timed out after {self.TIMEOUT_SECONDS}s: {e}") from e
        except httpx.RequestError as e:
            raise RepositorySyncError(f"Network error communicating with repository provider: {e}") from e

        extraction_stats = self.extract_zip_repository_safely(archive_res.content, target_dir)

        if not commit_sha:
            inferred = self._extract_sha_from_zip_bytes(archive_res.content)
            commit_sha = inferred or f"sha256:{hashlib.sha256(archive_res.content).hexdigest()[:32]}"

        return {
            "provider": detected_provider,
            "commit_sha": commit_sha[:64],
            "commit_message": commit_message[:500],
            "commit_author": commit_author[:255],
            "extraction_stats": extraction_stats,
        }

    def _resolve_effective_root(self, base_dir: str) -> str:
        """If unzipped archive contains a single top-level directory, analyze that directory."""
        entries = [os.path.join(base_dir, e) for e in os.listdir(base_dir)]
        dirs = [e for e in entries if os.path.isdir(e)]
        files = [e for e in entries if os.path.isfile(e)]
        if len(dirs) == 1 and len(files) == 0:
            return dirs[0]
        return base_dir

    @staticmethod
    def _is_path_excluded(rel_path: str, excluded_paths: Optional[List[str]]) -> bool:
        if not excluded_paths:
            return False
        import fnmatch
        rel_norm = rel_path.replace("\\", "/").lstrip("/")
        for pat in excluded_paths:
            pat_clean = (pat or "").strip().replace("\\", "/").lstrip("/")
            if not pat_clean:
                continue
            if fnmatch.fnmatch(rel_norm, pat_clean):
                return True
            if pat_clean.endswith("/**") and (
                rel_norm == pat_clean[:-3] or rel_norm.startswith(pat_clean[:-2])
            ):
                return True
        return False

    def _profile_repository_structure(
        self,
        root_dir: str,
        dependencies: Optional[List[Dict[str, Any]]] = None,
        excluded_paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Identifies languages, frameworks, and build systems from source files and manifests."""
        languages = set()
        frameworks = set()
        build_tools = set()

        extension_lang_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".java": "Java",
            ".go": "Go",
            ".rs": "Rust",
            ".php": "PHP",
            ".cs": "C#",
            ".rb": "Ruby",
            ".cpp": "C++",
            ".cc": "C++",
            ".hpp": "C++",
            ".c": "C",
            ".h": "C",
            ".kt": "Kotlin",
        }

        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in SourceCodeAnalyzer.IGNORE_DIRS and not d.startswith(".")]
            for f in files:
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, root_dir).replace("\\", "/")
                if self._is_path_excluded(rel_p, excluded_paths):
                    continue

                ext = os.path.splitext(f)[1].lower()
                if ext in extension_lang_map:
                    languages.add(extension_lang_map[ext])

                f_lower = f.lower()
                if f_lower in ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
                    build_tools.add("npm/yarn/pnpm")
                elif f_lower in ("requirements.txt", "pyproject.toml", "poetry.lock", "pipfile", "pipfile.lock"):
                    build_tools.add("pip/poetry")
                elif f_lower in ("pom.xml", "build.gradle", "build.gradle.kts"):
                    build_tools.add("maven/gradle")
                elif f_lower in ("cargo.toml", "cargo.lock"):
                    build_tools.add("cargo")
                elif f_lower in ("go.mod", "go.sum"):
                    build_tools.add("go modules")
                elif f_lower in ("composer.json", "composer.lock"):
                    build_tools.add("composer")
                elif f_lower in ("gemfile", "gemfile.lock"):
                    build_tools.add("bundler")
                elif f_lower.endswith(".csproj") or f_lower == "packages.config":
                    build_tools.add("dotnet/nuget")
                elif f_lower == "dockerfile":
                    build_tools.add("docker")
                elif f_lower in ("docker-compose.yml", "docker-compose.yaml"):
                    build_tools.add("docker-compose")

                if f_lower in ("next.config.js", "next.config.mjs", "next.config.ts"):
                    frameworks.add("Next.js")
                elif f_lower == "angular.json":
                    frameworks.add("Angular")
                elif f_lower == "manage.py":
                    frameworks.add("Django")
                elif f_lower == "artisan":
                    frameworks.add("Laravel")

        for dep in dependencies or []:
            dep_name = (dep.get("name") or "").lower()
            for sig, fw_label in FRAMEWORK_DEPENDENCY_SIGNATURES.items():
                if dep_name == sig or dep_name.startswith(sig + "/"):
                    frameworks.add(fw_label)

        return {
            "languages": sorted(languages),
            "frameworks": sorted(frameworks),
            "build_tools": sorted(build_tools),
        }

    def _discover_and_parse_dependencies(self, root_dir: str, parser: DependencyParser) -> List[Dict[str, Any]]:
        deps, _ = self._discover_and_parse_dependencies_with_errors(root_dir, parser)
        return deps

    def _discover_and_parse_dependencies_with_errors(
        self,
        root_dir: str,
        parser: DependencyParser,
        excluded_paths: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Scans for manifest and lockfiles across all 20+ supported formats."""
        all_deps: List[Dict[str, Any]] = []
        errors: List[str] = []
        seen_keys: Dict[Tuple[str, str], int] = {}

        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in SourceCodeAnalyzer.IGNORE_DIRS and not d.startswith(".")]
            # Parse lockfiles after direct manifests or merge so pinned lockfile versions enrich direct_dep flags
            sorted_files = sorted(files, key=lambda fn: (1 if "lock" in fn.lower() or fn.lower() == "go.sum" else 0, fn))
            for f in sorted_files:
                if not self._is_manifest_file(f):
                    continue
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, root_dir).replace("\\", "/")
                if self._is_path_excluded(rel_p, excluded_paths):
                    continue
                try:
                    with open(full_p, "r", encoding="utf-8", errors="replace") as fp:
                        content = fp.read()
                    extracted = parser.parse_manifest(f, content)
                    for dep in extracted:
                        name = (dep.get("name") or "").strip()
                        if not name:
                            continue
                        ecosystem = (dep.get("ecosystem") or "unknown").strip()
                        installed_ver = (dep.get("installed_version") or dep.get("version") or "unknown").strip()
                        dep_record = {
                            "name": name,
                            "ecosystem": ecosystem,
                            "installed_version": installed_ver,
                            "category": dep.get("category", "Library"),
                            "is_direct_dep": bool(dep.get("is_direct_dep", True)),
                            "license": dep.get("license"),
                            "file_source": rel_p,
                        }
                        dedup_key = (ecosystem.lower(), name.lower())
                        if dedup_key not in seen_keys:
                            seen_keys[dedup_key] = len(all_deps)
                            all_deps.append(dep_record)
                        else:
                            existing = all_deps[seen_keys[dedup_key]]
                            # Prefer exact lockfile version over loose manifest range while preserving direct flag
                            if existing["installed_version"] in ("latest", "unknown", "*") and installed_ver not in ("latest", "unknown", "*"):
                                existing["installed_version"] = installed_ver
                            if dep_record["is_direct_dep"]:
                                existing["is_direct_dep"] = True
                            if not existing.get("license") and dep_record.get("license"):
                                existing["license"] = dep_record["license"]
                except Exception as e:
                    msg = f"Error parsing dependency manifest '{rel_p}': {e}"
                    logger.warning(msg)
                    errors.append(msg)

        return all_deps, errors


def persist_ingestion_snapshot(
    db,
    org_id: str,
    project_id: str,
    ingestion_result: Dict[str, Any],
    repo_conn=None,
    ingestion_run=None,
    repo_url_or_filename: Optional[str] = None,
) -> Tuple[Any, bool]:
    """
    Atomically persists durable RepositoryAnalysisSnapshot, Technology/ProjectTechnology
    inventory, Project languages/frameworks, and RepositoryConnection sync metadata
    BEFORE any temporary workspace is removed.
    Idempotent on (project_id, commit_sha, analyzer_version).
    Returns (snapshot, reused_existing_snapshot).
    """
    from app.models.all_models import (
        Project,
        RepositoryConnection,
        RepositoryAnalysisSnapshot,
        Technology,
        ProjectTechnology,
    )

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project '{project_id}' not found during snapshot persistence.")

    if repo_conn is None:
        repo_conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()

    commit_sha = (ingestion_result.get("commit_sha") or "").strip() or f"manual:{uuid.uuid4().hex[:16]}"
    analyzer_version = ingestion_result.get("analyzer_version") or RepositoryIngestionService.ANALYZER_VERSION
    branch = ingestion_result.get("branch") or (repo_conn.selected_branch if repo_conn else "main") or "main"
    provider = ingestion_result.get("provider") or (repo_conn.provider if repo_conn else "github")

    profile = ingestion_result.get("profile") or {}
    code_analysis = ingestion_result.get("code_analysis") or {}
    dependencies = ingestion_result.get("dependencies") or []

    # Idempotency check: reuse existing snapshot for identical (project_id, commit_sha, analyzer_version)
    existing_snapshot = (
        db.query(RepositoryAnalysisSnapshot)
        .filter(
            RepositoryAnalysisSnapshot.project_id == project_id,
            RepositoryAnalysisSnapshot.commit_sha == commit_sha,
            RepositoryAnalysisSnapshot.analyzer_version == analyzer_version,
        )
        .first()
    )

    reused_existing = False
    if existing_snapshot is not None:
        snapshot = existing_snapshot
        reused_existing = True
    else:
        snapshot = RepositoryAnalysisSnapshot(
            org_id=org_id,
            project_id=project_id,
            repo_connection_id=repo_conn.id if repo_conn else None,
            ingestion_run_id=ingestion_run.id if ingestion_run else None,
            provider=provider,
            branch=branch,
            commit_sha=commit_sha,
            commit_message=ingestion_result.get("commit_message", ""),
            commit_author=ingestion_result.get("commit_author", ""),
            analyzer_version=analyzer_version,
            files_examined=ingestion_result.get("files_examined", code_analysis.get("files_analyzed", 0)),
            files_analyzed=code_analysis.get("files_analyzed", 0),
            files_excluded=ingestion_result.get("files_excluded", 0),
            unsupported_files=code_analysis.get("unsupported_files_count", 0),
            parser_failures=code_analysis.get("parser_failures_count", 0),
            lines_of_code=code_analysis.get("lines_of_code", 0),
            languages_json=profile.get("languages", []),
            frameworks_json=profile.get("frameworks", []),
            code_metrics_json={
                "test_files_count": code_analysis.get("test_files_count", 0),
                "maintainability_index": code_analysis.get("maintainability_index"),
                "avg_cyclomatic_complexity": code_analysis.get("avg_cyclomatic_complexity"),
                "max_cyclomatic_complexity": code_analysis.get("max_cyclomatic_complexity"),
                "code_duplication_percentage": code_analysis.get("code_duplication_percentage"),
                "defect_density": code_analysis.get("defect_density"),
                "quality_grade": code_analysis.get("quality_grade"),
                "build_tools": profile.get("build_tools", []),
                "language_breakdown": code_analysis.get("language_breakdown", {}),
                "hotspots": code_analysis.get("hotspots", []),
                "severity_breakdown": code_analysis.get("severity_breakdown", {}),
                "category_remediation_hours": code_analysis.get("category_remediation_hours", {}),
                "file_metrics": code_analysis.get("file_metrics", {}),
                "coverage_percentage": code_analysis.get("coverage_percentage"),
                "ast_analyzed_count": code_analysis.get("ast_analyzed_count"),
                "heuristic_analyzed_count": code_analysis.get("heuristic_analyzed_count"),
            },
            dependencies_json=dependencies,
            findings_json=code_analysis.get("findings", []),
            architecture_json=code_analysis.get("architecture_graph", {}),
        )
        db.add(snapshot)
        db.flush()

    # Sync discovered languages & frameworks onto Project
    langs = profile.get("languages") or []
    fws = profile.get("frameworks") or []
    if langs:
        project.languages = langs
    if fws:
        project.frameworks = fws

    # Upsert Technology & ProjectTechnology records idempotently
    for dep in dependencies:
        tech_name = (dep.get("name") or "").strip()
        if not tech_name:
            continue
        ecosystem = (dep.get("ecosystem") or "unknown").strip()
        installed_version = (dep.get("installed_version") or dep.get("version") or "unknown").strip()
        dep_license = dep.get("license")
        is_direct = bool(dep.get("is_direct_dep", True))
        file_source = dep.get("file_source")

        tech = (
            db.query(Technology)
            .filter(
                func.lower(Technology.name) == tech_name.lower(),
                func.lower(Technology.ecosystem) == ecosystem.lower(),
            )
            .first()
        )
        if not tech:
            tech = Technology(
                name=tech_name,
                ecosystem=ecosystem,
                category=dep.get("category", "Library"),
                latest_stable_version="unknown",
                license=dep_license,
            )
            db.add(tech)
            db.flush()
        elif dep_license and not tech.license:
            tech.license = dep_license

        pt = (
            db.query(ProjectTechnology)
            .filter(
                ProjectTechnology.project_id == project_id,
                ProjectTechnology.technology_id == tech.id,
            )
            .first()
        )
        if not pt:
            pt = ProjectTechnology(
                project_id=project_id,
                technology_id=tech.id,
                installed_version=installed_version,
                is_direct_dep=is_direct,
                file_source=file_source,
                license=dep_license,
            )
            db.add(pt)
        else:
            pt.installed_version = installed_version
            pt.is_direct_dep = is_direct
            if file_source:
                pt.file_source = file_source
            if dep_license:
                pt.license = dep_license

    # Update RepositoryConnection with authentic sync telemetry
    if repo_conn is not None:
        if not repo_conn.org_id:
            repo_conn.org_id = org_id
        repo_conn.provider = provider
        if repo_url_or_filename and not repo_conn.repo_url:
            repo_conn.repo_url = repo_url_or_filename
        repo_conn.branch = branch
        repo_conn.selected_branch = branch
        repo_conn.status = "synced"
        repo_conn.last_sync_status = SYNC_STATE_COMPLETED
        repo_conn.commit_sha = commit_sha
        repo_conn.commit_message = ingestion_result.get("commit_message", "")
        repo_conn.commit_author = ingestion_result.get("commit_author", "")
        repo_conn.file_count = code_analysis.get("files_analyzed", 0)
        repo_conn.size_bytes = ingestion_result.get("uncompressed_bytes", 0)
        repo_conn.last_synced_at = datetime.utcnow()

    if ingestion_run is not None:
        ingestion_run.status = SYNC_STATE_COMPLETED
        ingestion_run.progress_pct = 100
        ingestion_run.commit_sha = commit_sha
        ingestion_run.commit_message = ingestion_result.get("commit_message", "")
        ingestion_run.commit_author = ingestion_result.get("commit_author", "")
        ingestion_run.analyzer_version = analyzer_version
        ingestion_run.files_examined = snapshot.files_examined
        ingestion_run.files_analyzed = snapshot.files_analyzed
        ingestion_run.files_excluded = snapshot.files_excluded
        ingestion_run.lines_of_code = snapshot.lines_of_code
        ingestion_run.languages_json = profile.get("languages", [])
        ingestion_run.frameworks_json = profile.get("frameworks", [])
        ingestion_run.dependencies_count = len(dependencies)
        ingestion_run.findings_count = len(code_analysis.get("findings", []))
        errs = ingestion_result.get("analysis_errors") or []
        if errs:
            ingestion_run.error_message = "; ".join(str(x) for x in errs)[:1000]
        ingestion_run.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(snapshot)
    return snapshot, reused_existing


class IngestionJobManager:
    """
    Thread-safe in-memory and PostgreSQL-backed (`RepositoryIngestionRun`) ingestion job tracker.
    Supports canonical Phase 1.4 sync states:
    QUEUED -> CLONING_OR_DOWNLOADING -> ANALYSING -> PERSISTING -> COMPLETED / FAILED / CANCELLED,
    while preserving legacy status compatibility for existing API callers.
    """

    MAX_CONCURRENT_PER_ORG = 3
    ACTIVE_SYNC_STATES = {
        SYNC_STATE_QUEUED,
        SYNC_STATE_CLONING,
        SYNC_STATE_ANALYSING,
        SYNC_STATE_PERSISTING,
    }

    def __init__(self, persist_db: bool = True):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
        self._persist_db = persist_db

    @staticmethod
    def _normalize_states(status: str) -> Tuple[str, str]:
        raw = (status or "pending").strip()
        upper = raw.upper()
        if upper in VALID_SYNC_STATES:
            return _SYNC_STATE_TO_LEGACY[upper], upper
        sync_state = _LEGACY_TO_SYNC_STATE.get(raw.lower(), SYNC_STATE_QUEUED)
        return raw.lower(), sync_state

    def create_job(
        self,
        project_id: str,
        org_id: str,
        provider: str = "github",
        branch: str = "main",
        repository_connection_id: Optional[str] = None,
    ) -> str:
        with self._lock:
            active_count = sum(
                1
                for j in self._jobs.values()
                if j["org_id"] == org_id and j["sync_state"] in self.ACTIVE_SYNC_STATES
            )
            if active_count >= self.MAX_CONCURRENT_PER_ORG:
                raise ValueError(
                    f"Organization has reached maximum concurrent ingestion limit ({self.MAX_CONCURRENT_PER_ORG}). "
                    "Please wait for active jobs to complete."
                )

            job_id = str(uuid.uuid4())
            now_iso = datetime.utcnow().isoformat()
            self._jobs[job_id] = {
                "job_id": job_id,
                "project_id": project_id,
                "org_id": org_id,
                "provider": provider,
                "branch": branch,
                "status": "pending",
                "sync_state": SYNC_STATE_QUEUED,
                "progress": 0,
                "stage": "Job queued",
                "error": None,
                "results": None,
                "created_at": now_iso,
                "started_at": None,
                "completed_at": None,
            }

        if self._persist_db and org_id and project_id:
            try:
                from app.database import SessionLocal
                from app.models.all_models import Project, RepositoryIngestionRun

                db = SessionLocal()
                try:
                    proj_exists = (
                        db.query(Project.id)
                        .filter(Project.id == project_id, Project.org_id == org_id)
                        .first()
                    )
                    if proj_exists:
                        run = RepositoryIngestionRun(
                            id=job_id,
                            org_id=org_id,
                            project_id=project_id,
                            repo_connection_id=repository_connection_id,
                            provider=provider,
                            branch=branch,
                            status=SYNC_STATE_QUEUED,
                            progress_pct=0,
                            analyzer_version=RepositoryIngestionService.ANALYZER_VERSION,
                        )
                        db.add(run)
                        db.commit()
                finally:
                    db.close()
            except Exception as db_err:
                logger.debug(f"Skipping DB persistence for synthetic ingestion job {job_id}: {db_err}")

        return job_id

    def update_job(
        self,
        job_id: str,
        status: str,
        progress: int,
        stage: str,
        error: Optional[str] = None,
        results: Optional[Dict[str, Any]] = None,
    ) -> None:
        legacy_status, sync_state = self._normalize_states(status)
        now = datetime.utcnow()
        now_iso = now.isoformat()

        with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job["status"] = legacy_status
                job["sync_state"] = sync_state
                job["progress"] = min(100, max(0, progress))
                job["stage"] = stage
                if sync_state in (SYNC_STATE_CLONING, SYNC_STATE_ANALYSING, SYNC_STATE_PERSISTING) and not job["started_at"]:
                    job["started_at"] = now_iso
                if error is not None:
                    job["error"] = str(error)[:500]
                if results is not None:
                    job["results"] = results
                if sync_state in (SYNC_STATE_COMPLETED, SYNC_STATE_FAILED, SYNC_STATE_CANCELLED):
                    job["completed_at"] = now_iso

        if self._persist_db:
            try:
                from app.database import SessionLocal
                from app.models.all_models import RepositoryIngestionRun

                db = SessionLocal()
                try:
                    run = db.query(RepositoryIngestionRun).filter(RepositoryIngestionRun.id == job_id).first()
                    if run:
                        run.status = sync_state
                        run.progress_pct = min(100, max(0, progress))
                        if sync_state in (SYNC_STATE_CLONING, SYNC_STATE_ANALYSING, SYNC_STATE_PERSISTING) and not run.started_at:
                            run.started_at = now
                        if error is not None:
                            run.error_message = str(error)[:1000]
                        if sync_state in (SYNC_STATE_COMPLETED, SYNC_STATE_FAILED, SYNC_STATE_CANCELLED):
                            run.completed_at = now
                        db.commit()
                finally:
                    db.close()
            except Exception as db_err:
                logger.debug(f"Could not update DB ingestion run {job_id}: {db_err}")

    def get_job(self, job_id: str, org_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                if org_id and job["org_id"] != org_id:
                    return None
                return dict(job)

        if self._persist_db:
            try:
                from app.database import SessionLocal
                from app.models.all_models import RepositoryIngestionRun

                db = SessionLocal()
                try:
                    q = db.query(RepositoryIngestionRun).filter(RepositoryIngestionRun.id == job_id)
                    if org_id:
                        q = q.filter(RepositoryIngestionRun.org_id == org_id)
                    run = q.first()
                    if not run:
                        return None
                    legacy_status = _SYNC_STATE_TO_LEGACY.get(run.status, "pending")
                    progress_map = {
                        SYNC_STATE_QUEUED: 0,
                        SYNC_STATE_CLONING: 25,
                        SYNC_STATE_ANALYSING: 65,
                        SYNC_STATE_PERSISTING: 85,
                        SYNC_STATE_COMPLETED: 100,
                        SYNC_STATE_FAILED: 0,
                        SYNC_STATE_CANCELLED: 0,
                    }
                    return {
                        "job_id": run.id,
                        "project_id": run.project_id,
                        "org_id": run.org_id,
                        "provider": run.provider,
                        "branch": run.branch,
                        "status": legacy_status,
                        "sync_state": run.status,
                        "progress": run.progress_pct if run.progress_pct is not None else progress_map.get(run.status, 0),
                        "stage": run.status,
                        "error": run.error_message or None,
                        "results": {
                            "commit_sha": run.commit_sha,
                            "languages": run.languages_json or [],
                            "frameworks": run.frameworks_json or [],
                            "dependencies_count": run.dependencies_count or 0,
                            "files_analyzed": run.files_analyzed or 0,
                            "total_loc": run.lines_of_code or 0,
                            "findings_count": run.findings_count or 0,
                        } if run.status == SYNC_STATE_COMPLETED else None,
                        "created_at": run.created_at.isoformat() if run.created_at else None,
                        "started_at": run.started_at.isoformat() if run.started_at else None,
                        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                    }
                finally:
                    db.close()
            except Exception:
                return None
        return None


ingestion_job_manager = IngestionJobManager()


async def execute_async_ingestion(
    job_id: str,
    project_id: str,
    org_id: str,
    repo_url: Optional[str],
    zip_bytes: Optional[bytes] = None,
    auth_token: Optional[str] = None,
    branch: str = "main",
    provider: str = "github",
) -> None:
    """
    Executes asynchronous repository ingestion with explicit state transitions:
    QUEUED -> CLONING_OR_DOWNLOADING -> ANALYSING -> PERSISTING -> COMPLETED / FAILED.
    Persists complete analysis snapshot, dependencies, and metrics BEFORE temp workspace cleanup.
    """
    from app.database import SessionLocal
    from app.models.all_models import RepositoryConnection, RepositoryIngestionRun
    from app.services.crypto_service import decrypt_credential

    svc = RepositoryIngestionService()
    excluded_paths: Optional[List[str]] = None

    # Resolve stored credentials & repository settings if caller did not pass explicit token
    db_init = SessionLocal()
    try:
        conn_init = db_init.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
        if conn_init:
            if not auth_token and conn_init.encrypted_access_token:
                auth_token = decrypt_credential(conn_init.encrypted_access_token) or None
            meta = conn_init.metadata_json or {}
            inst_id = meta.get("installation_id")
            if not auth_token and conn_init.provider == "github" and inst_id:
                try:
                    from app.services.github_app_service import GitHubAppService
                    gh_svc = GitHubAppService()
                    if gh_svc.is_configured:
                        auth_token = gh_svc.get_installation_token(inst_id)
                except Exception as gh_err:
                    logger.warning(f"Could not obtain GitHub App installation token for {project_id}: {gh_err}")
            excluded_paths = meta.get("excluded_paths")
            conn_init.status = "syncing"
            conn_init.last_sync_status = SYNC_STATE_CLONING
            db_init.commit()
    finally:
        db_init.close()

    try:
        ingestion_job_manager.update_job(
            job_id,
            status=SYNC_STATE_CLONING,
            progress=20,
            stage="Downloading repository archive and commit metadata",
        )

        result = await svc.ingest_repository(
            repo_url=repo_url,
            zip_bytes=zip_bytes,
            auth_token=auth_token,
            branch=branch,
            provider=provider,
            excluded_paths=excluded_paths,
        )

        ingestion_job_manager.update_job(
            job_id,
            status=SYNC_STATE_ANALYSING,
            progress=65,
            stage="Completed static source-code and dependency analysis",
        )

        ingestion_job_manager.update_job(
            job_id,
            status=SYNC_STATE_PERSISTING,
            progress=85,
            stage="Persisting durable repository analysis snapshot",
        )

        db = SessionLocal()
        try:
            conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
            run = db.query(RepositoryIngestionRun).filter(RepositoryIngestionRun.id == job_id).first()
            snapshot, reused = persist_ingestion_snapshot(
                db=db,
                org_id=org_id,
                project_id=project_id,
                ingestion_result=result,
                repo_conn=conn,
                ingestion_run=run,
                repo_url_or_filename=repo_url,
            )
            snapshot_id = snapshot.id
        finally:
            db.close()

        code_analysis = result.get("code_analysis") or {}
        profile = result.get("profile") or {}
        ingestion_job_manager.update_job(
            job_id,
            status=SYNC_STATE_COMPLETED,
            progress=100,
            stage="Ingestion and snapshot persistence completed",
            results={
                "snapshot_id": snapshot_id,
                "idempotent_reused": reused,
                "commit_sha": result.get("commit_sha", ""),
                "languages": profile.get("languages", []),
                "frameworks": profile.get("frameworks", []),
                "dependencies_count": len(result.get("dependencies", [])),
                "files_analyzed": code_analysis.get("files_analyzed", 0),
                "total_loc": code_analysis.get("lines_of_code", 0),
                "findings_count": len(code_analysis.get("findings", [])),
            },
        )
    except Exception as e:
        logger.error(f"Async ingestion job {job_id} failed: {e}", exc_info=True)
        db = SessionLocal()
        try:
            conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project_id).first()
            if conn:
                conn.status = "failed"
                conn.last_sync_status = SYNC_STATE_FAILED
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

        ingestion_job_manager.update_job(
            job_id,
            status=SYNC_STATE_FAILED,
            progress=0,
            stage="Ingestion failed",
            error=str(e),
        )
