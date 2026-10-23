import os
import logging
from datetime import datetime, timedelta
from app.config import settings
from app.database import SessionLocal, Base, engine
from app.models.all_models import (
    Organization, User, Project, Technology, ProjectTechnology,
    Assessment, TechnologyScore, RiskFinding, EvidenceSource, HistoricalAssessment, ScheduledReview
)
from app.services.auth_service import get_password_hash
from app.services.scheduler_service import validate_and_compute_next_run

logger = logging.getLogger(__name__)

def seed():
    # Phase 1 Requirement 11: Disable demo account seeding in production!
    if settings.ENVIRONMENT.lower() == "production" or not settings.ENABLE_DEMO_SEED:
        logger.info("Production environment detected or demo seeding disabled. Skipping demo account generation.")
        return

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Check if demo users already seeded
        if db.query(User).filter(User.email == "admin@techdebt.ai").first():
            db.close()
            return

        # 1. Organization
        org = db.query(Organization).filter(Organization.slug == "acme-cloud").first()
        if not org:
            org = Organization(name="Acme Cloud Engineering", slug="acme-cloud", plan="Enterprise")
            db.add(org)
            db.commit()
            db.refresh(org)

        # 2. Users (Demo credentials only for development/testing)
        admin = User(
            org_id=org.id,
            email="admin@techdebt.ai",
            full_name="Sarah Connor (CTO)",
            hashed_password=get_password_hash("AdminPass123!"),
            role="Administrator"
        )
        manager = User(
            org_id=org.id,
            email="manager@techdebt.ai",
            full_name="Alex Rivera (Lead Architect)",
            hashed_password=get_password_hash("ManagerPass123!"),
            role="Engineering Manager"
        )
        dev = User(
            org_id=org.id,
            email="dev@techdebt.ai",
            full_name="David Chen (Senior Engineer)",
            hashed_password=get_password_hash("DevPass123!"),
            role="Developer"
        )
        db.add_all([admin, manager, dev])
        db.commit()

        # 3. Technologies
        tech_data = [
            {"name": "react", "ecosystem": "npm", "category": "Framework", "latest": "19.0.0", "desc": "The library for web and native user interfaces", "dep": False},
            {"name": "moment", "ecosystem": "npm", "category": "Library", "latest": "2.30.1", "desc": "Parse, validate, manipulate, and display dates and times in JS (Maintenance only)", "dep": True},
            {"name": "lodash", "ecosystem": "npm", "category": "Library", "latest": "4.17.21", "desc": "Lodash modular utilities", "dep": False},
            {"name": "axios", "ecosystem": "npm", "category": "Library", "latest": "1.7.9", "desc": "Promise based HTTP client for the browser and node.js", "dep": False},
            {"name": "fastapi", "ecosystem": "pypi", "category": "Framework", "latest": "0.115.6", "desc": "FastAPI framework, high performance, easy to learn, fast to code", "dep": False},
            {"name": "sqlalchemy", "ecosystem": "pypi", "category": "ORM", "latest": "2.0.36", "desc": "Database Abstraction Library for Python", "dep": False},
            {"name": "pydantic", "ecosystem": "pypi", "category": "Library", "latest": "2.10.4", "desc": "Data validation using Python type hints", "dep": False},
            {"name": "cryptography", "ecosystem": "pypi", "category": "Security", "latest": "44.0.0", "desc": "Cryptographic recipes and primitives", "dep": False},
        ]
        tech_map = {}
        for td in tech_data:
            t = db.query(Technology).filter(Technology.name == td["name"]).first()
            if not t:
                t = Technology(
                    name=td["name"],
                    ecosystem=td["ecosystem"],
                    category=td["category"],
                    latest_stable_version=td["latest"],
                    description=td["desc"],
                    is_deprecated=td["dep"]
                )
                db.add(t)
                db.commit()
                db.refresh(t)
            tech_map[td["name"]] = t

        # 4. Projects
        p1 = db.query(Project).filter(Project.org_id == org.id, Project.name == "Customer Web Portal").first()
        if not p1:
            p1 = Project(
                org_id=org.id,
                name="Customer Web Portal",
                description="Core customer-facing portal and self-service account dashboard.",
                repository_url="https://github.com/acme/customer-web-portal",
                languages=["TypeScript", "JavaScript"],
                frameworks=["React", "TailwindCSS"],
                owner_name="Frontend Squad",
                last_assessment_date=datetime.utcnow() - timedelta(days=2)
            )
            db.add(p1)
            db.commit()
            db.refresh(p1)

        p2 = db.query(Project).filter(Project.org_id == org.id, Project.name == "Payment Gateway Service").first()
        if not p2:
            p2 = Project(
                org_id=org.id,
                name="Payment Gateway Service",
                description="PCI-DSS compliant payment processing and billing orchestration microservice.",
                repository_url="https://github.com/acme/payment-service",
                languages=["Python"],
                frameworks=["FastAPI", "SQLAlchemy"],
                owner_name="Fintech Platform Squad",
                last_assessment_date=datetime.utcnow() - timedelta(days=1)
            )
            db.add(p2)
            db.commit()
            db.refresh(p2)

        # 5. Project Technologies
        if not db.query(ProjectTechnology).filter(ProjectTechnology.project_id == p1.id).first():
            pt1 = ProjectTechnology(project_id=p1.id, technology_id=tech_map["react"].id, installed_version="18.2.0", file_source="package.json")
            pt2 = ProjectTechnology(project_id=p1.id, technology_id=tech_map["moment"].id, installed_version="2.24.0", file_source="package.json")
            pt3 = ProjectTechnology(project_id=p1.id, technology_id=tech_map["lodash"].id, installed_version="4.17.15", file_source="package.json")
            pt4 = ProjectTechnology(project_id=p1.id, technology_id=tech_map["axios"].id, installed_version="0.27.2", file_source="package.json")

            pt5 = ProjectTechnology(project_id=p2.id, technology_id=tech_map["fastapi"].id, installed_version="0.100.0", file_source="requirements.txt")
            pt6 = ProjectTechnology(project_id=p2.id, technology_id=tech_map["sqlalchemy"].id, installed_version="1.4.45", file_source="requirements.txt")
            pt7 = ProjectTechnology(project_id=p2.id, technology_id=tech_map["pydantic"].id, installed_version="1.10.12", file_source="requirements.txt")
            pt8 = ProjectTechnology(project_id=p2.id, technology_id=tech_map["cryptography"].id, installed_version="38.0.4", file_source="requirements.txt")
            db.add_all([pt1, pt2, pt3, pt4, pt5, pt6, pt7, pt8])
            db.commit()

        # 6. Baseline Assessment
        if not db.query(Assessment).filter(Assessment.project_id == p1.id).first():
            a1 = Assessment(
                project_id=p1.id,
                trigger_type="manual",
                status="completed",
                overall_health_score=68.5,
                risk_classification="Needs Attention",
                confidence_level="High",
                summary="Customer Web Portal evaluated. Moment.js is in legacy maintenance mode; Lodash 4.17.15 has prototype pollution advisory.",
                created_at=datetime.utcnow() - timedelta(days=2)
            )
            db.add(a1)
            db.commit()
            db.refresh(a1)

            s_react = TechnologyScore(
                assessment_id=a1.id, technology_id=tech_map["react"].id, overall_score=88.0, risk_classification="Healthy",
                maintenance_health=95.0, security_exposure=95.0, version_currency=80.0, community_activity=95.0,
                documentation_quality=95.0, ecosystem_compatibility=95.0, sustainability=90.0, upgrade_complexity=80.0,
                recommended_action="Plan upgrade from React 18 to React 19.",
                notes="Active LTS branch."
            )
            s_moment = TechnologyScore(
                assessment_id=a1.id, technology_id=tech_map["moment"].id, overall_score=38.0, risk_classification="High Risk",
                maintenance_health=25.0, security_exposure=75.0, version_currency=40.0, community_activity=30.0,
                documentation_quality=70.0, ecosystem_compatibility=40.0, sustainability=20.0, upgrade_complexity=45.0,
                upgrade_complexity_level="High",
                recommended_action="Migrate to modern date-fns or native Temporal / Intl APIs.",
                notes="Official maintainers declare project in legacy maintenance mode."
            )
            db.add_all([s_react, s_moment])

            # Risks
            r1 = RiskFinding(
                assessment_id=a1.id, technology_id=tech_map["moment"].id, project_id=p1.id,
                severity="High", title="Moment.js Legacy Maintenance Deprecation",
                description="Moment.js is officially in maintenance mode.",
                business_impact="Increases client bundle size and lacks modern ECMAScript Temporal support.",
                technical_impact="Accumulation of obsolete mutable date APIs.",
                status="Open", assigned_to=dev.id
            )
            db.add(r1)

            # Historical Assessment
            h1 = HistoricalAssessment(
                project_id=p1.id, assessment_id=a1.id, health_score=68.5, score_delta=0.0,
                risk_classification="Needs Attention",
                summary_of_changes="Baseline assessment created with 1 open risk.",
                new_risks_count=1, resolved_risks_count=0,
                snapshot_data={"project_id": p1.id, "project_name": p1.name, "overall_health_score": 68.5},
                created_at=datetime.utcnow() - timedelta(days=2)
            )
            db.add(h1)

            # 7. Scheduled Review
            sch1 = ScheduledReview(
                project_id=p1.id, frequency="Weekly", cron_expression="0 0 * * 1",
                is_active=True, next_run_at=validate_and_compute_next_run("0 0 * * 1")
            )
            db.add(sch1)
            db.commit()
        logger.info("Demo data successfully seeded for development.")
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed()
