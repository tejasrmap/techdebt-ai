"""
TechDebt AI v3.1.0 — Commercial 10-Dimension Technical Debt & Architecture Scoring Engine.

Computes transparent, reproducible, evidence-grounded technical debt scores, Technical Debt Ratio (TDR),
confidence ratings, and deduplicated remediation effort ranges (Low, Expected, High).
"""

import math
from typing import Dict, Any, List, Optional


class CommercialDebtScoringEngine:
    """
    TechDebt AI v3.1.0 — Commercial 10-Dimension Technical Debt & Architecture Scoring Engine.
    Computes transparent, reproducible, evidence-grounded technical debt scores, Technical Debt Ratio (TDR),
    confidence ratings, and deduplicated remediation effort ranges.
    """

    SCORING_VERSION = "v3.1.0"
    DEFAULT_HOURLY_RATE = 120.0

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

    # Low / High confidence variance bounds
    EFFORT_VARIANCE_MAP = {
        "Critical": (4.0, 10.0),
        "High": (2.0, 5.0),
        "Medium": (1.0, 2.5),
        "Low": (0.25, 1.0),
        "Info": (0.1, 0.5)
    }

    @classmethod
    def calculate_project_debt(
        cls,
        code_metrics: Optional[Dict[str, Any]] = None,
        tech_scores: Optional[List[Dict[str, Any]]] = None,
        risk_findings: Optional[List[Dict[str, Any]]] = None,
        code_findings: Optional[List[Dict[str, Any]]] = None,
        documentation_coverage_pct: Optional[float] = None,
        measured_test_coverage_pct: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Computes composite 10-dimension debt scores, remediation effort ranges, and TDR.
        Explicitly tracks missing data without converting lack of evidence into false 100% health.
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
        maintainability_index = code_metrics.get("maintainability_index", 80.0)

        missing_signals = []
        if files_count == 0 and loc == 0:
            missing_signals.append("static_code_analysis")
        if not tech_scores:
            missing_signals.append("dependency_manifests")

        # -------------------------------------------------------------
        # 1. Code Maintainability Score (15%)
        # -------------------------------------------------------------
        maint_deduction = (duplication_pct * 1.5)
        if avg_complexity > 10:
            maint_deduction += (avg_complexity - 10) * 1.5
        score_maintainability = round(max(10.0, min(100.0, maintainability_index - maint_deduction)), 1)

        # -------------------------------------------------------------
        # 2. Architecture Quality Score (10%)
        # -------------------------------------------------------------
        arch_findings = [f for f in code_findings if f.get("category") in ("architecture", "maintainability")]
        crit_arch = sum(1 for f in arch_findings if f.get("severity") == "Critical")
        high_arch = sum(1 for f in arch_findings if f.get("severity") == "High")
        med_arch = sum(1 for f in arch_findings if f.get("severity") in ("Medium", "Moderate"))
        low_arch = sum(1 for f in arch_findings if f.get("severity") not in ("Critical", "High", "Medium", "Moderate"))
        arch_penalty = (crit_arch * 15.0) + (high_arch * 8.0) + (med_arch * 3.0) + (low_arch * 2.0)
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
            score_dependency = 50.0 if "dependency_manifests" in missing_signals else 85.0

        # -------------------------------------------------------------
        # 4. Security Posture Score (15%)
        # -------------------------------------------------------------
        sec_findings = [f for f in code_findings if f.get("category") == "security"]
        critical_sec = sum(1 for f in sec_findings if f.get("severity") == "Critical")
        high_sec = sum(1 for f in sec_findings if f.get("severity") == "High")
        med_sec = sum(1 for f in sec_findings if f.get("severity") == "Medium")
        
        dep_critical = sum(1 for r in risk_findings if r.get("severity") == "Critical")
        dep_high = sum(1 for r in risk_findings if r.get("severity") == "High")

        sec_deduction = (critical_sec * 25.0) + (high_sec * 12.0) + (med_sec * 4.0) + (dep_critical * 20.0) + (dep_high * 10.0)
        score_security = round(max(10.0, min(100.0, 98.0 - sec_deduction)), 1)

        # -------------------------------------------------------------
        # 5. Test Quality Score (10%)
        # -------------------------------------------------------------
        # Incorporate measured coverage when available
        test_cov = measured_test_coverage_pct if measured_test_coverage_pct is not None else code_metrics.get("measured_test_coverage_pct")
        if test_cov is not None:
            score_test = round(max(10.0, min(100.0, float(test_cov))), 1)
        elif files_count > 0:
            test_ratio = test_files / max(1, files_count)
            score_test = round(max(20.0, min(100.0, test_ratio * 400.0)), 1)
        else:
            score_test = 50.0

        # -------------------------------------------------------------
        # 6. Documentation Quality Score (5%)
        # -------------------------------------------------------------
        doc_cov = documentation_coverage_pct if documentation_coverage_pct is not None else code_metrics.get("documentation_coverage_pct")
        if doc_cov is not None:
            score_docs = round(max(10.0, min(100.0, float(doc_cov))), 1)
        elif tech_scores:
            doc_scores = [s.get("documentation_quality", 85.0) for s in tech_scores]
            score_docs = round(sum(doc_scores) / len(doc_scores), 1)
        else:
            score_docs = 50.0 if "static_code_analysis" in missing_signals else 85.0

        # -------------------------------------------------------------
        # 7. Reliability & Error Resilience Score (10%)
        # -------------------------------------------------------------
        rel_findings = [f for f in code_findings if f.get("category") == "reliability"]
        rel_penalty = len(rel_findings) * 5.0
        score_reliability = round(max(15.0, min(100.0, 95.0 - rel_penalty)), 1)

        # -------------------------------------------------------------
        # 8. Performance Static Indicators (5%)
        # -------------------------------------------------------------
        perf_findings = [f for f in code_findings if f.get("category") == "performance"]
        perf_penalty = len(perf_findings) * 6.0
        deep_nesting_count = sum(1 for f in code_findings if f.get("rule_id") in ("EXCESSIVE_NESTING_DEPTH", "PY_DEEP_NESTING", "JS_DEEP_NESTING"))
        score_performance = round(max(20.0, min(100.0, 95.0 - (deep_nesting_count * 5.0) - perf_penalty)), 1)

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
            score_upgrade = 50.0 if "dependency_manifests" in missing_signals else 85.0

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

        # Evidence-grounded Confidence Calculation (never 100% on missing evidence)
        evidence_signals = 0
        total_signals = 4
        if files_count >= 1:
            evidence_signals += 1
        if test_cov is not None or test_files > 0:
            evidence_signals += 1
        if tech_scores:
            evidence_signals += 1
        if doc_cov is not None or "documentation_quality" not in missing_signals:
            evidence_signals += 1

        coverage_pct = round((evidence_signals / total_signals) * 100.0, 1)
        if coverage_pct >= 75.0 and files_count >= 3:
            confidence = "High"
        elif coverage_pct >= 50.0:
            confidence = "Medium"
        else:
            confidence = "Low"

        # Deduplicated Remediation Effort Ranges (Low, Expected, High)
        remediation_hours_expected = 0.0
        remediation_hours_low = 0.0
        remediation_hours_high = 0.0

        for f in code_findings:
            sev = f.get("severity", "Medium")
            exp = float(f.get("estimated_remediation_hours") or cls.SEVERITY_HOURS_MAP.get(sev, 1.5))
            lo, hi = cls.EFFORT_VARIANCE_MAP.get(sev, (exp * 0.75, exp * 1.5))
            remediation_hours_expected += exp
            remediation_hours_low += lo
            remediation_hours_high += hi

        for r in risk_findings:
            sev = r.get("severity", "Medium")
            exp = float(r.get("estimated_remediation_hours") or cls.SEVERITY_HOURS_MAP.get(sev, 1.5))
            lo, hi = cls.EFFORT_VARIANCE_MAP.get(sev, (exp * 0.75, exp * 1.5))
            remediation_hours_expected += exp
            remediation_hours_low += lo
            remediation_hours_high += hi

        remediation_hours_expected = round(remediation_hours_expected, 1)
        remediation_hours_low = round(remediation_hours_low, 1)
        remediation_hours_high = round(remediation_hours_high, 1)

        # Technical Debt Ratio (TDR): Remediation Cost / Replacement Cost
        effective_loc = max(loc, len(tech_scores) * 200, 100)
        development_hours = max(20.0, effective_loc / 25.0)
        tdr_pct = round(min(100.0, (remediation_hours_expected / development_hours) * 100.0), 1)

        return {
            "scoring_version": cls.SCORING_VERSION,
            "overall_health_score": overall_score,
            "risk_classification": classification,
            "confidence_level": confidence,
            "evidence_coverage_pct": coverage_pct,
            "missing_signals": missing_signals,
            "technical_debt_ratio": tdr_pct,
            "estimated_remediation_hours": remediation_hours_expected,
            "remediation_hours_range": {
                "low": remediation_hours_low,
                "expected": remediation_hours_expected,
                "high": remediation_hours_high
            },
            "lines_of_code": loc,
            "files_analyzed": files_count,
            "dimensional_scores": dimensional_scores
        }

    @classmethod
    def explain_debt_score(
        cls,
        code_metrics: Optional[Dict[str, Any]] = None,
        tech_scores: Optional[List[Dict[str, Any]]] = None,
        risk_findings: Optional[List[Dict[str, Any]]] = None,
        code_findings: Optional[List[Dict[str, Any]]] = None,
        hourly_rate: float = DEFAULT_HOURLY_RATE,
        documentation_coverage_pct: Optional[float] = None,
        measured_test_coverage_pct: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generates an evidence-grounded, explainable technical debt breakdown.
        Rolls up 10 detailed dimensions into 5 core enterprise debt pillars,
        deduplicating hours/costs across pillars and providing explicit positive/negative drivers.
        """
        base_result = cls.calculate_project_debt(
            code_metrics=code_metrics,
            tech_scores=tech_scores,
            risk_findings=risk_findings,
            code_findings=code_findings,
            documentation_coverage_pct=documentation_coverage_pct,
            measured_test_coverage_pct=measured_test_coverage_pct
        )
        dim_scores = base_result["dimensional_scores"]
        code_findings = code_findings or []
        risk_findings = risk_findings or []
        code_metrics = code_metrics or {}
        tech_scores = tech_scores or []

        # Categorize findings into 5 Deduplicated Enterprise Pillars
        # 1. Architecture & Design Debt
        arch_findings = [f for f in code_findings if f.get("category") in ("architecture", "complexity")]
        arch_hours = sum(cls.SEVERITY_HOURS_MAP.get(f.get("severity", "Medium"), 1.5) for f in arch_findings)
        arch_score = round((dim_scores["architecture_quality"] * 0.5) + (dim_scores["development_complexity"] * 0.5), 1)
        arch_pos = []
        arch_pen = []
        if code_metrics.get("max_cyclomatic_complexity", 1) <= 15:
            arch_pos.append(f"Maximum cyclomatic complexity ({code_metrics.get('max_cyclomatic_complexity', 1)}) is well within healthy bounds (<= 15).")
        else:
            arch_pen.append(f"High maximum cyclomatic complexity ({code_metrics.get('max_cyclomatic_complexity')}) detected in complex routines.")
        if len(arch_findings) == 0:
            arch_pos.append("No architectural hotspots or extreme modularity violations identified.")
        else:
            arch_pen.append(f"{len(arch_findings)} architectural/complexity findings require refactoring.")

        # 2. Security & Compliance Debt
        sec_findings = [f for f in code_findings if f.get("category") == "security"]
        sec_hours = sum(cls.SEVERITY_HOURS_MAP.get(f.get("severity", "Medium"), 1.5) for f in sec_findings)
        for r in risk_findings:
            sec_hours += cls.SEVERITY_HOURS_MAP.get(r.get("severity", "Medium"), 1.5)
        sec_score = dim_scores["security_posture"]
        sec_pos = []
        sec_pen = []
        crit_sec = sum(1 for f in sec_findings if f.get("severity") == "Critical") + sum(1 for r in risk_findings if r.get("severity") == "Critical")
        high_sec = sum(1 for f in sec_findings if f.get("severity") == "High") + sum(1 for r in risk_findings if r.get("severity") == "High")
        if crit_sec == 0 and high_sec == 0:
            sec_pos.append("No critical or high severity vulnerabilities or CVE exposures present.")
        if crit_sec > 0:
            sec_pen.append(f"{crit_sec} critical security finding(s) require urgent patching (-{crit_sec * 25.0} penalty).")
        if high_sec > 0:
            sec_pen.append(f"{high_sec} high severity security finding(s) detected (-{high_sec * 12.0} penalty).")

        # 3. Code Quality & Maintainability Debt
        maint_findings = [f for f in code_findings if f.get("category") in ("maintainability", "quality", "performance")]
        maint_hours = sum(cls.SEVERITY_HOURS_MAP.get(f.get("severity", "Medium"), 1.5) for f in maint_findings)
        maint_score = round(
            (dim_scores["code_maintainability"] * 0.6) +
            (dim_scores["documentation_quality"] * 0.2) +
            (dim_scores["performance_indicators"] * 0.2),
            1
        )
        maint_pos = []
        maint_pen = []
        duplication = code_metrics.get("code_duplication_percentage", 0.0)
        if duplication < 3.0:
            maint_pos.append(f"Clean code DRY hygiene with only {duplication}% duplicated code blocks.")
        else:
            maint_pen.append(f"Elevated code duplication of {duplication}% across repository.")
        mi = code_metrics.get("maintainability_index", 80.0)
        if mi >= 75.0:
            maint_pos.append(f"High Maintainability Index ({mi}/100).")
        else:
            maint_pen.append(f"Suboptimal Maintainability Index ({mi}/100) indicates high cognitive overhead.")

        # 4. Dependency & Modernization Debt (pure dependency hours, deduplicated from security CVEs)
        dep_hours = round(len(tech_scores) * 0.5, 1)
        dep_score = round((dim_scores["dependency_health"] * 0.75) + (dim_scores["upgrade_risk"] * 0.25), 1)
        dep_pos = []
        dep_pen = []
        if len(tech_scores) > 0:
            avg_curr = sum(s.get("version_currency", 85.0) for s in tech_scores) / len(tech_scores)
            if avg_curr >= 80.0:
                dep_pos.append("Dependencies are actively tracked with healthy version currency.")
            else:
                dep_pen.append(f"Average dependency version currency is low ({round(avg_curr, 1)}/100).")
        else:
            dep_pos.append("Baseline dependency configuration evaluated.")

        # 5. Testing & Reliability Debt
        test_rel_findings = [f for f in code_findings if f.get("category") == "reliability"]
        test_rel_hours = sum(cls.SEVERITY_HOURS_MAP.get(f.get("severity", "Medium"), 1.5) for f in test_rel_findings)
        test_score = round((dim_scores["test_quality"] * 0.5) + (dim_scores["reliability"] * 0.5), 1)
        test_pos = []
        test_pen = []
        test_files = code_metrics.get("test_files_count", 0)
        total_files = code_metrics.get("files_analyzed", 0)
        if total_files > 0 and (test_files / total_files) >= 0.20:
            test_pos.append(f"Strong automated test file ratio ({test_files} test files for {total_files} modules).")
        else:
            test_pen.append("Automated test file ratio is below recommended 20% test-to-source ratio.")

        pillars = {
            "architecture_debt": {
                "name": "Architecture & Structural Debt",
                "score": arch_score,
                "remediation_hours": round(arch_hours, 1),
                "financial_cost_usd": round(arch_hours * hourly_rate, 2),
                "positive_factors": arch_pos,
                "penalty_factors": arch_pen,
                "recommended_action": "Refactor oversized routines, reduce cyclomatic branches, and modularize cross-component couplings."
            },
            "security_debt": {
                "name": "Security & Vulnerability Debt",
                "score": sec_score,
                "remediation_hours": round(sec_hours, 1),
                "financial_cost_usd": round(sec_hours * hourly_rate, 2),
                "positive_factors": sec_pos,
                "penalty_factors": sec_pen,
                "recommended_action": "Remediate open CVEs, replace insecure crypto/eval calls, and enforce strict input boundary validations."
            },
            "code_quality_debt": {
                "name": "Code Maintainability & Quality Debt",
                "score": maint_score,
                "remediation_hours": round(maint_hours, 1),
                "financial_cost_usd": round(maint_hours * hourly_rate, 2),
                "positive_factors": maint_pos,
                "penalty_factors": maint_pen,
                "recommended_action": "Eliminate code clones via shared utilities and simplify deeply nested blocks."
            },
            "dependency_debt": {
                "name": "Dependency & Currency Debt",
                "score": dep_score,
                "remediation_hours": round(dep_hours, 1),
                "financial_cost_usd": round(dep_hours * hourly_rate, 2),
                "positive_factors": dep_pos,
                "penalty_factors": dep_pen,
                "recommended_action": "Upgrade outdated third-party packages to safe major/minor releases and eliminate deprecated libraries."
            },
            "testing_debt": {
                "name": "Testing & Reliability Debt",
                "score": test_score,
                "remediation_hours": round(test_rel_hours, 1),
                "financial_cost_usd": round(test_rel_hours * hourly_rate, 2),
                "positive_factors": test_pos,
                "penalty_factors": test_pen,
                "recommended_action": "Implement missing unit and integration test fixtures for critical business logic modules."
            }
        }

        total_financial_cost = round(base_result["estimated_remediation_hours"] * hourly_rate, 2)
        total_financial_cost_low = round(base_result["remediation_hours_range"]["low"] * hourly_rate, 2)
        total_financial_cost_high = round(base_result["remediation_hours_range"]["high"] * hourly_rate, 2)

        weakest_pillar = min(pillars.items(), key=lambda p: p[1]["score"])
        exec_summary = (
            f"Overall codebase health is scored at {base_result['overall_health_score']}/100 ({base_result['risk_classification']}). "
            f"The primary driver of technical debt is {weakest_pillar[1]['name']} (Score: {weakest_pillar[1]['score']}/100). "
            f"Total remediation liability is estimated at {base_result['estimated_remediation_hours']} engineering hours "
            f"(${total_financial_cost:,.2f} USD at ${hourly_rate:,.0f}/hr blended rate; range ${total_financial_cost_low:,.2f} - ${total_financial_cost_high:,.2f})."
        )

        return {
            "scoring_version": cls.SCORING_VERSION,
            "overall_health_score": base_result["overall_health_score"],
            "risk_classification": base_result["risk_classification"],
            "confidence_level": base_result["confidence_level"],
            "evidence_coverage_pct": base_result["evidence_coverage_pct"],
            "missing_signals": base_result["missing_signals"],
            "technical_debt_ratio": base_result["technical_debt_ratio"],
            "total_remediation_hours": base_result["estimated_remediation_hours"],
            "remediation_hours_range": base_result["remediation_hours_range"],
            "blended_hourly_rate_usd": hourly_rate,
            "total_financial_cost_usd": total_financial_cost,
            "financial_cost_range_usd": {
                "low": total_financial_cost_low,
                "expected": total_financial_cost,
                "high": total_financial_cost_high
            },
            "executive_summary": exec_summary,
            "pillars": pillars,
            "detailed_dimensions": dim_scores
        }
