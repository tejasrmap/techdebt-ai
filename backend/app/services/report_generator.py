import io
import csv
from datetime import datetime
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

class ReportGenerator:
    @staticmethod
    def generate_csv(project_name: str, assessment_data: Dict[str, Any]) -> str:
        """Generate structured CSV audit report."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header info
        writer.writerow(["TechDebt AI - Technology Debt Audit Report"])
        writer.writerow(["Project Name", project_name])
        writer.writerow(["Generated Date", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")])
        writer.writerow(["Overall Health Score", assessment_data.get("overall_health_score", "N/A")])
        writer.writerow(["Risk Classification", assessment_data.get("risk_classification", "N/A")])
        writer.writerow([])

        # Technology Details Header
        writer.writerow([
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
        ])

        for s in assessment_data.get("scores", []):
            writer.writerow([
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
            ])

        writer.writerow([])
        writer.writerow(["Active Risk Findings"])
        writer.writerow(["Severity", "Technology", "Risk Title", "Status", "Business Impact", "Technical Impact"])
        
        for r in assessment_data.get("risks", []):
            writer.writerow([
                r.get("severity", ""),
                r.get("technology_name", ""),
                r.get("title", ""),
                r.get("status", "Open"),
                r.get("business_impact", ""),
                r.get("technical_impact", "")
            ])

        return output.getvalue()

    @staticmethod
    def generate_pdf(project_name: str, assessment_data: Dict[str, Any]) -> bytes:
        """Generate executive-level PDF report using ReportLab."""
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
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=14,
            spaceAfter=8
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
        elements.append(Paragraph("TechDebt AI — Executive Technology Debt Report", title_style))
        elements.append(Paragraph(
            f"<b>Project:</b> {project_name} | <b>Date:</b> {datetime.utcnow().strftime('%B %d, %Y')} | <b>Confidence:</b> {assessment_data.get('confidence_level', 'High')}",
            subtitle_style
        ))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#e2e8f0"), spaceAfter=14))

        # Executive Summary Box
        score = assessment_data.get("overall_health_score", 100)
        risk_class = assessment_data.get("risk_classification", "Healthy")
        
        badge_color = colors.HexColor("#16a34a") if score >= 85 else (
            colors.HexColor("#2563eb") if score >= 70 else (
                colors.HexColor("#d97706") if score >= 50 else colors.HexColor("#dc2626")
            )
        )

        exec_summary_text = (
            f"<b>Executive Summary:</b> {project_name} received an overall Technology Health Score of "
            f"<b>{score}/100</b> ({risk_class}). "
            f"This evaluation encompasses {len(assessment_data.get('scores', []))} dependencies assessed against "
            f"active maintenance, security advisories, ecosystem compatibility, and version currency."
        )
        elements.append(Paragraph(exec_summary_text, body_style))
        elements.append(Spacer(1, 12))

        # Key Metrics Table
        metrics_data = [
            ["Health Score", "Risk Rating", "Dependencies Assessed", "Critical / High Risks"],
            [f"{score} / 100", risk_class, str(len(assessment_data.get('scores', []))), str(len(assessment_data.get('risks', [])))]
        ]
        metrics_table = Table(metrics_data, colWidths=[130, 130, 140, 140])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor("#334155")),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ]))
        elements.append(metrics_table)
        elements.append(Spacer(1, 14))

        # Technology Inventory Breakdown
        elements.append(Paragraph("Technology Inventory & Scores", heading2_style))
        tech_rows = [["Technology", "Installed", "Latest", "Score", "Rating", "Complexity", "Action"]]
        for s in assessment_data.get("scores", [])[:15]:
            tech_rows.append([
                s.get("technology_name", "")[:18],
                s.get("installed_version", "")[:10],
                s.get("latest_stable_version", "")[:10],
                str(s.get("overall_score", 0)),
                s.get("risk_classification", "")[:12],
                s.get("upgrade_complexity_level", "Low"),
                s.get("recommended_action", "")[:35] + ("..." if len(s.get("recommended_action", "")) > 35 else "")
            ])

        tech_table = Table(tech_rows, colWidths=[90, 60, 60, 45, 75, 65, 145])
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
        elements.append(Spacer(1, 14))

        # Identified Risks Section
        risks = assessment_data.get("risks", [])
        if risks:
            elements.append(Paragraph("Priority Risk Findings", heading2_style))
            risk_rows = [["Severity", "Finding Title", "Business Impact", "Recommended Next Step"]]
            for r in risks[:8]:
                risk_rows.append([
                    r.get("severity", "Medium"),
                    Paragraph(f"<b>{r.get('title', '')}</b>", body_style),
                    Paragraph(r.get("business_impact", "")[:120], body_style),
                    Paragraph(r.get("technical_impact", "")[:120], body_style)
                ])
            risk_table = Table(risk_rows, colWidths=[65, 140, 170, 165])
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

