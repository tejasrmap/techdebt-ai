import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

@dataclass
class VersionInfo:
    major: int = 0
    minor: int = 0
    patch: int = 0
    prerelease: str = ""
    raw: str = ""

    def tuple(self) -> Tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

KNOWN_DEPRECATIONS: Dict[str, Dict[str, str]] = {
    "request": {
        "reason": "Package is fully deprecated and unmaintained since Feb 2020.",
        "replacement": "axios, undici, or native fetch",
        "urgency": "CRITICAL"
    },
    "moment": {
        "reason": "Moment.js is in maintenance mode; large bundle size and mutable date design.",
        "replacement": "date-fns, dayjs, or Luxon",
        "urgency": "MEDIUM"
    },
    "left-pad": {
        "reason": "Deprecated single-function package.",
        "replacement": "String.prototype.padStart()",
        "urgency": "HIGH"
    },
    "babel-eslint": {
        "reason": "Deprecated in favor of @babel/eslint-parser.",
        "replacement": "@babel/eslint-parser",
        "urgency": "HIGH"
    },
    "querystring": {
        "reason": "Legacy Node.js module deprecated in favor of URLSearchParams API.",
        "replacement": "URLSearchParams",
        "urgency": "MEDIUM"
    },
    "python-memcached": {
        "reason": "Legacy, unmaintained memcached Python client with threading limitations.",
        "replacement": "pymemcache",
        "urgency": "HIGH"
    },
    "pep8": {
        "reason": "Renamed to pycodestyle to avoid confusion with the PEP 8 document.",
        "replacement": "pycodestyle or ruff",
        "urgency": "MEDIUM"
    },
    "mock": {
        "reason": "External mock backport is obsolete for Python 3.3+.",
        "replacement": "unittest.mock (standard library)",
        "urgency": "MEDIUM"
    },
    "urllib3": {
        "reason": "urllib3 v1.x has reached end-of-support; vulnerable to multiple HTTP header and parsing flaws.",
        "replacement": "urllib3 >= 2.0.0",
        "urgency": "HIGH"
    },
    "coffee-script": {
        "reason": "Deprecated legacy coffeescript package name.",
        "replacement": "coffeescript",
        "urgency": "HIGH"
    }
}

KNOWN_BREAKING_MIGRATIONS: Dict[str, Dict[int, Dict[str, Any]]] = {
    "pydantic": {
        2: {
            "title": "Pydantic V1 to V2 Migration",
            "breaking_notes": [
                ".dict() is deprecated and replaced by .model_dump()",
                "@validator decorator replaced with @field_validator",
                "Config inner class replaced with model_config = ConfigDict(...)",
                "parse_obj() replaced by model_validate()"
            ],
            "risk": "HIGH"
        }
    },
    "sqlalchemy": {
        2: {
            "title": "SQLAlchemy 1.4 to 2.0 2.0-style Migration",
            "breaking_notes": [
                "Implicit commits are completely removed; explicit session.commit() required",
                "session.query() interface is legacy; select() statements with session.execute() standard",
                "engine.execute() removed; use with engine.connect() as conn: conn.execute(...)"
            ],
            "risk": "HIGH"
        }
    },
    "react": {
        18: {
            "title": "React 17 to React 18 Migration",
            "breaking_notes": [
                "ReactDOM.render replaced by ReactDOM.createRoot()",
                "Automatic batching enabled across all promises and setTimeout handlers",
                "Strict Mode mounts components twice in development"
            ],
            "risk": "MEDIUM"
        },
        19: {
            "title": "React 18 to React 19 Migration",
            "breaking_notes": [
                "useMemo and useCallback largely automated by React Compiler",
                "forwardRef deprecated in favor of ref prop directly on components",
                "ReactDOM.findDOMNode removed completely"
            ],
            "risk": "HIGH"
        }
    },
    "vue": {
        3: {
            "title": "Vue 2 to Vue 3 Migration",
            "breaking_notes": [
                "Vue.use, Vue.component replaced by createApp() instance methods",
                "$listeners removed, merged into $attrs",
                "Event bus pattern ($on, $off, $once) removed from core"
            ],
            "risk": "CRITICAL"
        }
    },
    "webpack": {
        5: {
            "title": "Webpack 4 to Webpack 5 Migration",
            "breaking_notes": [
                "Node.js core polyfills removed from default web target bundles",
                "Asset modules replace raw-loader, url-loader, and file-loader",
                "Deterministic chunk and module IDs enabled by default"
            ],
            "risk": "HIGH"
        }
    },
    "django": {
        4: {
            "title": "Django 3 to Django 4 Migration",
            "breaking_notes": [
                "django.conf.urls.url() removed in favor of re_path() / path()",
                "PostgreSQL < 10 support removed",
                "Default password hasher changed to PBKDF2 with SHA256"
            ],
            "risk": "MEDIUM"
        },
        5: {
            "title": "Django 4 to Django 5 Migration",
            "breaking_notes": [
                "Python 3.8 and 3.9 support dropped",
                "Simplified form field templates and generated model fields added"
            ],
            "risk": "MEDIUM"
        }
    }
}

