"""
TechDebt AI v3.1.0 — Deterministic Remediation Prioritization & ROI Service.

Provides multi-factor debt prioritization scoring, configurable ROI planning,
and assignable Remediation Work Package generation.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import math


class RemediationROIService:
    """
    Deterministic engineering prioritization and ROI intelligence service.
    Ranks issues across security severity, debt category, blast radius, effort, confidence, and age.
    Calculates ROI based on engineering capacity, cost per hour, and risk avoidance value.
    """

    DEFAULT_HOURLY_RATE = 120.0

    SEVERITY_SCORES = {
        "Critical": 100.0,
        "High": 80.0,
        "Medium": 50.0,
        "Low": 25.0,
        "Info": 10.0
    }

    CATEGORY_SCORES = {
        "security": 100.0,
        "architecture": 85.0,
        "reliability": 70.0,
        "complexity": 60.0,
        "maintainability": 50.0
    }

    CONFIDENCE_SCORES = {
        "High": 100.0,
        "Medium": 75.0,
        "Low": 50.0
    }

    # Factor weights summing to 1.0
    WEIGHTS = {
        "severity": 0.35,
        "category": 0.20,
        "blast_radius": 0.15,
        "effort_roi": 0.15,
        "confidence": 0.10,
        "age": 0.05
    }

    @classmethod
    def calculate_priority_score(
        cls,
        finding: Dict[str, Any],
        module_fan_in: int = 0
    ) -> Dict[str, Any]:
        """
        Computes deterministic multi-factor priority score (0-100), priority tier,
        and transparent explanation.
        """
        sev = finding.get("severity", "Medium")
        cat = finding.get("category", "maintainability").lower()
        conf = finding.get("confidence", "High")
        hours = float(finding.get("estimated_remediation_hours", 1.5) or 1.5)

        # 1. Severity Score (35%)
        sev_score = cls.SEVERITY_SCORES.get(sev, 50.0)

        # 2. Category / Debt Impact Score (20%)
        cat_score = cls.CATEGORY_SCORES.get(cat, 50.0)

        # 3. Blast Radius (15%): based on module dependencies / fan-in
        if module_fan_in >= 5:
            blast_score = 100.0
        elif module_fan_in >= 3:
            blast_score = 80.0
        elif module_fan_in >= 1:
            blast_score = 50.0
        else:
            blast_score = 25.0

        # 4. Effort ROI (15%): smaller effort yields higher ROI
        if hours <= 1.0:
            effort_score = 100.0  # Quick win
        elif hours <= 3.0:
            effort_score = 80.0
        elif hours <= 8.0:
            effort_score = 50.0
        else:
            effort_score = 30.0

        # 5. Confidence Score (10%)
        conf_score = cls.CONFIDENCE_SCORES.get(conf, 75.0)

        # 6. Age Score (5%): age in days
        created_at = finding.get("created_at")
        age_days = 0
        if isinstance(created_at, datetime):
            age_days = (datetime.utcnow() - created_at).days
        elif isinstance(created_at, str):
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_days = (datetime.utcnow() - dt.replace(tzinfo=None)).days
            except Exception:
                age_days = 0
        age_score = min(100.0, max(0.0, age_days * 0.5))

        # Composite score
        composite = (
            (sev_score * cls.WEIGHTS["severity"]) +
            (cat_score * cls.WEIGHTS["category"]) +
            (blast_score * cls.WEIGHTS["blast_radius"]) +
            (effort_score * cls.WEIGHTS["effort_roi"]) +
            (conf_score * cls.WEIGHTS["confidence"]) +
            (age_score * cls.WEIGHTS["age"])
        )
        composite = round(min(100.0, max(0.0, composite)), 1)

        # Priority Tier
        if composite >= 80.0:
            tier = "Critical"
        elif composite >= 65.0:
            tier = "High"
        elif composite >= 45.0:
            tier = "Medium"
        else:
            tier = "Low"

        # Rationale driver
        drivers = []
        if sev in ("Critical", "High"):
            drivers.append(f"{sev} severity {cat} issue")
        if module_fan_in >= 3:
            drivers.append(f"high blast radius ({module_fan_in} dependent modules)")
        if hours <= 1.0:
            drivers.append(f"quick-win low remediation effort ({hours}h)")
        if age_days > 30:
            drivers.append(f"unresolved for {age_days} days")

        rationale = f"Ranked {tier} priority (score {composite}/100) driven by: {', '.join(drivers) if drivers else 'standard baseline impact'}."

        return {
            "priority_score": composite,
            "priority_tier": tier,
            "priority_rationale": rationale,
            "factor_breakdown": {
                "severity_score": sev_score,
                "category_score": cat_score,
                "blast_radius_score": blast_score,
                "effort_score": effort_score,
                "confidence_score": conf_score,
                "age_score": age_score
            }
        }

    @classmethod
    def calculate_remediation_roi(
        cls,
        findings: List[Dict[str, Any]],
        hourly_rate: float = DEFAULT_HOURLY_RATE,
        team_size: int = 5,
        hours_per_week_per_dev: float = 10.0,
        planning_horizon_weeks: int = 4,
        budget_usd: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculates optimal remediation plan, financial investment, risk avoidance savings,
        and return on investment (ROI) within specified capacity.
        """
        hourly_rate = float(hourly_rate or cls.DEFAULT_HOURLY_RATE)
        team_size = max(1, int(team_size or 1))
        hours_per_week_per_dev = max(1.0, float(hours_per_week_per_dev or 10.0))
        planning_horizon_weeks = max(1, int(planning_horizon_weeks or 4))

        total_capacity_hours = team_size * hours_per_week_per_dev * planning_horizon_weeks
        effective_capacity_hours = total_capacity_hours
        if budget_usd is not None and budget_usd > 0:
            budget_max_hours = budget_usd / hourly_rate
            effective_capacity_hours = min(total_capacity_hours, budget_max_hours)

        # Prioritize each finding
        scored_findings = []
        total_backlog_hours = 0.0

        for f in findings:
            hours = float(f.get("estimated_remediation_hours", 1.5) or 1.5)
            total_backlog_hours += hours
            p_info = cls.calculate_priority_score(f)
            scored = dict(f)
            scored["priority_score"] = p_info["priority_score"]
            scored["priority_tier"] = p_info["priority_tier"]
            scored["priority_rationale"] = p_info["priority_rationale"]
            scored_findings.append(scored)

        # Sort descending by priority score, then ascending by effort (best ROI first)
        scored_findings.sort(key=lambda x: (x["priority_score"], -float(x.get("estimated_remediation_hours", 1.5) or 1.5)), reverse=True)

        # Allocate within capacity
        allocated_findings = []
        deferred_findings = []
        allocated_hours = 0.0

        for f in scored_findings:
            hours = float(f.get("estimated_remediation_hours", 1.5) or 1.5)
            if (allocated_hours + hours) <= effective_capacity_hours:
                allocated_findings.append(f)
                allocated_hours += hours
            else:
                deferred_findings.append(f)

        remediation_investment_usd = round(allocated_hours * hourly_rate, 2)
        total_backlog_liability_usd = round(total_backlog_hours * hourly_rate, 2)

        # Risk Avoidance Estimation:
        # Critical security / architecture issues avoided represent substantial commercial value
        # (e.g. avoided incident downtime, breach response, customer churn)
        risk_avoidance_usd = 0.0
        for f in allocated_findings:
            sev = f.get("severity", "Medium")
            cat = f.get("category", "maintainability")
            base_risk_val = 5000.0 if sev == "Critical" else 2000.0 if sev == "High" else 500.0 if sev == "Medium" else 100.0
            if cat == "security":
                base_risk_val *= 1.5
            elif cat == "architecture":
                base_risk_val *= 1.25
            risk_avoidance_usd += base_risk_val

        risk_avoidance_usd = round(risk_avoidance_usd, 2)
        net_value_created_usd = round(risk_avoidance_usd - remediation_investment_usd, 2)
        roi_percentage = round((net_value_created_usd / remediation_investment_usd * 100.0), 1) if remediation_investment_usd > 0 else 0.0

        return {
            "parameters": {
                "blended_hourly_rate_usd": hourly_rate,
                "team_size": team_size,
                "hours_per_week_per_dev": hours_per_week_per_dev,
                "planning_horizon_weeks": planning_horizon_weeks,
                "total_capacity_hours": round(total_capacity_hours, 1),
                "effective_capacity_hours": round(effective_capacity_hours, 1),
                "budget_usd": budget_usd
            },
            "summary": {
                "total_backlog_findings": len(findings),
                "total_backlog_hours": round(total_backlog_hours, 1),
                "total_backlog_liability_usd": total_backlog_liability_usd,
                "planned_remediation_findings": len(allocated_findings),
                "planned_remediation_hours": round(allocated_hours, 1),
                "remediation_investment_usd": remediation_investment_usd,
                "estimated_risk_avoidance_usd": risk_avoidance_usd,
                "net_value_created_usd": net_value_created_usd,
                "projected_roi_percentage": roi_percentage,
                "capacity_utilization_pct": round((allocated_hours / effective_capacity_hours * 100.0), 1) if effective_capacity_hours > 0 else 0.0
            },
            "planned_items": allocated_findings,
            "deferred_items": deferred_findings
        }
