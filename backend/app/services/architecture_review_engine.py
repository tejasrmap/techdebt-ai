import os
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class AntiPatternFinding:
    rule_id: str
    title: str
    severity: str  # Critical, High, Medium, Low
    file_path: str
    description: str
    remediation: str

class ArchitectureReviewEngine:
    """
    Automated software architecture review and cloud-native readiness engine.
    Detects architectural anti-patterns, evaluates 12-Factor App compliance,
    and synthesizes target architecture blueprints with phased migration plans.
    """

    @classmethod
    def analyze_architecture(
        cls,
        files: List[str],
        code_findings: Optional[List[Dict[str, Any]]] = None,
        code_metrics: Optional[Dict[str, Any]] = None,
        technologies: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        code_findings = code_findings or []
        code_metrics = code_metrics or {}
        technologies = technologies or []

        anti_patterns: List[AntiPatternFinding] = []

        # 1. Inspect God Objects / Monolithic Bloat
        for f in code_findings:
            if f.get("rule_id") in ("EXCESSIVE_METHOD_LENGTH", "HIGH_CYCLOMATIC_COMPLEXITY", "CROSS_FILE_CODE_DUPLICATION"):
                anti_patterns.append(AntiPatternFinding(
                    rule_id="GOD_MODULE_BLOAT",
                    title="Monolithic Component / God Module",
                    severity="High" if f.get("severity") == "High" else "Medium",
                    file_path=f.get("file_path", "unknown"),
                    description=f"File exceeds complexity thresholds ({f.get('title')}), violating the Single Responsibility Principle.",
                    remediation="Extract cohesive business subdomains into isolated service classes or micro-packages."
                ))

        # 2. Inspect Separation of Concerns in Directory Hierarchy
        has_api_or_controllers = any(re.search(r"(api|controller|routes|views)", f, re.IGNORECASE) for f in files)
        has_services_or_domain = any(re.search(r"(service|domain|core|business)", f, re.IGNORECASE) for f in files)
        has_models_or_entities = any(re.search(r"(model|entity|schema|dto)", f, re.IGNORECASE) for f in files)
        has_tests = any(re.search(r"(test|spec|__test__)", f, re.IGNORECASE) for f in files)

        layering_penalties = 0.0
        if not (has_api_or_controllers and has_services_or_domain and has_models_or_entities):
            layering_penalties += 25.0
            anti_patterns.append(AntiPatternFinding(
                rule_id="LACK_OF_TIERED_ABSTRACTION",
                title="Missing Layered Architecture Boundaries",
                severity="High",
                file_path="root/",
                description="Project lacks clear separation between presentation (API), business domain (Service), and persistence (Data).",
                remediation="Adopt a 3-tier Layered or Hexagonal architecture separating routes, domain logic, and repositories."
            ))

        # 3. 12-Factor App Cloud-Native Readiness
        # Factor III: Config in environment
        config_violations = [f for f in code_findings if "hardcoded" in f.get("title", "").lower() or "secret" in f.get("title", "").lower()]
        tf_config_penalty = len(config_violations) * 15.0

        # Factor VI: Stateless processes
        state_violations = [f for f in code_findings if f.get("rule_id") == "MUTABLE_GLOBAL_STATE"]
        tf_state_penalty = len(state_violations) * 10.0

        # Factor XI: Logs as event streams
        print_findings = [f for f in code_findings if "print(" in f.get("title", "").lower()]
        tf_log_penalty = len(print_findings) * 5.0

        twelve_factor_score = max(20.0, min(100.0, 100.0 - (tf_config_penalty + tf_state_penalty + tf_log_penalty)))

        # 4. Pattern Compliance Score
        ap_penalty = sum(15.0 if ap.severity == "Critical" else 10.0 if ap.severity == "High" else 5.0 for ap in anti_patterns)
        pattern_score = max(20.0, min(100.0, 100.0 - ap_penalty - layering_penalties))

        # 5. Target Architecture Blueprint
        target_blueprint = {
            "style": "Clean Architecture / Hexagonal Service-Repository",
            "layers": [
                {
                    "layer": "Presentation / Interface Layer",
                    "components": ["FastAPI Routers", "Request Validation DTOs", "HTTP Error Mappers"],
                    "rule": "Handles serialization and HTTP protocols. Never contains domain business logic or direct database queries."
                },
                {
                    "layer": "Application / Service Layer",
                    "components": ["Business Services", "Workflow Orchestrators", "Event Handlers"],
                    "rule": "Enforces domain rules, authorization logic, and coordinates data access."
                },
                {
                    "layer": "Domain Model Layer",
                    "components": ["Domain Entities", "Value Objects", "Invariants"],
                    "rule": "Pure business entities independent of frameworks and persistence tools."
                },
                {
                    "layer": "Infrastructure / Persistence Layer",
                    "components": ["SQLAlchemy ORM Models", "External API Clients", "Cache Adapters"],
                    "rule": "Implements repository interfaces for database, network, and disk I/O."
                }
            ]
        }

        # 6. Step-by-Step Modernization Migration Plan
        migration_plan = [
            {
                "phase": "Phase 1: Boundary Isolation (Sprint 1-2)",
                "goal": "Decouple presentation routers from database models.",
                "tasks": [
                    "Extract SQL operations out of API endpoints into dedicated Service classes.",
                    "Audit codebase for hardcoded configs and migrate to environment variables.",
                    "Eliminate mutable global variables to guarantee stateless horizontal scalability."
                ]
            },
            {
                "phase": "Phase 2: Hotspot Deconstruction (Sprint 3-4)",
                "goal": "Break apart monolithic God modules and reduce cyclomatic complexity.",
                "tasks": [
                    f"Refactor identified God modules: {[ap.file_path for ap in anti_patterns[:3]]}.",
                    "Replace deeply nested branching with early-exit guard clauses.",
                    "Extract duplicated cross-module code into reusable internal domain libraries."
                ]
            },
            {
                "phase": "Phase 3: Resiliency & Cloud-Native Hardening (Sprint 5-6)",
                "goal": "Achieve 12-Factor App compliance and automated regression safety.",
                "tasks": [
                    "Configure structured JSON logging to stdout for centralized observability.",
                    "Implement graceful termination handlers for SIGTERM in worker processes.",
                    "Expand test suite coverage around core service interfaces to >= 80%."
                ]
            }
        ]

        return {
            "pattern_compliance_score": round(pattern_score, 1),
            "twelve_factor_readiness_score": round(twelve_factor_score, 1),
            "architecture_grade": "A" if pattern_score >= 85 else "B" if pattern_score >= 70 else "C" if pattern_score >= 50 else "D",
            "anti_patterns_count": len(anti_patterns),
            "anti_patterns": [
                {
                    "rule_id": ap.rule_id,
                    "title": ap.title,
                    "severity": ap.severity,
                    "file_path": ap.file_path,
                    "description": ap.description,
                    "remediation": ap.remediation
                }
                for ap in anti_patterns
            ],
            "target_architecture_blueprint": target_blueprint,
            "migration_plan": migration_plan
        }
