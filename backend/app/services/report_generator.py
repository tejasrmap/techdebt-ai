"""
TechDebt AI v3.1.0 — Enterprise Report Generation Engine.

Produces secure, publication-grade executive PDF, CSV, and JSON audit reports.
Enforces strict XML entity escaping for ReportLab flowables and formula-injection neutralization for CSV exports.
"""

import io
import csv
import json
import html
from datetime import datetime
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


def _xml_esc(val: Any) -> str:
    """Escapes XML entities (&, <, >, ", ') to prevent ReportLab XML parser crashes."""
    if val is None:
        return ""
    return html.escape(str(val))


def _csv_cell(val: Any) -> Any:
    """Neutralizes spreadsheet formula injection prefixes (=, +, -, @, tab, CR)."""
    if val is None:
        return ""
    s = str(val)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{s}"
    return s


class ReportGenerator:
    VENDOR_NAME = "GT InnoX LLP"
    PLATFORM_NAME = "TechDebt AI v3.1.0"

    @staticmethod
    def generate_json(project_name: str, assessment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate structured machine-readable JSON technical debt audit report."""
        hours = assessment_data.get("estimated_remediation_hours", 0.0) or 0.0
        liability = assessment_data.get("financial_liability_usd", round(hours * 120.0, 2))

        return {
            "metadata": {
                "vendor": ReportGenerator.VENDOR_NAME,
                "platform": ReportGenerator.PLATFORM_NAME,
                "project_name": project_name,
                "commit_sha": assessment_data.get("commit_sha", "N/A"),
                "analyzer_version": assessment_data.get("analyzer_version", "v3.1.0"),
                "scoring_version": assessment_data.get("scoring_version", "v3.1.0"),
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "format_version": "3.1.0"
            },
            "executive_summary": {
                "overall_health_score": assessment_data.get("overall_health_score", 100.0),
                "risk_classification": assessment_data.get("risk_classification", "Healthy"),
                "confidence_level": assessment_data.get("confidence_level", "High"),
                "technical_debt_ratio": assessment_data.get("technical_debt_ratio", 0.0),
                "lines_of_code": assessment_data.get("lines_of_code", 0),
                "files_analyzed": assessment_data.get("files_analyzed", 0),
                "estimated_remediation_hours": hours,
                "financial_liability_usd": liability
            },
            "pillar_breakdown": assessment_data.get("pillar_scores", {
                "code_quality": 85.0,
                "architecture": 80.0,
                "security": 90.0,
                "dependencies": 78.0,
                "maintainability": 82.0
            }),
            "technologies": assessment_data.get("scores", []),
            "risks": assessment_data.get("risks", []),
            "code_findings": assessment_data.get("code_findings", [])
        }

    @staticmethod
    def generate_csv(project_name: str, assessment_data: Dict[str, Any]) -> str:
        """Generate structured CSV audit report with formula injection neutralization."""
        output = io.StringIO()
        writer = csv.writer(output)

        hours = assessment_data.get("estimated_remediation_hours", 0.0) or 0.0
        liability = assessment_data.get("financial_liability_usd", round(hours * 120.0, 2))
        tdr = assessment_data.get("technical_debt_ratio", 0.0)

        # Header info
        writer.writerow([_csv_cell(f"{ReportGenerator.PLATFORM_NAME} - Technical Debt Audit Report")])
        writer.writerow([_csv_cell("Organization / Vendor"), _csv_cell(ReportGenerator.VENDOR_NAME)])
        writer.writerow([_csv_cell("Project Name"), _csv_cell(project_name)])
        writer.writerow([_csv_cell("Commit SHA"), _csv_cell(assessment_data.get("commit_sha", "N/A"))])
        writer.writerow([_csv_cell("Analyzer Version"), _csv_cell(assessment_data.get("analyzer_version", "v3.1.0"))])
        writer.writerow([_csv_cell("Generated Date"), _csv_cell(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))])
        writer.writerow([_csv_cell("Overall Health Score"), _csv_cell(assessment_data.get("overall_health_score", "N/A"))])
        writer.writerow([_csv_cell("Risk Classification"), _csv_cell(assessment_data.get("risk_classification", "N/A"))])
        writer.writerow([_csv_cell("Technical Debt Ratio (TDR %)"), _csv_cell(f"{tdr}%")])
        writer.writerow([_csv_cell("Estimated Remediation Liability (USD)"), _csv_cell(f"${liability:,.2f}")])
        writer.writerow([_csv_cell("Lines of Code Analyzed"), _csv_cell(assessment_data.get("lines_of_code", 0))])
        writer.writerow([])

        # Technology Details Header
        writer.writerow([_csv_cell(c) for c in [
            "Technology",
            "Installed Version",
            "Latest Version",
            "Health Score",
            "Classification",
            "Maintenance (20%)",
            "Security (20%)",
            "Currency (15%)",
            "Community (10%)",
            "Docs (10%)",
            "Ecosystem (10%)",
            "Sustainability (10%)",
            "Complexity (5%)",
            "Confidence",
            "Upgrade Complexity",
            "Recommended Action"
        ]])

        for s in assessment_data.get("scores", []):
            writer.writerow([_csv_cell(c) for c in [
                s.get("technology_name", ""),
                s.get("installed_version", ""),
                s.get("latest_stable_version", ""),
                s.get("overall_score", 0),
                s.get("risk_classification", ""),
                s.get("maintenance_health", 0),
                s.get("security_exposure", 0),
                s.get("version_currency", 0),
                s.get("community_activity", 0),
                s.get("documentation_quality", 0),
                s.get("ecosystem_compatibility", 0),
                s.get("sustainability", 0),
                s.get("upgrade_complexity", 0),
                s.get("confidence_level", ""),
                s.get("upgrade_complexity_level", ""),
                s.get("recommended_action", "")
            ]])

        writer.writerow([])
        writer.writerow([_csv_cell("Active Risk Findings")])
        writer.writerow([_csv_cell(c) for c in ["Severity", "Technology", "Risk Title", "Status", "Business Impact", "Technical Impact"]])

        for r in assessment_data.get("risks", []):
            writer.writerow([_csv_cell(c) for c in [
                r.get("severity", ""),
                r.get("technology_name", ""),
                r.get("title", ""),
                r.get("status", "Open"),
                r.get("business_impact", ""),
                r.get("technical_impact", "")
            ]])

        return output.getvalue()

    @staticmethod
    def generate_pdf(project_name: str, assessment_data: Dict[str, Any]) -> bytes:
        """Generate executive-level PDF report using ReportLab with strict XML escaping."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=6
        )
        subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#475569"),
            spaceAfter=14
        )
        heading2_style = ParagraphStyle(
            'SectionHeading',
            parent=styles['Heading2'],
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=12,
            spaceAfter=6
        )
        body_style = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#334155")
        )

        elements = []

        # Header Title
        elements.append(Paragraph(f"<b>{_xml_esc(ReportGenerator.VENDOR_NAME)}</b> — {_xml_esc(ReportGenerator.PLATFORM_NAME)}", subtitle_style))
        elements.append(Paragraph(f"Executive Technical Debt Audit: {_xml_esc(project_name)}", title_style))
        elements.append(Paragraph(
            f"<b>Audit Date:</b> {datetime.utcnow().strftime('%B %d, %Y')} | "
            f"<b>Commit:</b> {_xml_esc(str(assessment_data.get('commit_sha', 'N/A'))[:10])} | "
            f"<b>Confidence:</b> {_xml_esc(assessment_data.get('confidence_level', 'High'))} | "
            f"<b>TDR:</b> {assessment_data.get('technical_debt_ratio', 0.0)}%",
            subtitle_style
        ))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#e2e8f0"), spaceAfter=12))

        # Executive Summary Box
        score = assessment_data.get("overall_health_score", 100)
        risk_class = assessment_data.get("risk_classification", "Healthy")
        hours = assessment_data.get("estimated_remediation_hours", 0.0) or 0.0
        liability = assessment_data.get("financial_liability_usd", round(hours * 120.0, 2))

        exec_summary_text = (
            f"<b>Executive Summary:</b> {_xml_esc(project_name)} received an overall Technology Health Score of "
            f"<b>{score}/100</b> ({_xml_esc(risk_class)}). "
            f"Estimated total remediation liability is <b>${liability:,.2f} USD</b> ({hours:.1f} engineering hours). "
            f"Total codebase analyzed: <b>{assessment_data.get('lines_of_code', 0):,} LOC</b> across "
            f"<b>{len(assessment_data.get('scores', []))} dependencies</b>."
        )
        elements.append(Paragraph(exec_summary_text, body_style))
        elements.append(Spacer(1, 10))

        # Key Metrics Table
        metrics_data = [
            ["Health Score", "Risk Rating", "TDR", "Remediation Liability", "Dependencies"],
            [f"{score} / 100", _xml_esc(risk_class), f"{assessment_data.get('technical_debt_ratio', 0.0)}%", f"${liability:,.2f}", str(len(assessment_data.get('scores', [])))]
        ]
        metrics_table = Table(metrics_data, colWidths=[108, 108, 108, 114, 102])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ]))
        elements.append(metrics_table)
        elements.append(Spacer(1, 12))

        # Technology Inventory Breakdown
        elements.append(Paragraph("Technology Inventory & Scores", heading2_style))
        tech_rows = [["Technology", "Installed", "Latest", "Score", "Rating", "Action"]]
        for s in assessment_data.get("scores", [])[:15]:
            tech_rows.append([
                _xml_esc(s.get("technology_name", ""))[:20],
                _xml_esc(s.get("installed_version", ""))[:12],
                _xml_esc(s.get("latest_stable_version", ""))[:12],
                str(s.get("overall_score", 0)),
                _xml_esc(s.get("risk_classification", ""))[:12],
                _xml_esc(s.get("recommended_action", ""))[:40] + ("..." if len(str(s.get("recommended_action", ""))) > 40 else "")
            ])

        tech_table = Table(tech_rows, colWidths=[110, 75, 75, 50, 80, 150])
        tech_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (3, 0), (3, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ]))
        elements.append(tech_table)
        elements.append(Spacer(1, 12))

        # Identified Risks Section
        risks = assessment_data.get("risks", [])
        if risks:
            elements.append(Paragraph("Priority Risk Findings", heading2_style))
            risk_rows = [["Severity", "Finding Title", "Business Impact", "Technical Impact"]]
            for r in risks[:6]:
                risk_rows.append([
                    _xml_esc(r.get("severity", "Medium")),
                    Paragraph(f"<b>{_xml_esc(r.get('title', ''))}</b>", body_style),
                    Paragraph(_xml_esc(r.get("business_impact", ""))[:100], body_style),
                    Paragraph(_xml_esc(r.get("technical_impact", ""))[:100], body_style)
                ])
            risk_table = Table(risk_rows, colWidths=[65, 145, 165, 165])
            risk_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#dc2626")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#fca5a5")),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#fef2f2")]),
            ]))
            elements.append(risk_table)

        doc.build(elements)
        return buffer.getvalue()

    @staticmethod
    def generate_portfolio_csv(org_name: str, portfolio_data: Dict[str, Any]) -> str:
        """Generate organization-wide portfolio CSV report with formula injection neutralization."""
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([_csv_cell(f"{ReportGenerator.PLATFORM_NAME} - Enterprise Portfolio Report")])
        writer.writerow([_csv_cell("Organization"), _csv_cell(org_name)])
        writer.writerow([_csv_cell("Generated Date"), _csv_cell(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))])
        writer.writerow([_csv_cell("Total Projects"), _csv_cell(portfolio_data.get("total_projects", 0))])
        writer.writerow([_csv_cell("Average Health Score"), _csv_cell(portfolio_data.get("average_health_score", 100.0))])
        writer.writerow([_csv_cell("Total Financial Liability (USD)"), _csv_cell(f"${portfolio_data.get('total_liability_usd', 0.0):,.2f}")])
        writer.writerow([])

        writer.writerow([_csv_cell(c) for c in ["Project ID", "Project Name", "Health Score", "TDR (%)", "Remediation Liability ($)", "Lines of Code", "Critical Risks", "Status"]])
        for p in portfolio_data.get("projects", []):
            writer.writerow([_csv_cell(c) for c in [
                p.get("project_id", ""),
                p.get("project_name", ""),
                p.get("health_score", 100.0),
                f"{p.get('technical_debt_ratio', 0.0)}%",
                f"${p.get('financial_liability_usd', 0.0):,.2f}",
                p.get("lines_of_code", 0),
                p.get("critical_risks_count", 0),
                p.get("risk_level", "Healthy")
            ]])

        return output.getvalue()

    @staticmethod
    def generate_portfolio_pdf(org_name: str, portfolio_data: Dict[str, Any]) -> bytes:
        """Generate executive-level portfolio PDF report with strict XML escaping."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=6
        )
        subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#475569"),
            spaceAfter=14
        )

        elements = []
        elements.append(Paragraph(f"<b>{_xml_esc(ReportGenerator.VENDOR_NAME)}</b> — {_xml_esc(ReportGenerator.PLATFORM_NAME)}", subtitle_style))
        elements.append(Paragraph(f"Portfolio Technical Debt Audit: {_xml_esc(org_name)}", title_style))
        elements.append(Paragraph(f"Generated on {datetime.utcnow().strftime('%B %d, %Y')} | Authorized Audit Report", subtitle_style))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#e2e8f0"), spaceAfter=12))

        # Metrics Table
        metrics_data = [
            ["Total Projects", "Avg Health Score", "Total Liability (USD)", "Critical Issues"],
            [
                str(portfolio_data.get("total_projects", 0)),
                f"{portfolio_data.get('average_health_score', 100.0)} / 100",
                f"${portfolio_data.get('total_liability_usd', 0.0):,.2f}",
                str(portfolio_data.get("total_critical_risks", 0))
            ]
        ]
        metrics_table = Table(metrics_data, colWidths=[135, 135, 135, 135])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ]))
        elements.append(metrics_table)
        elements.append(Spacer(1, 14))

        # Project Table
        p_rows = [["Project Name", "Health Score", "TDR", "Liability ($)", "Critical Risks", "Status"]]
        for p in portfolio_data.get("projects", [])[:20]:
            p_rows.append([
                _xml_esc(p.get("project_name", ""))[:25],
                str(p.get("health_score", 100.0)),
                f"{p.get('technical_debt_ratio', 0.0)}%",
                f"${p.get('financial_liability_usd', 0.0):,.2f}",
                str(p.get("critical_risks_count", 0)),
                _xml_esc(p.get("risk_level", "Healthy"))
            ])
        p_table = Table(p_rows, colWidths=[150, 75, 65, 90, 80, 80])
        p_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ]))
        elements.append(p_table)

        doc.build(elements)
        return buffer.getvalue()
