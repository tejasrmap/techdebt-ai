import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import engine, Base
from app.api.v1 import api_v1_router
from app.seed_data import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("techdebt_ai")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Run Alembic migrations programmatically
    logger.info("Verifying and applying Alembic database migrations...")
    try:
        import os
        from alembic.config import Config
        from alembic import command
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ini_path = os.path.join(base_dir, "alembic.ini")
        if os.path.exists(ini_path):
            alembic_cfg = Config(ini_path)
            alembic_cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))
            alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
            command.upgrade(alembic_cfg, "head")
            logger.info("Alembic schema migrations successfully applied to head.")
        else:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("CRITICAL: alembic.ini not found in production environment.")
            Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error(f"FATAL: Database migration failed: {e}")
        # Never fall back to Base.metadata.create_all() on migration failure; fail startup immediately
        raise RuntimeError(f"Application startup aborted: Alembic migrations failed: {e}") from e
    
    try:
        seed()
    except Exception as e:
        logger.warning(f"Seed step notice: {e}")

    # Note: In accordance with production architecture, APScheduler is NOT started
    # in the API web process. Background review scheduling is exclusively managed
    # by the dedicated worker process (app.worker) with atomic distributed locking.

    yield

    # Shutdown
    logger.info("Web API process shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="TechDebt AI – Commercial Software Engineering Intelligence and Technical Debt Platform.",
    version="2.0.0",
    lifespan=lifespan
)

# Explicit CORS Origins (never wildcard in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred.",
            "error_code": "INTERNAL_SERVER_ERROR"
        }
    )

# Include v1 API router
app.include_router(api_v1_router, prefix=settings.API_V1_STR)

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "app": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "api_version": "v1",
        "version": "2.0.0"
    }

@app.get("/ready", tags=["Health"])
def readiness_check():
    """Kubernetes/Container readiness probe verifying operational database connectivity."""
    try:
        from app.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "ready", "database": "connected", "version": "2.0.0"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not_ready", "database_error": str(e)})

@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Welcome to TechDebt AI API – Software Engineering Intelligence Platform",
        "docs_url": "/docs",
        "health_check": "/health",
        "readiness_check": "/ready",
        "version": "2.0.0"
    }
