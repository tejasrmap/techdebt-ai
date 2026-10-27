import io
import zipfile
import pytest
from app.services.repository_ingestion_service import (
    RepositoryIngestionService,
    UnsafeRepositoryURLError,
    ArchiveSecurityError
)

def test_ssrf_validation_blocks_internal_and_private_addresses():
    """Verify SSRF validation rejects internal IP ranges, localhost, and AWS metadata addresses."""
    # 1. Block localhost and loopback
    is_safe, reason = RepositoryIngestionService.validate_repo_url("http://localhost:8080/repo.git")
    assert is_safe is False
    assert "localhost" in reason.lower()

    is_safe, reason = RepositoryIngestionService.validate_repo_url("http://127.0.0.1:5000/repo.git")
    assert is_safe is False
    assert "private" in reason.lower() or "loopback" in reason.lower()

    # 2. Block AWS/Cloud Metadata IP (169.254.169.254)
    is_safe, reason = RepositoryIngestionService.validate_repo_url("http://169.254.169.254/latest/meta-data/")
    assert is_safe is False

    # 3. Block Private CIDRs (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    is_safe, _ = RepositoryIngestionService.validate_repo_url("https://10.0.0.15/repo.git")
    assert is_safe is False

    is_safe, _ = RepositoryIngestionService.validate_repo_url("https://192.168.1.100/repo.git")
    assert is_safe is False

    is_safe, _ = RepositoryIngestionService.validate_repo_url("https://172.16.5.20/repo.git")
    assert is_safe is False

    # 4. Block non-HTTP schemes
    is_safe, _ = RepositoryIngestionService.validate_repo_url("file:///etc/passwd")
    assert is_safe is False

    is_safe, _ = RepositoryIngestionService.validate_repo_url("ftp://ftp.example.com/repo.zip")
    assert is_safe is False

    # 5. Allow legitimate public git repositories
    is_safe, _ = RepositoryIngestionService.validate_repo_url("https://github.com/fastapi/fastapi.git")
    assert is_safe is True

    is_safe, _ = RepositoryIngestionService.validate_repo_url("https://gitlab.com/gitlab-org/gitlab.git")
    assert is_safe is True

def test_zip_slip_path_traversal_defense():
    """Verify Zip-Slip attacks (entries with ../, absolute paths, or null bytes) are completely blocked."""
    # Craft malicious zip with ../ path traversal
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../../etc/cron.d/malicious", "* * * * * root reboot\n")
    malicious_bytes = bio.getvalue()

    with pytest.raises(ArchiveSecurityError) as exc_info:
        RepositoryIngestionService.process_zip_upload(malicious_bytes, "test_proj_zipslip")
    assert "path traversal" in str(exc_info.value).lower() or "suspicious" in str(exc_info.value).lower()

def test_zip_slip_absolute_path_defense():
    """Verify absolute paths inside archives are rejected."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("/etc/passwd", "root:x:0:0::/root:/bin/bash\n")
    malicious_bytes = bio.getvalue()

    with pytest.raises(ArchiveSecurityError):
        RepositoryIngestionService.process_zip_upload(malicious_bytes, "test_proj_abs")

def test_legitimate_zip_extraction_and_profiling():
    """Verify safe archive extraction, language profiling, and manifest discovery."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("src/main.py", "def add(a, b):\n    return a + b\n")
        zf.writestr("src/app.ts", "export const app = () => 'ok';\n")
        zf.writestr("package.json", '{"name": "test-pkg", "dependencies": {"express": "4.18.2"}}\n')
        zf.writestr("README.md", "# Test Project\n")
    safe_bytes = bio.getvalue()

    result = RepositoryIngestionService.process_zip_upload(safe_bytes, "test_proj_safe")

    assert result["file_count"] == 4
    assert result["total_size_bytes"] > 0
    assert "Python" in result["languages"]
    assert "TypeScript" in result["languages"]
    assert any("package.json" in m for m in result["manifest_files"])

