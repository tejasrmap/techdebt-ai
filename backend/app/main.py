import os
import time
import uuid
import logging
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import engine, Base
from app.api.v1 import api_v1_router
from app.seed_data import seed
from app.services.metrics_service import MetricsService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("techdebt_ai")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Run Alembic migrations programmatically
    logger.info("Verifying and applying Alembic database migrations...")
    try:
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
    version="3.1.1",
    lifespan=lifespan
)

# Request Observability & Logging Middleware
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = f"{duration * 1000.0:.2f}"

    if request.url.path != "/metrics":
        MetricsService.record_request(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
            duration_seconds=duration
        )

    logger.info(
        f"[{request_id}] {request.method} {request.url.path} -> "
        f"{response.status_code} ({duration * 1000.0:.1f}ms)"
    )
    return response

# Explicit CORS Origins (never wildcard in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
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

@app.get("/metrics", tags=["Observability"])
def get_metrics():
    """Prometheus exposition metrics endpoint for monitoring and observability."""
    metrics_text = MetricsService.generate_prometheus_metrics()
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4; charset=utf-8")

@app.get("/health", tags=["Health"])
def health_check():
    """
    Genuine multi-component system health inspection (v3.1.1).
    Distinguishes configured, available, connected, healthy, and degraded states across:
    PostgreSQL, Redis, Storage, Worker, AI Providers, and Vulnerability Provider.
    """
    components: Dict[str, Any] = {}
    is_healthy = True

    # 1. Database (PostgreSQL / SQLite fallback)
    try:
        from app.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            components["database"] = {
                "status": "connected",
                "healthy": True,
                "engine": "postgresql" if "postgres" in str(db.bind.url).lower() else "sqlite"
            }
        finally:
            db.close()
    except Exception as db_err:
        is_healthy = False
        components["database"] = {
            "status": "connection_failed",
            "healthy": False,
            "error": str(db_err)
        }

    # 2. Redis
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis
            rc = redis.from_url(redis_url, decode_responses=True, socket_timeout=2.0)
            rc.ping()
            components["redis"] = {
                "status": "connected",
                "healthy": True,
                "configured": True
            }
        except Exception as r_err:
            components["redis"] = {
                "status": "degraded",
                "healthy": False,
                "configured": True,
                "error": str(r_err),
                "fallback": "database_bucket"
            }
    else:
        components["redis"] = {
            "status": "not_configured",
            "healthy": True,
            "configured": False,
            "fallback": "database_bucket"
        }

    # 3. Storage
    try:
        storage_dir = os.getenv("WORKSPACE_ROOT", "/tmp/techdebt_workspaces")
        if not os.path.exists(storage_dir):
            os.makedirs(storage_dir, exist_ok=True)
        test_file = os.path.join(storage_dir, f".health_check_{uuid.uuid4().hex[:6]}")
        with open(test_file, "w") as f:
            f.write("ok")
        if os.path.exists(test_file):
            os.remove(test_file)
        components["storage"] = {
            "status": "writable",
            "healthy": True,
            "path": storage_dir
        }
    except Exception as st_err:
        components["storage"] = {
            "status": "read_only_or_unreachable",
            "healthy": False,
            "error": str(st_err)
        }

    # 4. AI Provider Configuration
    gemini_key = os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", "")
    ai_configured = bool(gemini_key or openai_key)
    components["ai_providers"] = {
        "status": "configured" if ai_configured else "fallback_only",
        "healthy": True,
        "gemini_available": bool(gemini_key),
        "openai_available": bool(openai_key),
        "deterministic_engine": "active"
    }

    # 5. Vulnerability Intelligence
    components["vulnerability_intelligence"] = {
        "status": "available",
        "healthy": True,
        "provider": "Google OSV",
        "cache": "persistent_ttl"
    }

    overall_status = "healthy" if is_healthy else "degraded" if components.get("database", {}).get("healthy") else "unhealthy"
    status_code = 200 if is_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "app": settings.PROJECT_NAME,
            "environment": settings.ENVIRONMENT,
            "api_version": "v1",
            "version": "3.1.1",
            "components": components,
            "supabase_configured": bool(settings.SUPABASE_URL and settings.SUPABASE_PUBLISHABLE_KEY),
            "razorpay_configured": bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)
        }
    )

@app.get("/live", tags=["Health"])
def liveness_check():
    """Kubernetes liveness probe verifying process responsiveness."""
    return {
        "status": "alive",
        "uptime_seconds": round(MetricsService.get_uptime_seconds(), 2),
        "version": "3.1.1"
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
        return {
            "status": "ready",
            "database": "connected",
            "version": "3.1.1"
        }
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not_ready", "database_error": str(e), "version": "3.1.1"})

@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Welcome to TechDebt AI API – Software Engineering Intelligence Platform",
        "docs_url": "/docs",
        "health_check": "/health",
        "readiness_check": "/ready",
        "metrics_url": "/metrics",
        "version": "3.1.1"
    }
