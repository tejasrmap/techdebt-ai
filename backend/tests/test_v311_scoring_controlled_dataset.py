import pytest
from app.services.debt_scoring_engine import CommercialDebtScoringEngine

def test_controlled_dataset_1_clean_repository():
    """Clean repo: high test ratio, low complexity, clean dependencies, zero CVEs."""
    metrics = {
        "lines_of_code": 10000,
        "files_analyzed": 50,
        "test_files_count": 25,
        "maintainability_index": 92.0,
        "avg_cyclomatic_complexity": 2.1,
        "max_cyclomatic_complexity": 8,
        "code_duplication_percentage": 1.0,
        "coverage_percentage": 88.0,
        "documented_units": 90,
        "documentable_units": 100,
    }
    findings = []
    risks = []
    tech_scores = [
        {"name": "fastapi", "ecosystem": "pypi", "version_currency": 95.0, "maintenance_health": 95.0},
        {"name": "pydantic", "ecosystem": "pypi", "version_currency": 95.0, "maintenance_health": 95.0}
    ]

    result = CommercialDebtScoringEngine.calculate_project_debt(
        code_metrics=metrics,
        code_findings=findings,
        risk_findings=risks,
        tech_scores=tech_scores
    )

    assert result["overall_health_score"] >= 80.0
    assert result["technical_debt_ratio"] < 10.0
    assert result["confidence_level"] in ("High", "Medium", "Moderate")
    assert result["scoring_version"] == "v3.1.0"
    assert result["dimensional_scores"]["code_maintainability"] >= 80.0

def test_controlled_dataset_2_high_technical_debt():
    """High debt repo: bloated complexity, 35% duplication, poor maintainability, bare exceptions."""
    metrics = {
        "lines_of_code": 80000,
        "files_analyzed": 200,
        "test_files_count": 2,
        "maintainability_index": 45.0,
        "avg_cyclomatic_complexity": 18.5,
        "max_cyclomatic_complexity": 65,
        "code_duplication_percentage": 35.0,
        "coverage_percentage": 5.0,
        "documented_units": 5,
        "documentable_units": 300,
    }
    findings = [
        {"rule_id": "EXCESSIVE_METHOD_LENGTH", "category": "complexity", "severity": "High", "estimated_remediation_hours": 3.0},
        {"rule_id": "DEEP_NESTING_LEVEL", "category": "complexity", "severity": "High", "estimated_remediation_hours": 3.0},
        {"rule_id": "CROSS_FILE_CODE_DUPLICATION", "category": "maintainability", "severity": "High", "estimated_remediation_hours": 3.0},
        {"rule_id": "BARE_EXCEPTION_SWALLOWED", "category": "reliability", "severity": "High", "estimated_remediation_hours": 3.0}
    ]
    risks = []

    result = CommercialDebtScoringEngine.calculate_project_debt(
        code_metrics=metrics,
        code_findings=findings,
        risk_findings=risks
    )

    assert result["overall_health_score"] <= 65.0
    assert result["technical_debt_ratio"] > 0.0

def test_controlled_dataset_3_security_problems():
    """Security compromised repo: eval(), exposed tokens, Critical CVE in dependency."""
    metrics = {
        "lines_of_code": 15000,
        "files_analyzed": 40,
        "test_files_count": 10,
        "maintainability_index": 80.0,
        "avg_cyclomatic_complexity": 3.0,
        "max_cyclomatic_complexity": 10,
        "code_duplication_percentage": 2.0,
    }
    findings = [
        {"rule_id": "DANGEROUS_EVAL_USAGE", "category": "security", "severity": "Critical", "estimated_remediation_hours": 6.0},
        {"rule_id": "GITHUB_TOKEN_EXPOSED", "category": "security", "severity": "Critical", "estimated_remediation_hours": 6.0},
        {"rule_id": "SQL_INJECTION_FORMAT_STRING", "category": "security", "severity": "Critical", "estimated_remediation_hours": 6.0}
    ]
    risks = [
        {"severity": "Critical", "title": "CVE-2021-44228 Log4Shell Remote Code Execution", "estimated_remediation_hours": 6.0}
    ]

    result = CommercialDebtScoringEngine.calculate_project_debt(
        code_metrics=metrics,
        code_findings=findings,
        risk_findings=risks
    )

    assert result["dimensional_scores"]["security_posture"] < 65.0
    assert result["estimated_remediation_hours"] >= 24.0

    # Also verify explain_debt_score rolls up security debt pillar
    breakdown = CommercialDebtScoringEngine.explain_debt_score(
        code_metrics=metrics,
        code_findings=findings,
        risk_findings=risks,
        hourly_rate=120.0
    )
    assert breakdown["total_financial_cost_usd"] >= 2880.0
    assert "security_debt" in breakdown["pillars"]
    assert breakdown["pillars"]["security_debt"]["score"] < 65.0
    assert "security_debt" in breakdown["pillars"]

def test_controlled_dataset_4_architecture_problems():
    """Architecture issues: circular dependencies, god modules, layer boundary violations."""
    metrics = {
        "lines_of_code": 35000,
        "files_analyzed": 60,
        "test_files_count": 8,
        "maintainability_index": 72.0,
        "avg_cyclomatic_complexity": 5.0,
    }
    findings = [
        {"rule_id": "CIRCULAR_DEPENDENCY_CYCLE", "category": "architecture", "severity": "Critical", "estimated_remediation_hours": 6.0},
        {"rule_id": "ARCHITECTURE_LAYER_VIOLATION", "category": "architecture", "severity": "High", "estimated_remediation_hours": 3.0},
        {"rule_id": "LARGE_CLASS_GOD_OBJECT", "category": "architecture", "severity": "High", "estimated_remediation_hours": 3.0}
    ]

    result = CommercialDebtScoringEngine.calculate_project_debt(
        code_metrics=metrics,
        code_findings=findings
    )

    assert result["dimensional_scores"]["architecture_quality"] < 65.0

def test_controlled_dataset_5_poor_testing():
    """Zero test files, zero coverage."""
    metrics = {
        "lines_of_code": 25000,
        "files_analyzed": 50,
        "test_files_count": 0,
        "coverage_percentage": 0.0,
        "maintainability_index": 80.0,
    }

    result = CommercialDebtScoringEngine.calculate_project_debt(
        code_metrics=metrics,
        code_findings=[]
    )

    assert result["dimensional_scores"]["test_quality"] < 50.0

def test_controlled_dataset_6_dependency_problems():
    """Outdated, vulnerable, and unmaintained dependencies."""
    metrics = {
        "lines_of_code": 12000,
        "files_analyzed": 30,
        "test_files_count": 10,
        "maintainability_index": 85.0,
    }
    tech_scores = [
        {"name": "log4j", "version_currency": 20.0, "maintenance_health": 25.0},
        {"name": "struts2", "version_currency": 30.0, "maintenance_health": 20.0},
        {"name": "unpinned-dep", "version_currency": 40.0, "maintenance_health": 30.0},
    ]

    result = CommercialDebtScoringEngine.calculate_project_debt(
        code_metrics=metrics,
        tech_scores=tech_scores
    )

    assert result["dimensional_scores"]["dependency_health"] < 65.0
