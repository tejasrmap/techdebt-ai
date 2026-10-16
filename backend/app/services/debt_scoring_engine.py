import math
from typing import Dict, Any, List, Optional

class CommercialDebtScoringEngine:
    """
    TechDebt AI v2.0.0 — Commercial 10-Dimension Technical Debt & Architecture Scoring Engine.
    Computes transparent, reproducible, evidence-grounded technical debt scores, Technical Debt Ratio (TDR),
    and remediation hour estimates using deterministic mathematical formulations.
    """

    SCORING_VERSION = "v2.0.0"

    DIMENSION_WEIGHTS = {
        "code_maintainability": 0.15,
        "architecture_quality": 0.10,
        "dependency_health": 0.15,
        "security_posture": 0.15,
        "test_quality": 0.10,
        "documentation_quality": 0.05,
        "reliability": 0.10,
        "performance_indicators": 0.05,
        "development_complexity": 0.10,
        "upgrade_risk": 0.05
    }

    SEVERITY_HOURS_MAP = {
        "Critical": 6.0,
        "High": 3.0,
        "Medium": 1.5,
        "Low": 0.5,
        "Info": 0.2
    }

    @classmethod
    def calculate_project_debt(
        cls,
        code_metrics: Optional[Dict[str, Any]] = None,
        tech_scores: Optional[List[Dict[str, Any]]] = None,
        risk_findings: Optional[List[Dict[str, Any]]] = None,
        code_findings: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Computes composite 10-dimension debt scores, remediation effort, and TDR.
        """
        code_metrics = code_metrics or {}
        tech_scores = tech_scores or []
        risk_findings = risk_findings or []
        code_findings = code_findings or []

        loc = code_metrics.get("lines_of_code", 0)
        files_count = code_metrics.get("files_analyzed", 0)
        test_files = code_metrics.get("test_files_count", 0)
        avg_complexity = code_metrics.get("avg_cyclomatic_complexity", 1.0)
        max_complexity = code_metrics.get("max_cyclomatic_complexity", 1)
        duplication_pct = code_metrics.get("code_duplication_percentage", 0.0)
        maintainability_index = code_metrics.get("maintainability_index", 85.0)

        # -------------------------------------------------------------
        # 1. Code Maintainability Score (15%)
        # -------------------------------------------------------------
        # Influenced by Maintainability Index and code duplication
        maint_deduction = (duplication_pct * 1.5)
        if avg_complexity > 10:
            maint_deduction += (avg_complexity - 10) * 1.5
        score_maintainability = round(max(10.0, min(100.0, maintainability_index - maint_deduction)), 1)

        # -------------------------------------------------------------
        # 2. Architecture Quality Score (10%)
        # -------------------------------------------------------------
        # Penalizes excessive file length and cross-file duplication
        arch_findings = [f for f in code_findings if f.get("category") in ("architecture", "maintainability")]
        arch_penalty = len(arch_findings) * 3.0
        score_architecture = round(max(15.0, min(100.0, 95.0 - arch_penalty)), 1)

        # -------------------------------------------------------------
        # 3. Dependency Health Score (15%)
        # -------------------------------------------------------------
        if tech_scores:
            dep_maintenance = [s.get("maintenance_health", 85.0) for s in tech_scores]
            dep_currency = [s.get("version_currency", 85.0) for s in tech_scores]
            dep_sustainability = [s.get("sustainability", 85.0) for s in tech_scores]
            avg_dep = (
                (sum(dep_maintenance) / len(dep_maintenance)) * 0.4 +
                (sum(dep_currency) / len(dep_currency)) * 0.4 +
                (sum(dep_sustainability) / len(dep_sustainability)) * 0.2
            )
            score_dependency = round(max(10.0, min(100.0, avg_dep)), 1)
        else:
            score_dependency = 85.0

        # -------------------------------------------------------------
        # 4. Security Posture Score (15%)
        # -------------------------------------------------------------
        sec_findings = [f for f in code_findings if f.get("category") == "security"]
        critical_sec = sum(1 for f in sec_findings if f.get("severity") == "Critical")
        high_sec = sum(1 for f in sec_findings if f.get("severity") == "High")
        med_sec = sum(1 for f in sec_findings if f.get("severity") == "Medium")
        
        # Risk findings from dependencies
        dep_critical = sum(1 for r in risk_findings if r.get("severity") == "Critical")
        dep_high = sum(1 for r in risk_findings if r.get("severity") == "High")

        sec_deduction = (critical_sec * 25.0) + (high_sec * 12.0) + (med_sec * 4.0) + (dep_critical * 20.0) + (dep_high * 10.0)
        score_security = round(max(10.0, min(100.0, 98.0 - sec_deduction)), 1)

        # -------------------------------------------------------------
        # 5. Test Quality Score (10%)
        # -------------------------------------------------------------
        if files_count > 0:
            test_ratio = test_files / max(1, files_count)
            # Ideal test ratio is 0.25 (1 test file per 4 implementation files)
            score_test = round(max(20.0, min(100.0, test_ratio * 400.0)), 1)
        else:
            score_test = 70.0

        # -------------------------------------------------------------
        # 6. Documentation Quality Score (5%)
        # -------------------------------------------------------------
        if tech_scores:
            doc_scores = [s.get("documentation_quality", 85.0) for s in tech_scores]
            score_docs = round(sum(doc_scores) / len(doc_scores), 1)
        else:
            score_docs = 85.0

        # -------------------------------------------------------------
        # 7. Reliability & Error Resilience Score (10%)
        # -------------------------------------------------------------
        rel_findings = [f for f in code_findings if f.get("category") == "reliability"]
        rel_penalty = len(rel_findings) * 5.0
        score_reliability = round(max(15.0, min(100.0, 95.0 - rel_penalty)), 1)

        # -------------------------------------------------------------
        # 8. Performance Static Indicators (5%)
        # -------------------------------------------------------------
        deep_nesting_count = sum(1 for f in code_findings if f.get("rule_id") == "EXCESSIVE_NESTING_DEPTH")
        score_performance = round(max(20.0, min(100.0, 95.0 - (deep_nesting_count * 8.0))), 1)

        # -------------------------------------------------------------
        # 9. Development & Cognitive Complexity Score (10%)
        # -------------------------------------------------------------
        comp_findings = [f for f in code_findings if f.get("category") == "complexity"]
        comp_deduction = len(comp_findings) * 4.0
        if max_complexity > 20:
            comp_deduction += (max_complexity - 20) * 1.5
        score_complexity = round(max(10.0, min(100.0, 95.0 - comp_deduction)), 1)

        # -------------------------------------------------------------
        # 10. Upgrade & Modernization Risk Score (5%)
        # -------------------------------------------------------------
        if tech_scores:
            upg_scores = [s.get("upgrade_complexity", 85.0) for s in tech_scores]
            score_upgrade = round(sum(upg_scores) / len(upg_scores), 1)
        else:
            score_upgrade = 85.0

        # -------------------------------------------------------------
        # Overall Weighted Score Calculation
        # -------------------------------------------------------------
        dimensional_scores = {
            "code_maintainability": score_maintainability,
            "architecture_quality": score_architecture,
            "dependency_health": score_dependency,
            "security_posture": score_security,
            "test_quality": score_test,
            "documentation_quality": score_docs,
            "reliability": score_reliability,
            "performance_indicators": score_performance,
            "development_complexity": score_complexity,
            "upgrade_risk": score_upgrade
        }

        overall_score = round(
            sum(dimensional_scores[k] * cls.DIMENSION_WEIGHTS[k] for k in cls.DIMENSION_WEIGHTS),
            1
        )

        # Risk Classification
        if overall_score >= 80.0:
            classification = "Healthy" if overall_score >= 88.0 else "Good"
        elif overall_score >= 65.0:
            classification = "Moderate Risk"
        elif overall_score >= 45.0:
            classification = "High Risk"
        else:
            classification = "Critical Debt"

        # Remediation Effort & Technical Debt Ratio (TDR)
        # Total remediation hours calculated from finding severities
        total_remediation_hours = sum(
            f.get("estimated_remediation_hours", cls.SEVERITY_HOURS_MAP.get(f.get("severity", "Medium"), 1.5))
            for f in code_findings
        )
        for r in risk_findings:
            total_remediation_hours += cls.SEVERITY_HOURS_MAP.get(r.get("severity", "Medium"), 1.5)

        total_remediation_hours = round(total_remediation_hours, 1)

        # Estimated development effort: standard industry average ~ 25 lines of code per dev hour
        effective_loc = max(loc, len(tech_scores) * 200, 100)
        development_hours = max(20.0, effective_loc / 25.0)
        tdr_pct = round(min(100.0, (total_remediation_hours / development_hours) * 100.0), 1)

        # Confidence level
        confidence = "High"
        if files_count < 3 and len(tech_scores) < 3:
            confidence = "Medium"

        return {
            "scoring_version": cls.SCORING_VERSION,
            "overall_health_score": overall_score,
            "risk_classification": classification,
            "confidence_level": confidence,
            "technical_debt_ratio": tdr_pct,
            "estimated_remediation_hours": total_remediation_hours,
            "lines_of_code": loc,
            "files_analyzed": files_count,
            "dimensional_scores": dimensional_scores
        }

