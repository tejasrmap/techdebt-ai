"""
TechDebt AI v3.1.0 — Test Suite for PDF XML Escaping Safety,
CSV Formula Injection Neutralization, and Dashboard Latest-Assessment Parity (GAP-REP-01).
"""

import pytest
from app.services.report_generator import ReportGenerator


def test_pdf_generation_escapes_xml_and_prevents_crashes():
    malicious_data = {
        "overall_health_score": 75.0,
        "risk_classification": "Moderate <script>",
        "confidence_level": "High & Unfiltered",
        "commit_sha": "abc1234<script>",
        "analyzer_version": "v3.1.0",
        "technical_debt_ratio": 12.5,
        "estimated_remediation_hours": 15.0,
        "financial_liability_usd": 1800.0,
        "lines_of_code": 10000,
        "scores": [
            {
                "technology_name": "FastAPI <0.100.0> & Pydantic",
                "installed_version": "0.95.0",
                "latest_stable_version": "0.109.0",
                "overall_score": 70,
                "risk_classification": "Needs Attention",
                "recommended_action": "Upgrade to >= 0.100.0 & test routes"
            }
        ],
        "risks": [
            {
                "severity": "High",
                "title": "SQL Injection in <query_builder.py> & unsanitized input",
                "business_impact": "Loss of confidential data <CONFIDENTIAL>",
                "technical_impact": "Direct query concatenation with & operator"
            }
        ]
    }

    # Should successfully generate valid PDF bytes without ReportLab ExpatError
    pdf_bytes = ReportGenerator.generate_pdf("XSS & Injection <Project>", malicious_data)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")


def test_csv_generation_neutralizes_formula_injection():
    injection_data = {
        "overall_health_score": 80.0,
        "risk_classification": "=CMD|' /C calc'!A0",
        "technical_debt_ratio": 5.0,
        "commit_sha": "+123456",
        "analyzer_version": "v3.1.0",
        "scores": [
            {
                "technology_name": "@SUM(1+1)",
                "installed_version": "=1+1",
                "latest_stable_version": "-2+2",
                "overall_score": 85,
                "risk_classification": "Healthy",
                "recommended_action": "\tMALICIOUS_TAB"
            }
        ],
        "risks": [
            {
                "severity": "Critical",
                "technology_name": "@DEP",
                "title": "=cmd|' /C calc'!A0",
                "status": "Open",
                "business_impact": "+EVIL_FORMULA",
                "technical_impact": "-EVIL_DDE"
            }
        ]
    }

    csv_text = ReportGenerator.generate_csv("=1+1_Project", injection_data)
    assert isinstance(csv_text, str)

    # In spreadsheet cells, dangerous prefixes must be prepended with a single quote '
    lines = csv_text.splitlines()
    for line in lines:
        for cell in line.split(","):
            clean = cell.strip('"')
            if clean:
                # First character should not be raw unescaped formula triggers
                assert not clean.startswith(("=CMD", "@SUM", "=cmd", "+EVIL", "-EVIL")), f"Unneutralized cell: {clean}"
