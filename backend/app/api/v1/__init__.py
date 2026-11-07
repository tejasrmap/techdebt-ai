from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.projects import router as projects_router
from app.api.v1.technologies import router as technologies_router
from app.api.v1.assessments import router as assessments_router
from app.api.v1.risks import router as risks_router
from app.api.v1.intelligence import router as intelligence_router
from app.api.v1.reports import router as reports_router
from app.api.v1.scheduler import router as scheduler_router
from app.api.v1.settings import router as settings_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.repositories import router as repositories_router
from app.api.v1.billing import router as billing_router
from app.api.v1.teams import router as teams_router
from app.api.v1.code_findings import router as code_findings_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.system_admin import router as system_admin_router
from app.api.v1.remediations import router as remediations_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(projects_router)
api_v1_router.include_router(technologies_router)
api_v1_router.include_router(assessments_router)
api_v1_router.include_router(risks_router)
api_v1_router.include_router(intelligence_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(scheduler_router)
api_v1_router.include_router(settings_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(repositories_router)
api_v1_router.include_router(billing_router)
api_v1_router.include_router(teams_router)
api_v1_router.include_router(code_findings_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(organizations_router)
api_v1_router.include_router(system_admin_router)
api_v1_router.include_router(remediations_router)