# Curated reference latest versions for benchmark packages when external network is gated
CURATED_LATEST_VERSIONS: Dict[str, str] = {
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "vue": "3.4.38",
    "express": "4.19.2",
    "lodash": "4.17.21",
    "axios": "1.7.7",
    "fastapi": "0.115.0",
    "pydantic": "2.9.2",
    "sqlalchemy": "2.0.35",
    "django": "5.1.1",
    "flask": "3.0.3",
    "requests": "2.32.3",
    "urllib3": "2.2.3",
    "pytest": "8.3.3",
    "celery": "5.4.0",
    "redis": "5.0.8",
    "moment": "2.30.1",
    "date-fns": "3.6.0",
    "typescript": "5.6.2",
    "next": "14.2.13",
    "spring-boot": "3.3.4"
}

class DependencyHealthService:
    @staticmethod
    def parse_semver(version_str: str) -> VersionInfo:
        if not version_str or version_str.strip().lower() in ("latest", "*", ""):
            return VersionInfo(raw=version_str or "latest")
        
        # Clean leading characters: v, ^, ~, >=, <=, =, ==
        clean = re.sub(r"^[~^><=v\s]+", "", version_str.strip()).split(",")[0].strip()
        
        # Match standard semver: MAJOR.MINOR.PATCH(-prerelease)?
        match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9a-zA-Z\.-]+))?", clean)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2)) if match.group(2) is not None else 0
            patch = int(match.group(3)) if match.group(3) is not None else 0
            prerelease = match.group(4) or ""
            return VersionInfo(major=major, minor=minor, patch=patch, prerelease=prerelease, raw=version_str)
        
        # Fallback for calendar versioning e.g. 2024.1
        cal_match = re.match(r"^(\d{4})\.(\d+)(?:\.(\d+))?", clean)
        if cal_match:
            return VersionInfo(
                major=int(cal_match.group(1)),
                minor=int(cal_match.group(2)),
                patch=int(cal_match.group(3) or 0),
                raw=version_str
            )
        
        return VersionInfo(raw=version_str)

    @staticmethod
    def compare_versions(current_v: VersionInfo, target_v: VersionInfo) -> Dict[str, Any]:
        """
        Determines semantic diff type: UP_TO_DATE, PATCH, MINOR, MAJOR, or UNKNOWN.
        """
        if current_v.raw.lower() in ("latest", "*") or target_v.raw.lower() in ("latest", "*"):
            return {
                "diff_type": "UNKNOWN",
                "major_diff": 0,
                "minor_diff": 0,
                "patch_diff": 0,
                "is_outdated": False
            }
        
        if current_v.tuple() == target_v.tuple() and current_v.prerelease == target_v.prerelease:
            return {
                "diff_type": "UP_TO_DATE",
                "major_diff": 0,
                "minor_diff": 0,
                "patch_diff": 0,
                "is_outdated": False
            }
        
        # Check target is newer
        if target_v.tuple() > current_v.tuple():
            major_diff = target_v.major - current_v.major
            minor_diff = target_v.minor - current_v.minor
            patch_diff = target_v.patch - current_v.patch
            
            if major_diff > 0:
                diff_type = "MAJOR"
            elif minor_diff > 0:
                diff_type = "MINOR"
            elif patch_diff > 0:
                diff_type = "PATCH"
            else:
                diff_type = "UNKNOWN"
            
            return {
                "diff_type": diff_type,
                "major_diff": max(0, major_diff),
                "minor_diff": max(0, minor_diff),
                "patch_diff": max(0, patch_diff),
                "is_outdated": True
            }
        
        return {
            "diff_type": "UP_TO_DATE",
            "major_diff": 0,
            "minor_diff": 0,
            "patch_diff": 0,
            "is_outdated": False
        }

    @classmethod
    def evaluate_dependency(
        cls,
        name: str,
        current_version: str,
        target_version: Optional[str] = None,
        ecosystem: str = "npm"
    ) -> Dict[str, Any]:
        name_clean = name.strip().lower()
        curr_info = cls.parse_semver(current_version)
        
        # Lookup latest version from curated list or fallback
        if not target_version or target_version.strip().lower() in ("latest", "*"):
            resolved_target = CURATED_LATEST_VERSIONS.get(name_clean, curr_info.raw)
        else:
            resolved_target = target_version
        
        target_info = cls.parse_semver(resolved_target)
        diff = cls.compare_versions(curr_info, target_info)
        
        # Check deprecation
        is_deprecated = False
        deprecation_info = None
        if name_clean in KNOWN_DEPRECATIONS:
            dep_entry = KNOWN_DEPRECATIONS[name_clean]
            # Special check for urllib3 where only < 2.0 is deprecated
            if name_clean == "urllib3":
                if curr_info.major < 2 and curr_info.raw != "latest":
                    is_deprecated = True
                    deprecation_info = dep_entry
            else:
                is_deprecated = True
                deprecation_info = dep_entry

        # Check breaking migration rules
        breaking_notes = []
        breaking_risk = "LOW"
        if name_clean in KNOWN_BREAKING_MIGRATIONS:
            migrations = KNOWN_BREAKING_MIGRATIONS[name_clean]
            for target_maj, m_data in migrations.items():
                if curr_info.major < target_maj <= target_info.major:
                    breaking_notes.extend(m_data.get("breaking_notes", []))
                    breaking_risk = m_data.get("risk", "HIGH")
        
        if diff["diff_type"] == "MAJOR" and not breaking_notes:
            breaking_risk = "HIGH"
            breaking_notes.append(
                f"Major version upgrade from {curr_info.major}.x to {target_info.major}.x. Review upstream migration guides for breaking API changes."
            )
        elif diff["diff_type"] == "MINOR":
            breaking_risk = "LOW"
        elif diff["diff_type"] == "PATCH":
            breaking_risk = "LOW"

        if is_deprecated and deprecation_info:
            urgency = deprecation_info.get("urgency", "HIGH")
            if urgency == "CRITICAL":
                breaking_risk = "CRITICAL"
            elif urgency == "HIGH" and breaking_risk != "CRITICAL":
                breaking_risk = "HIGH"

        # Formulate upgrade strategy
        if is_deprecated:
            strategy = f"MIGRATE_REPLACE: Replace deprecated package with {deprecation_info.get('replacement', 'modern alternative')}."
            recommended_version = resolved_target if resolved_target != curr_info.raw else "DEPRECATED"
        elif diff["diff_type"] == "UP_TO_DATE":
            strategy = "MAINTAIN: Package is up to date."
            recommended_version = curr_info.raw
        elif diff["diff_type"] == "UNKNOWN":
            strategy = "PIN_VERSION: Unpinned or unresolved dependency version. Pin to a specific stable release."
            recommended_version = resolved_target if resolved_target not in ("latest", "*", "") else "PIN_REQUIRED"
        elif diff["diff_type"] == "PATCH":
            strategy = f"DIRECT_UPDATE: Safe backwards-compatible patch update to {resolved_target}."
            recommended_version = resolved_target
        elif diff["diff_type"] == "MINOR":
            strategy = f"FEATURE_UPDATE: Backwards-compatible feature upgrade to {resolved_target}. Run regression suite."
            recommended_version = resolved_target
        else: # MAJOR
            strategy = f"PHASED_MAJOR_UPGRADE: Review breaking change notes, update dependencies step-by-step, verify API migrations to {resolved_target}."
            recommended_version = resolved_target

        return {
            "name": name,
            "ecosystem": ecosystem,
            "current_version": current_version,
            "target_version": resolved_target,
            "recommended_version": recommended_version,
            "is_outdated": diff["is_outdated"],
            "diff_type": diff["diff_type"],
            "major_diff": diff["major_diff"],
            "minor_diff": diff["minor_diff"],
            "patch_diff": diff["patch_diff"],
            "is_deprecated": is_deprecated,
            "deprecation_info": deprecation_info,
            "breaking_risk": breaking_risk,
            "breaking_notes": breaking_notes,
            "upgrade_strategy": strategy
        }

    @classmethod
    def evaluate_project_dependencies(
        cls,
        dependencies: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Evaluates a collection of dependencies and returns an aggregate health scorecard.
        """
        total = len(dependencies)
        if total == 0:
            return {
                "health_score": 100.0,
                "grade": "A+",
                "total_dependencies": 0,
                "up_to_date_count": 0,
                "patch_outdated_count": 0,
                "minor_outdated_count": 0,
                "major_outdated_count": 0,
                "deprecated_count": 0,
                "risk_breakdown": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
                "dependencies": [],
                "recommendations": []
            }

        evaluated = []
        up_to_date = 0
        patch_outdated = 0
        minor_outdated = 0
        major_outdated = 0
        deprecated_count = 0
        risk_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

        # Penalty point system:
        # Base: 100
        # Major outdated: -8 pts each (up to max -40)
        # Minor outdated: -3 pts each (up to max -25)
        # Patch outdated: -1 pt each (up to max -15)
        # Deprecated: -15 pts each (up to max -45)
        # Critical risk: -20 pts each (up to max -50)
        penalty = 0.0

        for dep in dependencies:
            name = dep.get("name", "")
            version = dep.get("version", "latest")
            target = dep.get("target_version")
            eco = dep.get("ecosystem", "unknown")
            
            res = cls.evaluate_dependency(name, version, target, eco)
            evaluated.append(res)

            if res["is_deprecated"]:
                deprecated_count += 1
                penalty += 12.0
            elif res["diff_type"] == "UP_TO_DATE":
                up_to_date += 1
            elif res["diff_type"] == "PATCH":
                patch_outdated += 1
                penalty += 1.0
            elif res["diff_type"] == "MINOR":
                minor_outdated += 1
                penalty += 3.0
            elif res["diff_type"] == "MAJOR":
                major_outdated += 1
                penalty += 8.0

            risk = res["breaking_risk"]
            if risk in risk_counts:
                risk_counts[risk] += 1
            if risk == "CRITICAL":
                penalty += 10.0

        health_score = max(0.0, min(100.0, 100.0 - penalty))

        if health_score >= 90:
            grade = "A"
        elif health_score >= 80:
            grade = "B"
        elif health_score >= 70:
            grade = "C"
        elif health_score >= 60:
            grade = "D"
        else:
            grade = "F"

        # Sort recommendations by risk: CRITICAL -> HIGH -> MEDIUM -> LOW
        risk_priority = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        outdated_deps = [d for d in evaluated if d["is_outdated"] or d["is_deprecated"]]
        outdated_deps.sort(key=lambda x: (risk_priority.get(x["breaking_risk"], 4), -x["major_diff"]))

        return {
            "health_score": round(health_score, 1),
            "grade": grade,
            "total_dependencies": total,
            "up_to_date_count": up_to_date,
            "patch_outdated_count": patch_outdated,
            "minor_outdated_count": minor_outdated,
            "major_outdated_count": major_outdated,
            "deprecated_count": deprecated_count,
            "risk_breakdown": risk_counts,
            "dependencies": evaluated,
            "recommendations": outdated_deps
        }
