"""
TechDebt AI v3.1.0 — Test Suite for 10-Dimension Technical Debt Scoring,
Confidence Calibration, Effort Ranges, and Explainability (GAP-SCR-01).
"""

import pytest
from app.services.debt_scoring_engine import CommercialDebtScoringEngine


def test_dimension_weights_sum_to_one():
    weights = CommercialDebtScoringEngine.DIMENSION_WEIGHTS
    assert len(weights) == 10
    total_weight = sum(weights.values())
    assert pytest.approx(total_weight, 0.0001) == 1.0


def test_reproducible_scoring_with_full_evidence():
    code_metrics = {
        "files_analyzed": 50,
        "lines_of_code": 10000,
        "avg_cyclomatic_complexity": 3.5,
        "max_cyclomatic_complexity": 12,
        "code_duplication_percentage": 4.2,
        "maintainability_index": 78.0,
        "test_files_count": 12
    }
    tech_scores = [
        {
            "maintenance_health": 85.0,
            "version_currency": 90.0,
            "security_exposure": 80.0,
            "documentation_quality": 88.0,
            "sustainability": 82.0,
            "upgrade_complexity": 15.0
        }
    ]
    code_findings = [
        {
            "id": "CF-1",
            "category": "security",
            "severity": "High",
            "title": "SQL query concatenation"
        },
        {
            "id": "CF-2",
            "category": "architecture",
            "severity": "Medium",
            "title": "Circular dependency between core and util"
        },
        {
            "id": "CF-3",
            "category": "performance",
            "severity": "Low",
            "title": "Uncached lookup inside hot loop"
        }
    ]
    risk_findings = [
        {
            "id": "RF-1",
            "severity": "High",
            "title": "CVE-2024-1234 in requests"
        }
    ]

    res1 = CommercialDebtScoringEngine.calculate_project_debt(
        code_metrics=code_metrics,
        tech_scores=tech_scores,
        risk_findings=risk_findings,
        code_findings=code_findings,
        documentation_coverage_pct=75.0,
        measured_test_coverage_pct=65.0
    )
    res2 = CommercialDebtScoringEngine.calculate_project_debt(
        code_metrics=code_metrics,
        tech_scores=tech_scores,
        risk_findings=risk_findings,
        code_findings=code_findings,
        documentation_coverage_pct=75.0,
        measured_test_coverage_pct=65.0
    )

    # Strict reproducibility
    assert res1 == res2
    assert res1["overall_health_score"] > 0
    assert res1["confidence_level"] in ("High", "Medium")
    assert res1["evidence_coverage_pct"] >= 70.0
    assert len(res1["missing_signals"]) == 0
    assert "remediation_hours_range" in res1
    ranges = res1["remediation_hours_range"]
    assert ranges["low"] < ranges["expected"] < ranges["high"]


def test_missing_signals_reduce_confidence_and_prevent_false_health():
    # Calling with empty data should NOT yield 100% health with High confidence
    empty_res = CommercialDebtScoringEngine.calculate_project_debt(
        code_metrics={},
        tech_scores=[],
        risk_findings=[],
        code_findings=[]
    )

    assert "static_code_analysis" in empty_res["missing_signals"]
    assert "dependency_manifests" in empty_res["missing_signals"]
    assert empty_res["confidence_level"] in ("Low", "Medium")
    assert empty_res["evidence_coverage_pct"] < 60.0


def test_explain_debt_score_deduplicates_pillars_and_calculates_financial_ranges():
    code_metrics = {
        "files_analyzed": 20,
        "lines_of_code": 4000,
        "code_duplication_percentage": 5.0,
        "maintainability_index": 82.0
    }
    tech_scores = [
        {
            "maintenance_health": 80.0,
            "version_currency": 75.0,
            "security_exposure": 70.0,
            "documentation_quality": 85.0
        }
    ]
    risk_findings = [
        {"severity": "Critical", "title": "Critical RCE"}
    ]
    code_findings = [
        {"category": "security", "severity": "High", "title": "Hardcoded token"},
        {"category": "architecture", "severity": "Medium", "title": "God class"}
    ]

    explanation = CommercialDebtScoringEngine.explain_debt_score(
        code_metrics=code_metrics,
        tech_scores=tech_scores,
        risk_findings=risk_findings,
        code_findings=code_findings,
        hourly_rate=120.0
    )

    assert explanation["blended_hourly_rate_usd"] == 120.0
    assert "pillars" in explanation
    assert len(explanation["pillars"]) == 5
    pillars = explanation["pillars"]
    assert "security_debt" in pillars
    assert "architecture_debt" in pillars
    assert "code_quality_debt" in pillars
    assert "dependency_debt" in pillars
    assert "testing_debt" in pillars

    # Financial cost range
    fin_range = explanation["financial_cost_range_usd"]
    assert fin_range["low"] < fin_range["expected"] < fin_range["high"]
    assert fin_range["expected"] == pytest.approx(explanation["total_financial_cost_usd"], 0.01)
    assert len(explanation["executive_summary"]) > 20
