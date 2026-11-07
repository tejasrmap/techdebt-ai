"""
TechDebt AI v3.1.0 — Test Suite for Remediation Prioritization,
ROI Simulation Planner, and Work Package Management (GAP-ROI-01).
"""

import pytest
from datetime import datetime, timedelta
from app.services.remediation_roi_service import RemediationROIService


def test_multi_factor_priority_scoring_critical_vs_low():
    # Critical security vulnerability with high blast radius and low remediation effort
    critical_finding = {
        "id": "FINDING-SEC-01",
        "severity": "Critical",
        "category": "security",
        "confidence": "High",
        "estimated_remediation_hours": 1.0,
        "created_at": datetime.utcnow() - timedelta(days=45)
    }
    crit_calc = RemediationROIService.calculate_priority_score(critical_finding, module_fan_in=6)
    assert crit_calc["priority_tier"] == "Critical"
    assert crit_calc["priority_score"] >= 85.0
    assert "Critical severity security issue" in crit_calc["priority_rationale"]

    # Low maintainability issue with zero blast radius and high effort
    low_finding = {
        "id": "FINDING-MAINT-01",
        "severity": "Low",
        "category": "maintainability",
        "confidence": "Low",
        "estimated_remediation_hours": 10.0,
        "created_at": datetime.utcnow()
    }
    low_calc = RemediationROIService.calculate_priority_score(low_finding, module_fan_in=0)
    assert low_calc["priority_tier"] == "Low"
    assert low_calc["priority_score"] < 45.0


def test_remediation_roi_simulation_capacity_and_roi_calculation():
    findings = [
        {
            "id": "F1",
            "severity": "Critical",
            "category": "security",
            "estimated_remediation_hours": 2.0
        },
        {
            "id": "F2",
            "severity": "High",
            "category": "architecture",
            "estimated_remediation_hours": 4.0
        },
        {
            "id": "F3",
            "severity": "Medium",
            "category": "reliability",
            "estimated_remediation_hours": 8.0
        },
        {
            "id": "F4",
            "severity": "Low",
            "category": "maintainability",
            "estimated_remediation_hours": 12.0
        }
    ]

    # Team capacity: 1 dev * 5 hours/week * 2 weeks = 10 hours capacity
    roi_result = RemediationROIService.calculate_remediation_roi(
        findings=findings,
        hourly_rate=120.0,
        team_size=1,
        hours_per_week_per_dev=5.0,
        planning_horizon_weeks=2
    )

    params = roi_result["parameters"]
    summary = roi_result["summary"]

    assert params["effective_capacity_hours"] == 10.0
    # F1 (2h) + F2 (4h) = 6h fit in 10h. F3 (8h) would exceed 10h, so it's deferred.
    assert summary["planned_remediation_findings"] == 2
    assert summary["planned_remediation_hours"] == 6.0
    assert summary["remediation_investment_usd"] == pytest.approx(6.0 * 120.0, 0.01)
    assert summary["estimated_risk_avoidance_usd"] > summary["remediation_investment_usd"]
    assert summary["projected_roi_percentage"] > 0.0
    assert len(roi_result["planned_items"]) == 2
    assert len(roi_result["deferred_items"]) == 2


def test_remediation_roi_simulation_budget_constraint():
    findings = [
        {"id": "F1", "severity": "Critical", "estimated_remediation_hours": 5.0},
        {"id": "F2", "severity": "High", "estimated_remediation_hours": 5.0}
    ]

    # $600 budget at $120/hr allows at most 5 hours
    roi_result = RemediationROIService.calculate_remediation_roi(
        findings=findings,
        hourly_rate=120.0,
        team_size=5,
        hours_per_week_per_dev=10.0,
        planning_horizon_weeks=4,
        budget_usd=600.0
    )

    assert roi_result["parameters"]["effective_capacity_hours"] == 5.0
    assert roi_result["summary"]["planned_remediation_hours"] == 5.0
    assert roi_result["summary"]["remediation_investment_usd"] == 600.0
