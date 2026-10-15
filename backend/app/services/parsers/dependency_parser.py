import re
import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        import toml as tomllib

def clean_version(raw_version: str) -> str:
    if not raw_version:
        return "latest"
    # Strip common package manager version specifiers
    cleaned = re.sub(r"^[~^><=v\s]+", "", raw_version.strip())
    # Take first version in range if multiple e.g. ">=1.0, <2.0"
    cleaned = cleaned.split(",")[0].strip()
    return cleaned if cleaned else "latest"

class DependencyParser:
    @staticmethod
    def parse_manifest(file_name: str, content: str) -> List[Dict[str, Any]]:
        return DependencyParser.parse(file_name, content)

    @staticmethod
    def parse(file_name: str, content: str) -> List[Dict[str, Any]]:
        name_lower = file_name.lower()
        if name_lower.endswith("package-lock.json"):
            return DependencyParser._parse_package_lock_json(content)
        elif name_lower.endswith("yarn.lock"):
            return DependencyParser._parse_yarn_lock(content)
        elif name_lower.endswith("poetry.lock"):
            return DependencyParser._parse_poetry_lock(content)
        elif name_lower.endswith("cargo.lock"):
            return DependencyParser._parse_cargo_lock(content)
        elif name_lower.endswith("go.sum"):
            return DependencyParser._parse_go_sum(content)
        elif name_lower.endswith("composer.lock"):
            return DependencyParser._parse_composer_lock(content)
        elif name_lower.endswith((".csproj", "packages.config")):
            return DependencyParser._parse_csproj(content)
        elif name_lower.endswith("package.json"):
            return DependencyParser._parse_package_json(content)
        elif name_lower.endswith("requirements.txt") or "requirements" in name_lower:
            return DependencyParser._parse_requirements_txt(content)
        elif name_lower.endswith("pyproject.toml"):
            return DependencyParser._parse_pyproject_toml(content)
        elif name_lower.endswith("pom.xml"):
            return DependencyParser._parse_pom_xml(content)
        elif name_lower.endswith("build.gradle") or name_lower.endswith("build.gradle.kts"):
            return DependencyParser._parse_build_gradle(content)
        elif name_lower.endswith("cargo.toml"):
            return DependencyParser._parse_cargo_toml(content)
        elif name_lower.endswith("go.mod"):
            return DependencyParser._parse_go_mod(content)
        elif name_lower.endswith("composer.json"):
            return DependencyParser._parse_composer_json(content)
        else:
            # Fallback heuristic: try JSON, then toml, then line-based
            try:
                data = json.loads(content)
                if "dependencies" in data or "require" in data:
                    return DependencyParser._parse_package_json(content)
                elif "packages" in data:
                    return DependencyParser._parse_package_lock_json(content)
            except Exception:
                pass
            return DependencyParser._parse_requirements_txt(content)

    @staticmethod
    def _parse_package_lock_json(content: str) -> List[Dict[str, Any]]:
        results = []
        try:
            data = json.loads(content)
            # npm lockfile v2 / v3
            packages = data.get("packages", {})
            for pkg_path, meta in packages.items():
                if not pkg_path:  # root package
                    continue
                pkg_name = pkg_path.split("node_modules/")[-1]
                version = meta.get("version", "latest")
                results.append({
                    "name": pkg_name,
                    "installed_version": clean_version(version),
                    "ecosystem": "npm",
                    "category": "Library",
                    "is_direct_dep": not ("node_modules/" in pkg_path[13:]),
                    "file_source": "package-lock.json"
                })

            # npm lockfile v1 fallback
            if not results and "dependencies" in data:
                for pkg_name, meta in data.get("dependencies", {}).items():
                    results.append({
                        "name": pkg_name,
                        "installed_version": clean_version(meta.get("version", "latest")),
                        "ecosystem": "npm",
                        "category": "Library",
                        "is_direct_dep": True,
                        "file_source": "package-lock.json"
                    })
        except Exception:
            pass
        return results

    @staticmethod
    def _parse_yarn_lock(content: str) -> List[Dict[str, Any]]:
        results = []
        try:
            current_pkg = None
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.endswith(":") and ("@" in line):
                    # e.g. "react@^18.2.0":
                    pkg_raw = line.split(":")[0].strip('"').strip("'")
                    current_pkg = pkg_raw.rsplit("@", 1)[0]
                elif current_pkg and line.startswith("version "):
                    ver = line.replace("version ", "").strip('"').strip("'")
                    results.append({
                        "name": current_pkg,
                        "installed_version": clean_version(ver),
                        "ecosystem": "npm",
                        "category": "Library",
                        "is_direct_dep": True,
                        "file_source": "yarn.lock"
                    })
                    current_pkg = None
        except Exception:
            pass
        return results

    @staticmethod
    def _parse_poetry_lock(content: str) -> List[Dict[str, Any]]:
        results = []
        try:
            data = tomllib.loads(content)
            packages = data.get("package", [])
            for pkg in packages:
                results.append({
                    "name": pkg.get("name", ""),
                    "installed_version": clean_version(pkg.get("version", "latest")),
                    "ecosystem": "pypi",
                    "category": "Library",
                    "is_direct_dep": pkg.get("category", "") == "main",
                    "file_source": "poetry.lock"
                })
        except Exception:
            pass
        return results

    @staticmethod
    def _parse_cargo_lock(content: str) -> List[Dict[str, Any]]:
        results = []
        try:
            data = tomllib.loads(content)
            packages = data.get("package", [])
            for pkg in packages:
                results.append({
                    "name": pkg.get("name", ""),
                    "installed_version": clean_version(pkg.get("version", "latest")),
                    "ecosystem": "cargo",
                    "category": "Crate",
                    "is_direct_dep": True,
                    "file_source": "Cargo.lock"
                })
        except Exception:
            pass
        return results

    @staticmethod
    def _parse_go_sum(content: str) -> List[Dict[str, Any]]:
        results = []
        seen = set()
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                mod_name = parts[0]
                version_raw = parts[1].split("/")[0]  # strip /go.mod
                key = (mod_name, version_raw)
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "name": mod_name,
                        "installed_version": clean_version(version_raw),
                        "ecosystem": "go",
                        "category": "Module",
                        "is_direct_dep": True,
                        "file_source": "go.sum"
                    })
        return results

    @staticmethod
    def _parse_composer_lock(content: str) -> List[Dict[str, Any]]:
        results = []
        try:
            data = json.loads(content)
            for pkg in data.get("packages", []):
                results.append({
                    "name": pkg.get("name", ""),
                    "installed_version": clean_version(pkg.get("version", "latest")),
                    "ecosystem": "packagist",
                    "category": "Package",
                    "is_direct_dep": True,
                    "file_source": "composer.lock"
                })
        except Exception:
            pass
        return results

    @staticmethod
    def _parse_csproj(content: str) -> List[Dict[str, Any]]:
        results = []
        try:
            root = ET.fromstring(content)
            for elem in root.iter():
                if elem.tag.endswith("PackageReference"):
                    name = elem.attrib.get("Include") or elem.attrib.get("Update")
                    version = elem.attrib.get("Version") or "latest"
                    if not version and elem.find("Version") is not None:
                        version = elem.find("Version").text
                    if name:
                        results.append({
                            "name": name,
                            "installed_version": clean_version(version),
                            "ecosystem": "nuget",
                            "category": "Package",
                            "is_direct_dep": True,
                            "file_source": ".csproj"
                        })
        except Exception:
            # Fallback regex
            for match in re.finditer(r'<PackageReference\s+Include=["\']([^"\']+)["\']\s+Version=["\']([^"\']+)["\']', content):
                results.append({
                    "name": match.group(1),
                    "installed_version": clean_version(match.group(2)),
                    "ecosystem": "nuget",
                    "category": "Package",
                    "is_direct_dep": True,
                    "file_source": ".csproj"
                })
        return results

    @staticmethod
    def _parse_package_json(content: str) -> List[Dict[str, Any]]:
        results = []
        try:
            data = json.loads(content)
            deps = data.get("dependencies", {})
            dev_deps = data.get("devDependencies", {})
            
            for pkg, ver in deps.items():
                results.append({
                    "name": pkg,
                    "installed_version": clean_version(str(ver)),
                    "ecosystem": "npm",
                    "category": "Library",
                    "is_direct_dep": True,
                    "file_source": "package.json"
                })
            for pkg, ver in dev_deps.items():
                results.append({
                    "name": pkg,
                    "installed_version": clean_version(str(ver)),
                    "ecosystem": "npm",
                    "category": "DevDependency",
                    "is_direct_dep": False,
                    "file_source": "package.json"
                })
        except Exception:
            pass
        return results

    @staticmethod
    def _parse_requirements_txt(content: str) -> List[Dict[str, Any]]:
        results = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-r") or line.startswith("--"):
                continue
            # Regex for name and version
            match = re.split(r"(==|>=|<=|~=|!=|>|<)", line)
            pkg_name = match[0].strip()
            # Remove environment markers like '; python_version < "3.8"'
            pkg_name = pkg_name.split(";")[0].strip()
            version = "latest"
            if len(match) > 2:
                ver_part = match[2].split(";")[0].strip()
                version = clean_version(ver_part)
            if pkg_name:
                results.append({
                    "name": pkg_name,
                    "installed_version": version,
                    "ecosystem": "pypi",
                    "category": "Library",
                    "is_direct_dep": True,
                    "file_source": "requirements.txt"
                })
        return results

    @staticmethod
    def _parse_pyproject_toml(content: str) -> List[Dict[str, Any]]:
        results = []
        try:
            data = tomllib.loads(content) if hasattr(tomllib, "loads") else {}
            # Check PEP 621 project.dependencies
            deps = data.get("project", {}).get("dependencies", [])
            for item in deps:
                if isinstance(item, str):
                    res = DependencyParser._parse_requirements_txt(item)
                    for r in res:
                        r["file_source"] = "pyproject.toml"
                        results.append(r)
            
            # Check Poetry [tool.poetry.dependencies]
            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            for pkg, ver in poetry_deps.items():
                if pkg.lower() == "python":
                    continue
                version_str = str(ver) if not isinstance(ver, dict) else str(ver.get("version", "latest"))
                results.append({
                    "name": pkg,
                    "installed_version": clean_version(version_str),
                    "ecosystem": "pypi",
                    "category": "Library",
                    "is_direct_dep": True,
                    "file_source": "pyproject.toml"
                })
        except Exception:
            pass
        return results

    @staticmethod
    def _parse_pom_xml(content: str) -> List[Dict[str, Any]]:
        results = []
        try:
            # Strip namespaces for easier parsing
            clean_xml = re.sub(r' xmlns="[^"]+"', '', content, count=1)
            root = ET.fromstring(clean_xml)
            for dep in root.findall(".//dependency"):
                group_id = dep.findtext("groupId", "").strip()
                artifact_id = dep.findtext("artifactId", "").strip()
                version = dep.findtext("version", "latest").strip()
                name = f"{group_id}:{artifact_id}" if group_id else artifact_id
                if name:
                    results.append({
                        "name": name,
                        "installed_version": clean_version(version),
                        "ecosystem": "maven",
                        "category": "Library",
                        "is_direct_dep": True,
                        "file_source": "pom.xml"
                    })
        except Exception:
            pass
        return results

    @staticmethod
    def _parse_build_gradle(content: str) -> List[Dict[str, Any]]:
        results = []
        patterns = [
            r"""(?:implementation|api|compile|testImplementation)\s*['"]([^:'"]+):([^:'"]+)(?::([^:'"]+))?['"]""",
            r"""(?:implementation|api|compile)\s*\(\s*['"]([^:'"]+):([^:'"]+)(?::([^:'"]+))?['"]\s*\)"""
        ]
        for pattern in patterns:
            matches = re.findall(pattern, content)
            for m in matches:
                group, artifact = m[0].strip(), m[1].strip()
                version = m[2].strip() if len(m) > 2 and m[2] else "latest"
                name = f"{group}:{artifact}"
                results.append({
                    "name": name,
                    "installed_version": clean_version(version),
                    "ecosystem": "gradle",
                    "category": "Library",
                    "is_direct_dep": True,
                    "file_source": "build.gradle"
                })
        return results

    @staticmethod
    def _parse_cargo_toml(content: str) -> List[Dict[str, Any]]:
        results = []
        try:
            data = tomllib.loads(content) if hasattr(tomllib, "loads") else {}
            deps = data.get("dependencies", {})
            for pkg, val in deps.items():
                ver = val if isinstance(val, str) else (val.get("version", "latest") if isinstance(val, dict) else "latest")
                results.append({
                    "name": pkg,
                    "installed_version": clean_version(str(ver)),
                    "ecosystem": "cargo",
                    "category": "Crate",
                    "is_direct_dep": True,
                    "file_source": "Cargo.toml"
                })
        except Exception:
            pass
        return results

    @staticmethod
    def _parse_go_mod(content: str) -> List[Dict[str, Any]]:
        results = []
        in_require_block = False
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            if line.startswith("require ("):
                in_require_block = True
                continue
            if in_require_block:
                if line == ")":
                    in_require_block = False
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    results.append({
                        "name": parts[0],
                        "installed_version": clean_version(parts[1]),
                        "ecosystem": "go",
                        "category": "Module",
                        "is_direct_dep": not ("// indirect" in line),
                        "file_source": "go.mod"
                    })
            elif line.startswith("require "):
                parts = line.replace("require ", "").split()
                if len(parts) >= 2:
                    results.append({
                        "name": parts[0],
                        "installed_version": clean_version(parts[1]),
                        "ecosystem": "go",
                        "category": "Module",
                        "is_direct_dep": not ("// indirect" in line),
                        "file_source": "go.mod"
                    })
        return results

    @staticmethod
    def _parse_composer_json(content: str) -> List[Dict[str, Any]]:
        results = []
        try:
            data = json.loads(content)
            reqs = data.get("require", {})
            for pkg, ver in reqs.items():
                if pkg.lower() == "php":
                    continue
                results.append({
                    "name": pkg,
                    "installed_version": clean_version(str(ver)),
                    "ecosystem": "packagist",
                    "category": "Package",
                    "is_direct_dep": True,
                    "file_source": "composer.json"
                })
        except Exception:
            pass
        return results

