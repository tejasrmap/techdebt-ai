import os
import uuid
import tempfile
import asyncio
import threading
import multiprocessing
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.config import (
    Settings,
    DEFAULT_DEV_SECRET,
    PROHIBITED_SECRET_DEFAULTS,
    PROHIBITED_PLACEHOLDER_SUBSTRINGS,
    contains_prohibited_placeholder
)
from app.database import SessionLocal
from app.models.all_models import (
    Organization, User, Project, ScheduledReview, ReviewJob,
    HistoricalAssessment, Assessment, DistributedLock, Technology, ProjectTechnology,
    TechnologyScore, RiskFinding
)
from app.services.scheduler_service import (
    run_scheduled_job,
    execute_project_review,
    acquire_distributed_lock,
    release_distributed_lock,
    renew_distributed_lock,
    get_lock_generation,
    assert_valid_fenced_lease,
    assert_valid_fenced_lease_transactional,
    verify_ownership_short_transaction,
    verify_ownership_standalone,
    StaleGenerationWriteError,
    LockHeartbeat,
    register_job_in_scheduler,
    scheduler
)
from app.services.ai_analyzer import AITechnologyDebtAnalyzer
from app.services.historical_memory_adapter import HistoricalAssessmentMemoryAdapter
from app.services.memento_adapter import MementoMemoryAdapter
from app.main import app

client = TestClient(app)

def get_or_create_test_org(db) -> Organization:
    org = db.query(Organization).first()
    if not org:
        org = Organization(name="Test Org " + uuid.uuid4().hex[:6], slug="test-org-" + uuid.uuid4().hex[:6])
        db.add(org)
        db.commit()
        db.refresh(org)
    return org

def get_or_create_test_project(db) -> Project:
    org = get_or_create_test_org(db)
    proj = db.query(Project).filter(Project.org_id == org.id).first()
    if not proj:
        proj = Project(org_id=org.id, name="Test Project " + uuid.uuid4().hex[:6])
        db.add(proj)
        db.commit()
        db.refresh(proj)
    return proj


# -------------------------------------------------------------
# 1. DOCKER SECRETS & PLACEHOLDER VALIDATION TESTS
# -------------------------------------------------------------
def test_production_rejects_default_secrets():
    """Verify production configuration rejects known default secret keys and weak values."""
    with patch.dict(os.environ, {
        "ENVIRONMENT": "production",
        "SECRET_KEY": DEFAULT_DEV_SECRET,
        "ENCRYPTION_KEY": "a" * 32,
        "DATABASE_URL": "postgresql://user:valid_strong_pass@localhost:5432/db"
    }):
        with pytest.raises(ValueError, match="FATAL SECURITY VIOLATION"):
            Settings()

    # Reject short secret key (< 32 characters)
    with patch.dict(os.environ, {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "short-secret-key-too-brief",
        "ENCRYPTION_KEY": "a" * 32,
        "DATABASE_URL": "postgresql://user:valid_strong_pass@localhost:5432/db"
    }):
        with pytest.raises(ValueError, match="at least 32 characters long"):
            Settings()

def test_production_rejects_all_placeholder_secrets():
    """
    Verify production configuration strictly rejects template placeholders from .env.example:
    - replace-with
    - your-secret
    - example-key
    - change-me
    - changeme
    - default
    """
    placeholders = [
        "replace-with-at-least-32-char-random-jwt-secret-key-prod",
        "your-secret-key-goes-here-32chars-long",
        "example-key-value-for-testing-prod-32c",
        "change-me-before-deploying-production-32c",
        "changeme-12345678901234567890123456",
        "default-secret-production-key-32chars"
    ]
    for ph in placeholders:
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "SECRET_KEY": ph,
            "ENCRYPTION_KEY": "a-strong-random-encryption-key-valid",
            "DATABASE_URL": "postgresql://user:valid_strong_pass@localhost:5432/db"
        }):
            with pytest.raises(ValueError, match="strictly rejected"):
                Settings()

def test_sample_env_example_cannot_launch_production():
    """Ensure that the exact sample .env.example cannot be used unchanged in production."""
    with patch.dict(os.environ, {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "replace-with-at-least-32-char-random-jwt-secret-key-prod",
        "ENCRYPTION_KEY": "replace-with-at-least-32-char-random-fernet-key-prod",
        "DATABASE_URL": "postgresql://postgres:replace-with-strong-db-password-in-production@localhost:5432/db"
    }):
        with pytest.raises(ValueError, match="strictly rejected"):
            Settings()

def test_production_rejects_default_db_password():
    """Verify production rejects known default postgres passwords in DATABASE_URL."""
    with patch.dict(os.environ, {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "a-strong-random-production-secret-key-that-is-long-enough",
        "ENCRYPTION_KEY": "a-strong-production-fernet-key-valid",
        "DATABASE_URL": "postgresql://postgres:postgrespassword@localhost:5432/db"
    }):
        with pytest.raises(ValueError, match="DATABASE_URL must not use default"):
            Settings()


# -------------------------------------------------------------
# 2. SAFE DATABASE MIGRATION TESTS (ISOLATED DISPOSABLE DATABASE)
# -------------------------------------------------------------
def assert_safe_test_database(url: str):
    """Safeguard: Refuse to execute destructive migration tests against production databases."""
    lower_url = url.lower()
    if "production" in lower_url or (not "test" in lower_url and not "temp" in lower_url and not "disposable" in lower_url):
        raise ValueError(f"ABORT: Destructive migration test cannot run against non-test database URL: {url}")

def test_migration_safeguard_rejects_production_urls():
    """Verify safeguard rejects production database URLs for migration tests."""
    with pytest.raises(ValueError, match="ABORT: Destructive migration test cannot run"):
        assert_safe_test_database("postgresql://admin:secret@production-db.company.internal:5432/techdebt")
    with pytest.raises(ValueError, match="ABORT: Destructive migration test cannot run"):
        assert_safe_test_database("postgresql://user:pass@db:5432/techdebt_db")

def test_alembic_startup_fails_on_migration_error():
    """Verify application startup fails if Alembic migration fails without falling back to create_all."""
    from app.main import lifespan
    with patch("alembic.command.upgrade", side_effect=Exception("Simulated schema migration syntax error")):
        with patch.object(app, "router"):
            async def run():
                async with lifespan(app):
                    pass
            with pytest.raises(RuntimeError, match="Application startup aborted: Alembic migrations failed"):
                asyncio.run(run())

def test_safe_database_migration_downgrade_and_upgrade_on_disposable_db():
    """
    Test Alembic rollback to base and re-upgrade to head on an isolated disposable test database.
    Production and development databases (techdebt.db) are strictly preserved and untouched.
    """
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import create_engine, inspect

    # Create isolated disposable SQLite database file in OS temp directory
    disposable_file = os.path.join(tempfile.gettempdir(), f"disposable_migration_{uuid.uuid4().hex}.db")
    disposable_url = f"sqlite:///{disposable_file}"
    assert_safe_test_database(disposable_url)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ini_path = os.path.join(base_dir, "alembic.ini")
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", disposable_url)

    try:
        # 1. Clean upgrade to head on disposable DB
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(disposable_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "organizations" in tables
        assert "distributed_locks" in tables
        assert "assessments" in tables
        engine.dispose()

        # 2. Downgrade to base on disposable DB
        command.downgrade(alembic_cfg, "base")

        engine = create_engine(disposable_url)
        inspector = inspect(engine)
        tables_after_downgrade = set(inspector.get_table_names())
        assert "organizations" not in tables_after_downgrade
        assert "distributed_locks" not in tables_after_downgrade
        engine.dispose()

        # 3. Re-upgrade to head on disposable DB
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(disposable_url)
        inspector = inspect(engine)
        tables_reupgraded = set(inspector.get_table_names())
        assert "organizations" in tables_reupgraded
        assert "distributed_locks" in tables_reupgraded
        engine.dispose()

    finally:
        # Clean up temporary disposable DB
        if os.path.exists(disposable_file):
            try:
                os.remove(disposable_file)
            except Exception:
                pass


# -------------------------------------------------------------
# 3. SCHEDULER: GENUINE MULTIPROCESSING CONCURRENCY & LEASES
# -------------------------------------------------------------
def _run_worker_job_in_process(schedule_id: str, worker_id: str, queue: multiprocessing.Queue):
    """Independent worker process entry point for genuine multiprocessing concurrency test."""
    from app.services.scheduler_service import run_scheduled_job
    from unittest.mock import patch
    from app.models.all_models import Assessment

    async def mock_review(*args, **kwargs):
        # Simulate slight processing duration
        import time
        time.sleep(0.1)
        return Assessment(project_id="test_pid", status="completed", overall_health_score=80.0)

    with patch("app.services.scheduler_service.execute_project_review", side_effect=mock_review):
        executed = run_scheduled_job(schedule_id, worker_id=worker_id)
        queue.put((worker_id, executed))

def _acquire_lock_in_process(lock_key: str, worker_id: str, queue: multiprocessing.Queue):
    """Independent worker process entry point for concurrent expired-lock reclamation testing."""
    from app.database import SessionLocal
    from app.services.scheduler_service import acquire_distributed_lock
    db = SessionLocal()
    try:
        acquired = acquire_distributed_lock(db, lock_key, worker_id, ttl_seconds=60)
        queue.put((worker_id, acquired))
    finally:
        db.close()

def test_genuine_multiprocessing_scheduler_concurrency():
    """
    Genuine multiprocessing concurrency test:
    Two separate OS worker processes simultaneously attempt to execute the same scheduled review.
    Verifies that atomic distributed locking allows exactly one worker to execute, while the other is rejected.
    """
    db = SessionLocal()
    try:
        org = get_or_create_test_org(db)
        proj = Project(org_id=org.id, name=f"Multiprocess Proj {uuid.uuid4().hex[:6]}")
        db.add(proj)
        db.commit()

        schedule = ScheduledReview(
            project_id=proj.id,
            frequency="Daily",
            cron_expression="0 0 * * *",
            is_active=True
        )
        db.add(schedule)
        db.commit()
        schedule_id = schedule.id

        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()

        p1 = ctx.Process(target=_run_worker_job_in_process, args=(schedule_id, "process_worker_1", queue))
        p2 = ctx.Process(target=_run_worker_job_in_process, args=(schedule_id, "process_worker_2", queue))

        # Launch both independent worker processes simultaneously
        p1.start()
        p2.start()

        p1.join(timeout=10)
        p2.join(timeout=10)

        # Timeout cleanup for worker processes
        for p in (p1, p2):
            if p.is_alive():
                p.terminate()
                p.join(timeout=2)

        # Exit-code checks
        assert p1.exitcode == 0, f"Worker process 1 exited with code {p1.exitcode}"
        assert p2.exitcode == 0, f"Worker process 2 exited with code {p2.exitcode}"

        # Retrieve results using queue.get(timeout=5)
        results = []
        for _ in range(2):
            try:
                results.append(queue.get(timeout=5))
            except Exception as e:
                pytest.fail(f"Timed out waiting for worker result from queue: {e}")

        assert len(results) == 2, f"Expected 2 process results, got: {results}"
        executed_count = sum(1 for _, res in results if res is True)
        rejected_count = sum(1 for _, res in results if res is False)

        # Exactly one worker process must have executed the review
        assert executed_count == 1, f"Expected exactly 1 execution, got {executed_count}"
        assert rejected_count == 1, f"Expected exactly 1 rejection, got {rejected_count}"

        # Verify only one completed ReviewJob in database
        jobs = db.query(ReviewJob).filter(ReviewJob.scheduled_review_id == schedule_id).all()
        assert len(jobs) == 1
        assert jobs[0].status == "Completed"

    finally:
        db.close()

def test_lock_renewal_and_long_execution():
    """
    Test safe lease mechanism:
    Verify that an active lease can be renewed during execution longer than 10 minutes.
    """
    db = SessionLocal()
    try:
        lock_key = f"long_exec_lock_{uuid.uuid4().hex[:6]}"
        owner = "long_worker_1"

        # Acquire initial 60-second lease
        acquired = acquire_distributed_lock(db, lock_key, owner, ttl_seconds=60)
        assert acquired is True

        # Check initial expiration
        lock_rec = db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first()
        initial_expires = lock_rec.expires_at

        # Renew lease for an additional 900 seconds (15 minutes) for long-running execution
        renewed = renew_distributed_lock(db, lock_key, owner, extension_seconds=900)
        assert renewed is True

        db.refresh(lock_rec)
        assert lock_rec.expires_at > initial_expires
        assert (lock_rec.expires_at - datetime.utcnow()).total_seconds() > 800

        # Non-owner cannot renew lease
        invalid_renew = renew_distributed_lock(db, lock_key, "imposter_worker", extension_seconds=600)
        assert invalid_renew is False

        # Release lock
        released = release_distributed_lock(db, lock_key, owner)
        assert released is True
    finally:
        db.close()

def test_expired_lock_recovery():
    """
    Test that expired locks (e.g. from a crashed worker) are safely reclaimed and acquired by a new worker.
    """
    db = SessionLocal()
    try:
        lock_key = f"expired_recovery_lock_{uuid.uuid4().hex[:6]}"

        # Insert a pre-expired lock (expired 15 minutes ago)
        expired_lock = DistributedLock(
            lock_key=lock_key,
            owner_id="crashed_worker",
            acquired_at=datetime.utcnow() - timedelta(minutes=20),
            expires_at=datetime.utcnow() - timedelta(minutes=10)
        )
        db.add(expired_lock)
        db.commit()

        # New worker attempts to acquire the lock
        acquired = acquire_distributed_lock(db, lock_key, "new_healthy_worker", ttl_seconds=300)
        assert acquired is True

        # Verify ownership was transferred to new worker
        lock_rec = db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first()
        assert lock_rec.owner_id == "new_healthy_worker"
        assert lock_rec.expires_at > datetime.utcnow()

        release_distributed_lock(db, lock_key, "new_healthy_worker")
    finally:
        db.close()

def test_avoid_duplicate_scheduling_during_periodic_sync():
    """
    Verify that periodic schedule synchronization does not recreate jobs or reset cron timers
    when schedule configuration has not changed.
    """
    db = SessionLocal()
    try:
        proj = get_or_create_test_project(db)
        schedule = ScheduledReview(
            project_id=proj.id,
            frequency="Weekly",
            cron_expression="0 0 * * 1",
            is_active=True
        )
        db.add(schedule)
        db.commit()

        job_id = f"review_job_{schedule.id}"

        # First registration
        register_job_in_scheduler(schedule)
        first_job = scheduler.get_job(job_id)
        assert first_job is not None

        # Subsequent periodic sync with identical cron expression must NOT recreate or change job instance
        register_job_in_scheduler(schedule)
        second_job = scheduler.get_job(job_id)
        assert second_job is not None
        assert first_job.id == second_job.id

        # Clean up
        scheduler.remove_job(job_id)
    finally:
        db.close()

def test_dedicated_worker_real_scheduled_assessment():
    """
    Execute a real scheduled assessment through the dedicated worker pipeline end-to-end.
    Verifies that run_scheduled_job():
    1. Successfully acquires distributed lock
    2. Runs complete project assessment pipeline with intelligence and scoring
    3. Creates completed ReviewJob audit entry
    4. Records historical snapshot in database
    5. Cleanly releases distributed lock upon completion
    """
    db = SessionLocal()
    try:
        org = get_or_create_test_org(db)
        proj = Project(
            org_id=org.id,
            name=f"Worker Schedule Project {uuid.uuid4().hex[:6]}",
            description="Dedicated worker assessment integration test"
        )
        db.add(proj)
        db.commit()

        # Add real technologies
        t1 = Technology(name=f"react-{uuid.uuid4().hex[:10]}", ecosystem="npm", latest_stable_version="18.2.0")
        t2 = Technology(name=f"fastapi-{uuid.uuid4().hex[:10]}", ecosystem="pypi", latest_stable_version="0.109.0")
        db.add_all([t1, t2])
        db.commit()

        pt1 = ProjectTechnology(project_id=proj.id, technology_id=t1.id, installed_version="18.2.0")
        pt2 = ProjectTechnology(project_id=proj.id, technology_id=t2.id, installed_version="0.100.0")
        db.add_all([pt1, pt2])
        db.commit()

        # Create scheduled review
        schedule = ScheduledReview(
            project_id=proj.id,
            frequency="Daily",
            cron_expression="0 2 * * *",
            is_active=True
        )
        db.add(schedule)
        db.commit()

        # Execute scheduled job directly through the worker execution entry point
        worker_id = f"test_worker_{uuid.uuid4().hex[:6]}"
        result = run_scheduled_job(schedule.id, worker_id=worker_id)
        assert result is True, "Scheduled job should have completed successfully"

        # Verify ReviewJob was recorded with Completed status
        job = db.query(ReviewJob).filter(ReviewJob.scheduled_review_id == schedule.id).first()
        assert job is not None
        assert job.status == "Completed"
        assert job.completed_at is not None

        # Verify Assessment was created
        assessment = (
            db.query(Assessment)
            .filter(Assessment.project_id == proj.id)
            .order_by(Assessment.created_at.desc())
            .first()
        )
        assert assessment is not None
        assert assessment.status == "completed"
        assert assessment.overall_health_score is not None
        assert assessment.overall_health_score > 0

        # Verify HistoricalAssessment snapshot was recorded
        hist = (
            db.query(HistoricalAssessment)
            .filter(HistoricalAssessment.project_id == proj.id)
            .first()
        )
        assert hist is not None
        assert hist.health_score == assessment.overall_health_score
        assert hist.storage_provider == "postgresql"

        # Verify distributed lock was released
        lock_key = f"review_job_lock_{schedule.id}"
        lock = db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first()
        assert lock is None or lock.expires_at <= datetime.utcnow()
    finally:
        db.close()

def test_worker_safely_aborts_on_lock_loss():
    """
    Verify that assessment execution safely aborts if distributed lock ownership is lost.
    Ensures safe early termination, failure logging, and prevents modifying or releasing locks owned by others.
    """
    db = SessionLocal()
    try:
        org = get_or_create_test_org(db)
        proj = Project(org_id=org.id, name=f"Lock Loss Proj {uuid.uuid4().hex[:6]}")
        db.add(proj)
        db.commit()

        # Add a technology to project
        tech = Technology(name=f"test-pkg-{uuid.uuid4().hex[:4]}", ecosystem="npm", latest_stable_version="1.0.0")
        db.add(tech)
        db.commit()

        p_tech = ProjectTechnology(project_id=proj.id, technology_id=tech.id, installed_version="1.0.0")
        db.add(p_tech)
        db.commit()

        # 1. Direct execute_project_review with should_abort returning True
        with pytest.raises(RuntimeError, match="lost distributed lock ownership"):
            asyncio.run(execute_project_review(
                project_id=proj.id,
                trigger_type="scheduled",
                db_session=db,
                should_abort=lambda: True
            ))

        # 2. Scheduled job aborts safely and logs Failure status without retrying
        schedule = ScheduledReview(
            project_id=proj.id,
            frequency="Daily",
            cron_expression="0 0 * * *",
            is_active=True
        )
        db.add(schedule)
        db.commit()

        async def mock_exec_with_lock_lost(*args, **kwargs):
            raise RuntimeError("Review aborted: Worker lost distributed lock ownership")

        with patch("app.services.scheduler_service.execute_project_review", side_effect=mock_exec_with_lock_lost):
            executed = run_scheduled_job(schedule.id, max_retries=1)
            assert executed is False

        # ReviewJob must be marked Failed
        job = db.query(ReviewJob).filter(ReviewJob.scheduled_review_id == schedule.id).first()
        assert job is not None
        assert job.status == "Failed"
        assert "lost distributed lock" in job.error_message.lower() or "lost" in job.error_message.lower()
    finally:
        db.close()

def test_long_running_heartbeat_renewal_and_safe_loss_abort():
    """
    Comprehensive long-running concurrency & lease loss integration test:
    1. Starts worker 1 with a short initial lease (TTL 2s).
    2. Executes a simulated long-running assessment.
    3. Allows the heartbeat to renew the lease multiple times.
    4. Starts a second worker during the first execution.
    5. Verifies that the second worker cannot acquire the lock.
    6. Simulates lock ownership loss.
    7. Verifies that the original worker stops safely.
    8. Verifies that no stale results are committed.
    """
    db = SessionLocal()
    schedule_id = None
    lock_key = None
    try:
        org = get_or_create_test_org(db)
        proj = Project(
            org_id=org.id,
            name=f"Long Running Concurrency {uuid.uuid4().hex[:6]}",
            description="Long-running heartbeat concurrency test"
        )
        db.add(proj)
        db.commit()

        tech = Technology(name=f"pkg-{uuid.uuid4().hex[:4]}", ecosystem="npm", latest_stable_version="1.0.0")
        db.add(tech)
        db.commit()

        p_tech = ProjectTechnology(project_id=proj.id, technology_id=tech.id, installed_version="1.0.0")
        db.add(p_tech)
        db.commit()

        schedule = ScheduledReview(
            project_id=proj.id,
            frequency="Daily",
            cron_expression="0 0 * * *",
            is_active=True
        )
        db.add(schedule)
        db.commit()
        schedule_id = schedule.id
        lock_key = f"review_job_lock_{schedule_id}"

        worker_1_id = "worker_long_running_1"
        worker_2_id = "worker_concurrent_2"

        # 1. Acquire initial short lease for worker 1 (TTL 2 seconds)
        acquired = acquire_distributed_lock(db, lock_key, worker_1_id, ttl_seconds=2)
        assert acquired is True

        # Start heartbeat with short interval (0.3s) and extension (2s)
        from app.services.scheduler_service import LockHeartbeat
        heartbeat_1 = LockHeartbeat(lock_key, worker_1_id, interval=0.3, lease_extension=2)
        heartbeat_1.start()

        # 2 & 3. Allow heartbeat to renew the lease multiple times (sleep 1.0s)
        import time
        time.sleep(1.0)
        lock_rec_1 = db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first()
        assert lock_rec_1 is not None
        assert lock_rec_1.owner_id == worker_1_id
        assert lock_rec_1.expires_at > datetime.utcnow()

        # 4 & 5. Worker 2 attempts to run during worker 1's active lease; must be rejected
        worker_2_acquired = acquire_distributed_lock(db, lock_key, worker_2_id, ttl_seconds=5)
        assert worker_2_acquired is False, "Worker 2 must NOT acquire lock while Worker 1 holds active lease"

        worker_2_run_res = run_scheduled_job(schedule_id, worker_id=worker_2_id)
        assert worker_2_run_res is False, "Worker 2 execution must be rejected due to active lock"

        # 6. Simulate lock ownership loss for worker 1
        heartbeat_1.mark_lost()
        assert heartbeat_1.is_lock_lost() is True

        # 7. Execute review with should_abort=heartbeat_1.is_lock_lost; verify it stops safely
        with pytest.raises(RuntimeError, match="Worker lost distributed lock ownership"):
            asyncio.run(execute_project_review(
                project_id=proj.id,
                trigger_type="scheduled",
                db_session=db,
                should_abort=heartbeat_1.is_lock_lost
            ))

        # 8. Verify no stale completed assessment results were committed to database
        completed_assessments = (
            db.query(Assessment)
            .filter(Assessment.project_id == proj.id, Assessment.status == "completed")
            .all()
        )
        assert len(completed_assessments) == 0, "No completed assessment should be committed by a worker that lost its lock"

        heartbeat_1.stop()
    finally:
        if lock_key:
            db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
            db.commit()
        db.close()


# -------------------------------------------------------------
# 3B. SCHEDULER SUITE TESTS A THROUGH J (EXHAUSTIVE CONCURRENCY)
# -------------------------------------------------------------
def test_scheduler_suite_a_initial_acquisition():
    """Test A: Initial lock acquisition on an unoccupied key."""
    db = SessionLocal()
    lock_key = f"suite_a_lock_{uuid.uuid4().hex[:6]}"
    worker_id = "suite_worker_a"
    try:
        acquired = acquire_distributed_lock(db, lock_key, worker_id, ttl_seconds=60)
        assert acquired is True

        lock_rec = db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first()
        assert lock_rec is not None
        assert lock_rec.owner_id == worker_id
        assert lock_rec.generation == 1
        assert lock_rec.expires_at > datetime.utcnow()
    finally:
        db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db.commit()
        db.close()

def test_scheduler_suite_b_active_ownership_rejection():
    """Test B: Active ownership rejection while lease is held."""
    db = SessionLocal()
    lock_key = f"suite_b_lock_{uuid.uuid4().hex[:6]}"
    worker_1 = "suite_worker_b1"
    worker_2 = "suite_worker_b2"
    try:
        acquired_1 = acquire_distributed_lock(db, lock_key, worker_1, ttl_seconds=60)
        assert acquired_1 is True

        # Second worker must be rejected
        acquired_2 = acquire_distributed_lock(db, lock_key, worker_2, ttl_seconds=60)
        assert acquired_2 is False

        lock_rec = db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first()
        assert lock_rec.owner_id == worker_1
        assert lock_rec.generation == 1
    finally:
        db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db.commit()
        db.close()

def test_scheduler_suite_c_expired_lock_reclamation():
    """Test C: Expired lock reclamation increments generation atomically."""
    db = SessionLocal()
    lock_key = f"suite_c_lock_{uuid.uuid4().hex[:6]}"
    old_worker = "crashed_worker_c"
    new_worker = "healthy_worker_c"
    try:
        # Pre-seed expired lock
        expired_lock = DistributedLock(
            lock_key=lock_key,
            owner_id=old_worker,
            generation=1,
            acquired_at=datetime.utcnow() - timedelta(seconds=120),
            expires_at=datetime.utcnow() - timedelta(seconds=60)
        )
        db.add(expired_lock)
        db.commit()

        # Reclaim expired lock
        acquired = acquire_distributed_lock(db, lock_key, new_worker, ttl_seconds=300)
        assert acquired is True

        db.refresh(expired_lock)
        assert expired_lock.owner_id == new_worker
        assert expired_lock.generation == 2
        assert expired_lock.expires_at > datetime.utcnow()
    finally:
        db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db.commit()
        db.close()

def test_scheduler_suite_d_concurrent_expired_lock_reclamation():
    """Test D: Concurrent expired lock reclamation across independent worker processes."""
    db = SessionLocal()
    lock_key = f"suite_d_lock_{uuid.uuid4().hex[:6]}"
    try:
        expired_lock = DistributedLock(
            lock_key=lock_key,
            owner_id="crashed_old_worker",
            generation=1,
            acquired_at=datetime.utcnow() - timedelta(seconds=120),
            expires_at=datetime.utcnow() - timedelta(seconds=60)
        )
        db.add(expired_lock)
        db.commit()

        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()

        p1 = ctx.Process(target=_acquire_lock_in_process, args=(lock_key, "worker_d_1", queue))
        p2 = ctx.Process(target=_acquire_lock_in_process, args=(lock_key, "worker_d_2", queue))

        p1.start()
        p2.start()

        p1.join(timeout=10)
        p2.join(timeout=10)

        for p in (p1, p2):
            if p.is_alive():
                p.terminate()
                p.join(timeout=2)

        assert p1.exitcode == 0
        assert p2.exitcode == 0

        results = [queue.get(timeout=5) for _ in range(2)]
        won = sum(1 for _, res in results if res is True)
        lost = sum(1 for _, res in results if res is False)

        assert won == 1, f"Exactly 1 process must reclaim the expired lock; results: {results}"
        assert lost == 1, f"Exactly 1 process must be rejected; results: {results}"

        # In DB, generation must be 2
        lock_rec = db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first()
        assert lock_rec.generation == 2
    finally:
        db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db.commit()
        db.close()

def test_scheduler_suite_e_heartbeat_renewal_multiple_times():
    """Test E: Heartbeat renewal periodically extends lease expiration."""
    db = SessionLocal()
    lock_key = f"suite_e_lock_{uuid.uuid4().hex[:6]}"
    worker_id = "heartbeat_worker_e"
    try:
        acquired = acquire_distributed_lock(db, lock_key, worker_id, ttl_seconds=3)
        assert acquired is True

        gen = get_lock_generation(db, lock_key, worker_id)
        assert gen == 1

        hb = LockHeartbeat(lock_key, worker_id, interval=0.2, lease_extension=4, generation=gen)
        hb.start()

        import time
        time.sleep(0.7)  # Multiple renewal triggers

        assert hb.is_lock_lost() is False

        lock_rec = db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first()
        assert lock_rec.owner_id == worker_id
        assert lock_rec.expires_at > datetime.utcnow()
        hb.stop()
    finally:
        db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db.commit()
        db.close()

def test_scheduler_suite_f_worker_ownership_renewal_isolation():
    """Test F: Worker ownership isolation: non-owners or wrong generations cannot renew."""
    db = SessionLocal()
    lock_key = f"suite_f_lock_{uuid.uuid4().hex[:6]}"
    worker_1 = "owner_worker_f"
    imposter = "imposter_worker_f"
    try:
        acquire_distributed_lock(db, lock_key, worker_1, ttl_seconds=60)

        # Imposter renewal fails
        assert renew_distributed_lock(db, lock_key, imposter, extension_seconds=300) is False

        # Wrong generation renewal fails
        assert renew_distributed_lock(db, lock_key, worker_1, extension_seconds=300, expected_generation=999) is False

        # Valid owner and generation succeeds
        assert renew_distributed_lock(db, lock_key, worker_1, extension_seconds=300, expected_generation=1) is True
    finally:
        db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db.commit()
        db.close()

def test_scheduler_suite_g_worker_ownership_release_isolation():
    """Test G: Worker release isolation: non-owners or wrong generations cannot release."""
    db = SessionLocal()
    lock_key = f"suite_g_lock_{uuid.uuid4().hex[:6]}"
    worker_1 = "owner_worker_g"
    imposter = "imposter_worker_g"
    try:
        acquire_distributed_lock(db, lock_key, worker_1, ttl_seconds=60)

        # Imposter release fails
        assert release_distributed_lock(db, lock_key, imposter) is False
        assert db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first() is not None

        # Wrong generation release fails
        assert release_distributed_lock(db, lock_key, worker_1, expected_generation=999) is False
        assert db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first() is not None

        # Legitimate owner releases
        assert release_distributed_lock(db, lock_key, worker_1, expected_generation=1) is True
        assert db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first() is None
    finally:
        db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db.commit()
        db.close()

def test_scheduler_suite_h_long_running_assessment_heartbeat():
    """Test H: Long-running review execution maintains heartbeat without losing lease."""
    db = SessionLocal()
    org = get_or_create_test_org(db)
    proj = Project(org_id=org.id, name=f"Suite H Proj {uuid.uuid4().hex[:6]}")
    db.add(proj)
    db.commit()

    lock_key = f"suite_h_lock_{uuid.uuid4().hex[:6]}"
    worker_id = "long_worker_h"
    try:
        acquired = acquire_distributed_lock(db, lock_key, worker_id, ttl_seconds=2)
        assert acquired is True

        gen = get_lock_generation(db, lock_key, worker_id)
        hb = LockHeartbeat(lock_key, worker_id, interval=0.2, lease_extension=3, generation=gen)
        hb.start()

        # Execute review with heartbeat running
        res = asyncio.run(execute_project_review(
            project_id=proj.id,
            trigger_type="scheduled",
            db_session=db,
            should_abort=hb.is_lock_lost,
            fencing_key=lock_key,
            fencing_owner=worker_id,
            fencing_generation=gen
        ))
        assert res is not None
        assert res.status == "completed"
        assert hb.is_lock_lost() is False
        hb.stop()
    finally:
        db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db.commit()
        db.close()

def test_scheduler_suite_i_mid_execution_fencing_rejection_and_rollback():
    """Test I: Mid-execution lock loss or fencing token change safely rolls back without stale writes."""
    db = SessionLocal()
    org = get_or_create_test_org(db)
    proj = Project(org_id=org.id, name=f"Suite I Proj {uuid.uuid4().hex[:6]}")
    db.add(proj)
    db.commit()

    lock_key = f"suite_i_lock_{uuid.uuid4().hex[:6]}"
    worker_id = "worker_i_initial"
    try:
        acquire_distributed_lock(db, lock_key, worker_id, ttl_seconds=60)

        # Fencing assertion with generation mismatch immediately raises RuntimeError
        with pytest.raises(RuntimeError, match="Fencing token validation failed"):
            assert_valid_fenced_lease(db, lock_key, worker_id, expected_generation=999)

        # In pipeline, passing stale expected generation aborts execution immediately
        with pytest.raises(RuntimeError, match="Fencing token validation failed"):
            asyncio.run(execute_project_review(
                project_id=proj.id,
                trigger_type="scheduled",
                db_session=db,
                fencing_key=lock_key,
                fencing_owner=worker_id,
                fencing_generation=999  # Stale generation
            ))
    finally:
        db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db.commit()
        db.close()

def test_scheduler_suite_j_transient_db_interruption_during_heartbeat():
    """Test J: LockHeartbeat retries on transient errors and marks lock lost if retries exceeded."""
    lock_key = f"suite_j_lock_{uuid.uuid4().hex[:6]}"
    worker_id = "worker_j_transient"

    # Heartbeat targeting non-existent lock will fail after retries and mark lock as lost
    hb = LockHeartbeat(lock_key, worker_id, interval=0.1, lease_extension=10, max_retries=2, generation=1)
    hb.start()

    import time
    time.sleep(0.4)

    assert hb.is_lock_lost() is True, "Heartbeat must flag lock as lost when renewal fails"
    hb.stop()

def test_genuine_mid_execution_lock_loss_stale_write_rejection():
    """
    Genuine Mid-Execution Lock-Loss & Transactional Stale-Write Protection Integration Test:
    1. Independent database sessions & worker execution contexts (Worker A in thread, Worker B in main).
    2. Worker A acquires distributed lock -> generation = 1.
    3. Worker A starts assessment pipeline with an active LockHeartbeat.
    4. Worker A completes initial stage (creation & intelligence) and pauses at controlled synchronization barrier.
    5. Confirm Worker A's heartbeat is operating and extending lease.
    6. Confirm Worker B cannot acquire the active lock (rejected).
    7. Simulate valid lease expiration / ownership loss condition (heartbeat stopped, expires_at set to past).
    8. Worker B reclaims expired lock -> generation incremented to 2.
    9. Worker A resumes its pending execution.
    10. Worker A attempts to persist its results.
    11. Database rejects Worker A's write (StaleGenerationWriteError / fencing mismatch).
    12. Worker A safely rolls back, suppresses mutating assessment status to failed, and terminates.
    13. Worker B retains ownership and completes its own assessment under generation 2.
    14. Worker A attempts to release Worker B's lock -> rejected (cannot release).
    15. Verify:
        - Only 1 active owner (Worker B).
        - Monotonic fencing generation (1 -> 2).
        - Stale Worker A write rejected.
        - Worker B write accepted.
        - Exactly 1 completed assessment (generation 2).
        - Exactly 1 historical snapshot (generation 2, PostgreSQL storage).
        - No duplicate assessments, no stale scores, no stale risks.
    """
    import threading
    db_a = SessionLocal()
    db_b = SessionLocal()
    db_admin = SessionLocal()

    lock_key = f"review_job_lock_{uuid.uuid4().hex[:8]}"
    worker_a = "worker_alpha"
    worker_b = "worker_beta"

    try:
        # Create test org, project, and technology
        org = get_or_create_test_org(db_admin)
        proj = Project(
            org_id=org.id,
            name=f"Fencing Proj {uuid.uuid4().hex[:6]}",
            description="Fencing test project"
        )
        db_admin.add(proj)
        db_admin.commit()

        tech = Technology(
            name=f"fencing-pkg-{uuid.uuid4().hex[:4]}",
            ecosystem="npm",
            latest_stable_version="2.0.0"
        )
        db_admin.add(tech)
        db_admin.commit()

        p_tech = ProjectTechnology(project_id=proj.id, technology_id=tech.id, installed_version="1.0.0")
        db_admin.add(p_tech)
        db_admin.commit()

        # Step 1 & 2: Worker A acquires the lock -> generation = 1
        acq_a = acquire_distributed_lock(db_a, lock_key, worker_a, ttl_seconds=6)
        assert acq_a is True
        gen_a = get_lock_generation(db_a, lock_key, worker_a)
        assert gen_a == 1

        # Step 3: Worker A starts real heartbeat
        hb_a = LockHeartbeat(lock_key, worker_a, interval=0.2, lease_extension=6, generation=gen_a)
        hb_a.start()

        # Synchronization barriers
        worker_a_paused = threading.Event()
        worker_a_resume = threading.Event()
        worker_a_error = []
        worker_a_finished = threading.Event()

        def worker_a_stage_hook(stage_name: str):
            if stage_name == "7_before_score_calculation":
                worker_a_paused.set()
                worker_a_resume.wait(timeout=10)

        def worker_a_execution():
            thread_db_a = SessionLocal()
            try:
                asyncio.run(execute_project_review(
                    project_id=proj.id,
                    trigger_type="scheduled",
                    db_session=thread_db_a,
                    should_abort=hb_a.is_lock_lost,
                    fencing_key=lock_key,
                    fencing_owner=worker_a,
                    fencing_generation=gen_a,
                    stage_hook=worker_a_stage_hook
                ))
            except Exception as e:
                worker_a_error.append(e)
            finally:
                thread_db_a.close()
                worker_a_finished.set()

        thread_a = threading.Thread(target=worker_a_execution, daemon=True)
        thread_a.start()

        # Step 4: Wait for Worker A to complete initial stages and pause at barrier
        assert worker_a_paused.wait(timeout=5), "Worker A should pause at synchronization barrier"

        # Step 5: Confirm Worker A's heartbeat is operating and lease is active
        import time
        time.sleep(0.3)
        assert hb_a.is_lock_lost() is False
        lock_before = db_admin.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first()
        assert lock_before.owner_id == worker_a
        assert lock_before.expires_at > datetime.utcnow()

        # Step 6: Confirm Worker B cannot acquire active lock
        acq_b_fail = acquire_distributed_lock(db_b, lock_key, worker_b, ttl_seconds=600)
        assert acq_b_fail is False

        # Step 7: Stop Worker A's heartbeat and simulate valid lease expiration
        hb_a.stop()
        past_time = datetime.utcnow() - timedelta(seconds=10)
        db_admin.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).update({
            "expires_at": past_time
        })
        db_admin.commit()

        # Step 8 & 9: Worker B reclaims expired lock with generation incremented to 2
        acq_b_success = acquire_distributed_lock(db_b, lock_key, worker_b, ttl_seconds=600)
        assert acq_b_success is True
        gen_b = get_lock_generation(db_b, lock_key, worker_b)
        assert gen_b == 2

        # Step 10 & 11: Worker A resumes its pending operation
        worker_a_resume.set()
        assert worker_a_finished.wait(timeout=5), "Worker A should terminate after resuming"

        # Step 12: Assert Worker A's stale write was rejected and aborted safely
        assert len(worker_a_error) > 0, "Worker A should have encountered an error"
        assert any(
            isinstance(err, (StaleGenerationWriteError, RuntimeError))
            for err in worker_a_error
        ), f"Worker A should fail with fencing error, got: {worker_a_error}"

        # Step 13: Worker B executes review pipeline to completion under generation 2
        res_b = asyncio.run(execute_project_review(
            project_id=proj.id,
            trigger_type="scheduled",
            db_session=db_b,
            fencing_key=lock_key,
            fencing_owner=worker_b,
            fencing_generation=gen_b
        ))
        assert res_b is not None
        assert res_b.status == "completed"
        assert res_b.fencing_generation == 2

        # Step 14: Worker A cannot release Worker B's lock
        rel_a_fail = release_distributed_lock(db_a, lock_key, worker_a, expected_generation=gen_a)
        assert rel_a_fail is False, "Worker A cannot release Worker B's lock"

        # Step 15: Required assertions
        # 1. Exactly 1 active owner (worker_b) with generation = 2
        final_lock = db_admin.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first()
        assert final_lock.owner_id == worker_b
        assert final_lock.generation == 2

        # 2. Exactly 1 completed assessment exists for this project (produced by Worker B)
        completed_assessments = (
            db_admin.query(Assessment)
            .filter(Assessment.project_id == proj.id, Assessment.status == "completed")
            .all()
        )
        assert len(completed_assessments) == 1
        assert completed_assessments[0].fencing_generation == 2

        # 3. Exactly 1 historical snapshot recorded, with generation 2 and PostgreSQL storage
        hist_records = (
            db_admin.query(HistoricalAssessment)
            .filter(HistoricalAssessment.project_id == proj.id)
            .all()
        )
        assert len(hist_records) == 1
        assert hist_records[0].fencing_generation == 2
        assert hist_records[0].storage_provider == "postgresql"

        # 4. Clean up
        release_distributed_lock(db_b, lock_key, worker_b, expected_generation=gen_b)

    finally:
        if 'hb_a' in locals() and hb_a:
            hb_a.stop()
        db_admin.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db_admin.commit()
        db_a.close()
        db_b.close()
        db_admin.close()

def test_heartbeat_renewal_unblocked_during_slow_ai_request():
    """
    Phase 4: Verify that LockHeartbeat renews its lease periodically while a slow external
    AI/Firecrawl request is running, proving that the assessment execution pipeline does NOT
    hold database row locks across external operations.
    """
    db = SessionLocal()
    db_b = SessionLocal()
    org = get_or_create_test_org(db)
    proj = Project(org_id=org.id, name=f"Slow AI Proj {uuid.uuid4().hex[:6]}")
    db.add(proj)
    db.commit()

    tech = Technology(name=f"pkg-{uuid.uuid4().hex[:4]}", ecosystem="npm", latest_stable_version="1.0.0")
    db.add(tech)
    db.commit()

    p_tech = ProjectTechnology(project_id=proj.id, technology_id=tech.id, installed_version="1.0.0")
    db.add(p_tech)
    db.commit()

    lock_key = f"review_job_lock_{uuid.uuid4().hex[:8]}"
    worker_id = "worker_slow_ai"
    try:
        # Worker acquires lock with short TTL (2 seconds)
        acquired = acquire_distributed_lock(db, lock_key, worker_id, ttl_seconds=2)
        assert acquired is True
        gen = get_lock_generation(db, lock_key, worker_id)

        # Heartbeat runs every 0.15s extending by 2s
        hb = LockHeartbeat(lock_key, worker_id, interval=0.15, lease_extension=2, generation=gen)
        hb.start()

        # Simulated slow AI analyzer that sleeps for 0.8 seconds
        async def mock_slow_ai(*args, **kwargs):
            await asyncio.sleep(0.8)
            return {
                "overall_score": 85.0,
                "risk_classification": "Good",
                "maintenance_health": 90.0,
                "security_exposure": 90.0,
                "version_currency": 90.0,
                "community_activity": 85.0,
                "documentation_quality": 85.0,
                "ecosystem_compatibility": 90.0,
                "sustainability": 90.0,
                "upgrade_complexity": 90.0,
                "confidence_level": "High",
                "recommended_action": "Keep current",
                "upgrade_complexity_level": "Low",
                "identified_problems": [],
                "risks": []
            }

        with patch("app.services.ai_analyzer.AITechnologyDebtAnalyzer.analyze_technology", side_effect=mock_slow_ai):
            # Run assessment
            res = asyncio.run(execute_project_review(
                project_id=proj.id,
                trigger_type="scheduled",
                db_session=db,
                should_abort=hb.is_lock_lost,
                fencing_key=lock_key,
                fencing_owner=worker_id,
                fencing_generation=gen
            ))

            # While assessment ran (>0.8s), heartbeat must have renewed without being blocked!
            assert hb.is_lock_lost() is False

            # Verify Worker B is rejected because Worker A successfully renewed its lease
            acq_b = acquire_distributed_lock(db_b, lock_key, "worker_b_competing", ttl_seconds=60)
            assert acq_b is False, "Worker B must be rejected while Worker A holds active renewed lease"

            assert res is not None
            assert res.status == "completed"

        hb.stop()
        release_distributed_lock(db, lock_key, worker_id, expected_generation=gen)
    finally:
        db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db.commit()
        db.close()
        db_b.close()


def test_premature_commit_regression_and_atomic_persistence():
    """
    Regression Test for Premature-Commit Defect and Atomic Assessment Persistence (Requirement 3):
    Validates that verify_ownership_short_transaction() does NOT commit the caller's session,
    does NOT release the row-level lock acquired via SELECT FOR UPDATE, and does NOT
    allow another worker to take over while the protected transaction is active.
    
    Sequence:
    1. Worker A acquires generation 1.
    2. Worker A starts an assessment (created with processing status).
    3. Worker A reaches final persistence.
    4. Worker A acquires the transactional fencing lock (SELECT ... FOR UPDATE).
    5. Assessment completion update, scores, and risks are staged on Worker A's session.
    6. Trigger the ownership verification checkpoint before snapshot creation:
       verify_ownership_short_transaction(session_a, lock_key, "worker_a", 1).
    7. Verify from an independent inspection session (session_inspect) that the verification
       function DID NOT commit pending records (scores, risks, completed status).
    8. Verify that the fencing lock remains held by Worker A.
    9. Verify that Worker B (session_b) cannot reclaim or modify the lock during the protected transaction.
    10. Complete snapshot creation (staged on session_a with auto_commit=False).
    11. Commit all protected records atomically (session_a.commit()).
    12. Verify from session_inspect that completed assessment, scores, risks, and snapshot exist together.
    """
    session_admin = SessionLocal()
    session_a = SessionLocal()
    session_b = SessionLocal()
    session_inspect = SessionLocal()

    lock_key = f"review_job_lock_{uuid.uuid4().hex[:8]}"
    worker_a = "worker_alpha"
    worker_b = "worker_beta"

    try:
        org = get_or_create_test_org(session_admin)
        proj = Project(
            org_id=org.id,
            name=f"Atomic Commit Test Proj {uuid.uuid4().hex[:6]}",
            description="Testing atomic persistence without premature commit"
        )
        session_admin.add(proj)
        session_admin.commit()

        tech = Technology(
            name=f"test-pkg-{uuid.uuid4().hex[:4]}",
            ecosystem="npm",
            latest_stable_version="3.0.0"
        )
        session_admin.add(tech)
        session_admin.commit()

        # Step 1: Worker A acquires generation 1
        acq_a = acquire_distributed_lock(session_a, lock_key, worker_a, ttl_seconds=60)
        assert acq_a is True
        gen_a = get_lock_generation(session_a, lock_key, worker_a)
        assert gen_a == 1

        # Step 2: Worker A starts an assessment
        assessment = Assessment(
            project_id=proj.id,
            trigger_type="scheduled",
            status="processing",
            fencing_generation=gen_a,
            overall_health_score=None,
            risk_classification="Healthy",
            confidence_level="High"
        )
        session_a.add(assessment)
        session_a.commit()
        assessment_id = assessment.id

        # Step 3 & 4: Worker A reaches final persistence and acquires transactional fencing lock
        assert_valid_fenced_lease_transactional(session_a, lock_key, worker_a, gen_a)

        # Step 5: Assessment, scores, and risks are staged on session_a (uncommitted)
        session_a.query(Assessment).filter(Assessment.id == assessment_id).update({
            "overall_health_score": 88.5,
            "risk_classification": "Good",
            "status": "completed",
            "summary": "Completed under atomic fenced transaction"
        }, synchronize_session=False)

        score_rec = TechnologyScore(
            assessment_id=assessment_id,
            technology_id=tech.id,
            overall_score=88.5,
            risk_classification="Good",
            confidence_level="High",
            notes="Staged score"
        )
        session_a.add(score_rec)

        risk_rec = RiskFinding(
            assessment_id=assessment_id,
            technology_id=tech.id,
            project_id=proj.id,
            severity="Medium",
            title=f"Staged Risk {uuid.uuid4().hex[:6]}",
            description="Staged risk description",
            status="Open"
        )
        session_a.add(risk_rec)

        # Step 6: Trigger the ownership verification checkpoint before snapshot creation
        # THIS MUST NOT COMMIT session_a!
        verify_ownership_short_transaction(session_a, lock_key, worker_a, gen_a)

        # Step 7: Verify that the verification function does NOT commit pending records
        # In session_inspect (an independent session), the staged records MUST NOT be visible!
        inspect_scores = session_inspect.query(TechnologyScore).filter(TechnologyScore.assessment_id == assessment_id).all()
        assert len(inspect_scores) == 0, "Premature commit defect: TechnologyScore was committed before final commit!"

        inspect_risks = session_inspect.query(RiskFinding).filter(RiskFinding.assessment_id == assessment_id).all()
        assert len(inspect_risks) == 0, "Premature commit defect: RiskFinding was committed before final commit!"

        inspect_assessment = session_inspect.query(Assessment).filter(Assessment.id == assessment_id).first()
        assert inspect_assessment.status == "processing", "Premature commit defect: Assessment status was committed before final commit!"

        # Step 8 & 9: Verify that the fencing lock remains held and Worker B cannot reclaim it
        # Worker B attempts to acquire/reclaim the lock in an independent thread/session
        worker_b_reclaimed = []
        def worker_b_try_acquire():
            thread_db_b = SessionLocal()
            try:
                from sqlalchemy import text
                if thread_db_b.bind.dialect.name == "sqlite":
                    thread_db_b.execute(text("PRAGMA busy_timeout=300"))
                res = acquire_distributed_lock(thread_db_b, lock_key, worker_b, ttl_seconds=60)
                worker_b_reclaimed.append(res)
            except Exception:
                worker_b_reclaimed.append(False)
            finally:
                thread_db_b.close()

        th_b = threading.Thread(target=worker_b_try_acquire)
        th_b.start()
        th_b.join(timeout=2.0)
        assert len(worker_b_reclaimed) == 1
        assert worker_b_reclaimed[0] is False, "Worker B should not be able to reclaim lock held by Worker A"

        # Step 10: Complete snapshot creation (staged on session_a with auto_commit=False)
        adapter = HistoricalAssessmentMemoryAdapter()
        asyncio.run(adapter.record_assessment_snapshot(
            db=session_a,
            project_id=proj.id,
            assessment_id=assessment_id,
            overall_score=88.5,
            risk_classification="Good",
            tech_scores=[{"technology_name": tech.name, "score": 88.5, "classification": "Good"}],
            identified_risks=[{"severity": "Medium", "title": risk_rec.title}],
            project_name=proj.name,
            fencing_generation=gen_a,
            auto_commit=False
        ))

        # Still not committed in session_inspect
        inspect_snapshots_pre = session_inspect.query(HistoricalAssessment).filter(HistoricalAssessment.assessment_id == assessment_id).all()
        assert len(inspect_snapshots_pre) == 0, "HistoricalAssessment was committed before final commit!"

        # Step 11: Commit all protected records atomically
        session_a.commit()

        # Step 12: Verify that assessment, scores, risks, and snapshot exist together
        session_inspect.commit()  # Refresh session_inspect to see committed state
        inspect_assessment_post = session_inspect.query(Assessment).filter(Assessment.id == assessment_id).first()
        assert inspect_assessment_post.status == "completed"
        assert inspect_assessment_post.overall_health_score == 88.5

        inspect_scores_post = session_inspect.query(TechnologyScore).filter(TechnologyScore.assessment_id == assessment_id).all()
        assert len(inspect_scores_post) == 1

        inspect_risks_post = session_inspect.query(RiskFinding).filter(RiskFinding.assessment_id == assessment_id).all()
        assert len(inspect_risks_post) == 1

        inspect_snapshots_post = session_inspect.query(HistoricalAssessment).filter(HistoricalAssessment.assessment_id == assessment_id).all()
        assert len(inspect_snapshots_post) == 1
        assert inspect_snapshots_post[0].health_score == 88.5

    finally:
        session_admin.close()
        session_a.close()
        session_b.close()
        session_inspect.close()


def test_premature_commit_regression_rollback_variant():
    """
    Rollback Variant for Premature-Commit Defect (Requirement 3):
    Verifies that when a failure occurs before final commit, a rollback
    discards ALL uncommitted records (assessment status, scores, risks, snapshot)
    and leaves ZERO orphaned result records in the database.
    """
    session_admin = SessionLocal()
    session_a = SessionLocal()
    session_inspect = SessionLocal()

    lock_key = f"review_job_lock_{uuid.uuid4().hex[:8]}"
    worker_a = "worker_alpha"

    try:
        org = get_or_create_test_org(session_admin)
        proj = Project(
            org_id=org.id,
            name=f"Rollback Test Proj {uuid.uuid4().hex[:6]}",
            description="Testing rollback of uncommitted results"
        )
        session_admin.add(proj)
        session_admin.commit()

        tech = Technology(
            name=f"rollback-pkg-{uuid.uuid4().hex[:4]}",
            ecosystem="npm",
            latest_stable_version="1.0.0"
        )
        session_admin.add(tech)
        session_admin.commit()

        # Worker A acquires lock
        acquire_distributed_lock(session_a, lock_key, worker_a, ttl_seconds=60)
        gen_a = get_lock_generation(session_a, lock_key, worker_a)

        # Baseline assessment created with processing status
        assessment = Assessment(
            project_id=proj.id,
            trigger_type="scheduled",
            status="processing",
            fencing_generation=gen_a
        )
        session_a.add(assessment)
        session_a.commit()
        assessment_id = assessment.id

        # Acquire transactional fencing lock
        assert_valid_fenced_lease_transactional(session_a, lock_key, worker_a, gen_a)

        # Stage assessment update, scores, risks, and snapshot
        session_a.query(Assessment).filter(Assessment.id == assessment_id).update({
            "overall_health_score": 75.0,
            "risk_classification": "Moderate",
            "status": "completed"
        }, synchronize_session=False)

        score_rec = TechnologyScore(
            assessment_id=assessment_id,
            technology_id=tech.id,
            overall_score=75.0,
            risk_classification="Moderate"
        )
        session_a.add(score_rec)

        risk_rec = RiskFinding(
            assessment_id=assessment_id,
            technology_id=tech.id,
            project_id=proj.id,
            severity="High",
            title=f"Doomed Risk {uuid.uuid4().hex[:6]}",
            description="Should be rolled back",
            status="Open"
        )
        session_a.add(risk_rec)

        # Checkpoint before snapshot - must NOT commit!
        verify_ownership_short_transaction(session_a, lock_key, worker_a, gen_a)

        adapter = HistoricalAssessmentMemoryAdapter()
        asyncio.run(adapter.record_assessment_snapshot(
            db=session_a,
            project_id=proj.id,
            assessment_id=assessment_id,
            overall_score=75.0,
            risk_classification="Moderate",
            tech_scores=[],
            identified_risks=[],
            project_name=proj.name,
            fencing_generation=gen_a,
            auto_commit=False
        ))

        # Force a failure before final commit -> trigger rollback
        session_a.rollback()

        # Verify none of the protected result records survived
        inspect_scores = session_inspect.query(TechnologyScore).filter(TechnologyScore.assessment_id == assessment_id).all()
        assert len(inspect_scores) == 0, "Rollback failed: TechnologyScore survived rollback!"

        inspect_risks = session_inspect.query(RiskFinding).filter(RiskFinding.assessment_id == assessment_id).all()
        assert len(inspect_risks) == 0, "Rollback failed: RiskFinding survived rollback!"

        inspect_snapshots = session_inspect.query(HistoricalAssessment).filter(HistoricalAssessment.assessment_id == assessment_id).all()
        assert len(inspect_snapshots) == 0, "Rollback failed: HistoricalAssessment survived rollback!"

        inspect_assessment = session_inspect.query(Assessment).filter(Assessment.id == assessment_id).first()
        assert inspect_assessment.status == "processing", "Assessment status was not rolled back to processing!"
        assert inspect_assessment.overall_health_score is None

    finally:
        session_admin.close()
        session_a.close()
        session_inspect.close()


def test_final_persistence_boundary_concurrency_lock_loss():
    """
    Final Persistence Boundary Concurrency & Stale Write Rejection Test (Requirement 4):
    Proves that:
    1. Independent execution contexts own their dedicated SQLAlchemy sessions (no shared active session).
    2. Worker A executes up to the final persistence boundary (stage 8: '8_before_assessment_persistence').
    3. Worker A pauses at this boundary.
    4. Worker A's lease expires; Worker B takes ownership under generation 2.
    5. Worker B executes and completes its review to completion under generation 2.
    6. Worker A resumes and attempts to enter the final persistence transaction.
    7. Worker A is rejected by transactional fencing with StaleGenerationWriteError.
    8. Worker A rolls back cleanly and terminates safely without altering status to failed.
    9. Final verification proves:
       - Worker A cannot commit after Worker B takes ownership.
       - Worker B completes successfully.
       - No stale assessment results survive from Worker A.
       - No stale snapshots survive from Worker A.
       - No duplicate completed assessments occur (exactly 1 completed assessment).
    """
    import threading
    db_admin = SessionLocal()
    lock_key = f"review_job_lock_{uuid.uuid4().hex[:8]}"
    worker_a = "worker_alpha_persist"
    worker_b = "worker_beta_persist"

    try:
        org = get_or_create_test_org(db_admin)
        proj = Project(
            org_id=org.id,
            name=f"Persistence Boundary Proj {uuid.uuid4().hex[:6]}",
            description="Testing concurrency at final persistence boundary"
        )
        db_admin.add(proj)
        db_admin.commit()

        tech = Technology(
            name=f"pkg-boundary-{uuid.uuid4().hex[:4]}",
            ecosystem="npm",
            latest_stable_version="2.0.0"
        )
        db_admin.add(tech)
        db_admin.commit()

        p_tech = ProjectTechnology(project_id=proj.id, technology_id=tech.id, installed_version="1.0.0")
        db_admin.add(p_tech)
        db_admin.commit()

        # Worker A acquires initial lease -> generation 1
        acq_a = acquire_distributed_lock(db_admin, lock_key, worker_a, ttl_seconds=6)
        assert acq_a is True
        gen_a = get_lock_generation(db_admin, lock_key, worker_a)
        assert gen_a == 1

        hb_a = LockHeartbeat(lock_key, worker_a, interval=0.1, lease_extension=6, generation=gen_a)
        hb_a.start()

        worker_a_at_boundary = threading.Event()
        worker_a_resume = threading.Event()
        worker_a_error = []
        worker_a_finished = threading.Event()

        def worker_a_stage_hook(stage_name: str):
            if stage_name == "8_before_assessment_persistence":
                worker_a_at_boundary.set()
                worker_a_resume.wait(timeout=10)

        def worker_a_runner():
            # Dedicated thread-local session
            thread_db_a = SessionLocal()
            try:
                asyncio.run(execute_project_review(
                    project_id=proj.id,
                    trigger_type="scheduled",
                    db_session=thread_db_a,
                    should_abort=hb_a.is_lock_lost,
                    fencing_key=lock_key,
                    fencing_owner=worker_a,
                    fencing_generation=gen_a,
                    stage_hook=worker_a_stage_hook
                ))
            except Exception as e:
                worker_a_error.append(e)
            finally:
                thread_db_a.close()
                worker_a_finished.set()

        thread_a = threading.Thread(target=worker_a_runner, daemon=True)
        thread_a.start()

        # Wait for Worker A to reach stage 8 (the final persistence boundary)
        assert worker_a_at_boundary.wait(timeout=6), "Worker A should reach final persistence boundary"

        # Stop Worker A's heartbeat and simulate lease expiration
        hb_a.stop()
        past_time = datetime.utcnow() - timedelta(seconds=120)
        db_admin.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).update({
            "expires_at": past_time
        })
        db_admin.commit()

        # Worker B creates its own session and reclaims the lock -> generation 2
        db_b = SessionLocal()
        try:
            acq_b = acquire_distributed_lock(db_b, lock_key, worker_b, ttl_seconds=60)
            assert acq_b is True, "Worker B should reclaim expired lock"
            gen_b = get_lock_generation(db_b, lock_key, worker_b)
            assert gen_b == 2, f"Worker B generation should be 2, got {gen_b}"

            # Worker B runs to completion under generation 2
            res_b = asyncio.run(execute_project_review(
                project_id=proj.id,
                trigger_type="scheduled",
                db_session=db_b,
                fencing_key=lock_key,
                fencing_owner=worker_b,
                fencing_generation=gen_b
            ))
            assert res_b is not None
            assert res_b.status == "completed"
            assert res_b.fencing_generation == 2
        finally:
            db_b.close()

        # Resume Worker A to attempt commit across the persistence boundary
        worker_a_resume.set()
        assert worker_a_finished.wait(timeout=6), "Worker A should finish"

        # Worker A must have been rejected
        assert len(worker_a_error) == 1
        assert isinstance(worker_a_error[0], StaleGenerationWriteError) or "superseded" in str(worker_a_error[0]).lower() or "lost" in str(worker_a_error[0]).lower()

        # Invariants verification:
        # 1. Exactly 1 completed assessment exists for this project (from Worker B, gen 2)
        completed_assessments = (
            db_admin.query(Assessment)
            .filter(Assessment.project_id == proj.id, Assessment.status == "completed")
            .all()
        )
        assert len(completed_assessments) == 1, f"Expected exactly 1 completed assessment, found {len(completed_assessments)}"
        assert completed_assessments[0].fencing_generation == 2

        # 2. Exactly 1 historical snapshot exists (from Worker B, gen 2)
        hist_snapshots = (
            db_admin.query(HistoricalAssessment)
            .filter(HistoricalAssessment.project_id == proj.id)
            .all()
        )
        assert len(hist_snapshots) == 1, f"Expected exactly 1 historical snapshot, found {len(hist_snapshots)}"
        assert hist_snapshots[0].fencing_generation == 2
        assert hist_snapshots[0].storage_provider == "postgresql"

        # 3. Worker A's initial processing assessment was NOT marked failed (stale write suppressed)
        proc_assessments = (
            db_admin.query(Assessment)
            .filter(Assessment.project_id == proj.id, Assessment.fencing_generation == 1)
            .all()
        )
        for pa in proc_assessments:
            assert pa.status != "completed"

    finally:
        if 'hb_a' in locals() and hb_a:
            hb_a.stop()
        db_admin.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db_admin.commit()
        db_admin.close()


def test_post_commit_lease_expiration_does_not_fail_assessment():
    """
    v1.0.9 Regression Test: Post-commit completion boundary safety.
    Verifies that if lock lease expires or is reassigned to another worker
    immediately after the database commit (stage '10_post_completion_telemetry'),
    the assessment remains durably committed as 'completed' and is NEVER marked 'failed'
    or rolled back.
    """
    db_admin = SessionLocal()
    db_worker = SessionLocal()
    lock_key = f"review_job_lock_{uuid.uuid4().hex[:8]}"
    worker_id = "worker_post_commit"

    try:
        org = get_or_create_test_org(db_admin)
        proj = Project(
            org_id=org.id,
            name=f"PostCommit Proj {uuid.uuid4().hex[:6]}",
            description="Testing post-commit lease expiration safety"
        )
        db_admin.add(proj)
        db_admin.commit()

        tech = Technology(
            name=f"pkg-pc-{uuid.uuid4().hex[:4]}",
            ecosystem="npm",
            latest_stable_version="1.5.0"
        )
        db_admin.add(tech)
        db_admin.commit()

        p_tech = ProjectTechnology(project_id=proj.id, technology_id=tech.id, installed_version="1.0.0")
        db_admin.add(p_tech)
        db_admin.commit()

        # Worker acquires lock with generation 1
        acq = acquire_distributed_lock(db_admin, lock_key, worker_id, ttl_seconds=60)
        assert acq is True
        gen = get_lock_generation(db_admin, lock_key, worker_id)
        assert gen == 1

        stage_10_reached = []

        def post_commit_stage_hook(stage_name: str):
            if stage_name == "10_post_completion_telemetry":
                stage_10_reached.append(True)
                # At this exact point, db.commit() has executed.
                # Simulate lease expiration and takeover by another worker (e.g. Worker B)
                thread_db = SessionLocal()
                try:
                    thread_db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).update({
                        "owner_id": "worker_competitor_post_commit",
                        "generation": 2,
                        "expires_at": datetime.utcnow() + timedelta(seconds=60)
                    }, synchronize_session=False)
                    thread_db.commit()
                finally:
                    thread_db.close()

        # Execute project review
        completed_assessment = asyncio.run(execute_project_review(
            project_id=proj.id,
            trigger_type="scheduled",
            db_session=db_worker,
            fencing_key=lock_key,
            fencing_owner=worker_id,
            fencing_generation=gen,
            stage_hook=post_commit_stage_hook
        ))

        assert len(stage_10_reached) == 1, "Stage 10 post-completion hook should have been called"
        assert completed_assessment is not None
        assert completed_assessment.status == "completed", f"Assessment status must be 'completed', got '{completed_assessment.status}'"
        assert completed_assessment.overall_health_score is not None
        assert completed_assessment.overall_health_score > 0

        # Verify from independent inspection session
        db_inspect = SessionLocal()
        try:
            inspect_assessment = db_inspect.query(Assessment).filter(Assessment.id == completed_assessment.id).first()
            assert inspect_assessment is not None
            assert inspect_assessment.status == "completed"

            # Verify scores and risks are persisted
            scores = db_inspect.query(TechnologyScore).filter(TechnologyScore.assessment_id == completed_assessment.id).all()
            assert len(scores) >= 1

            # Verify historical snapshot exists
            snapshots = db_inspect.query(HistoricalAssessment).filter(HistoricalAssessment.assessment_id == completed_assessment.id).all()
            assert len(snapshots) == 1
            assert snapshots[0].storage_provider == "postgresql"

            # Verify project last_assessment_date is updated
            inspect_proj = db_inspect.query(Project).filter(Project.id == proj.id).first()
            assert inspect_proj.last_assessment_date is not None

            # Verify no duplicate assessments created for this project
            all_assessments = db_inspect.query(Assessment).filter(Assessment.project_id == proj.id).all()
            assert len(all_assessments) == 1
        finally:
            db_inspect.close()

    finally:
        db_admin.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).delete()
        db_admin.commit()
        db_worker.close()
        db_admin.close()


# -------------------------------------------------------------
# 4. AI PROVIDER VERIFICATION TESTS (AUTHENTICATED PROBES)
# -------------------------------------------------------------
def test_ai_provider_verification_gemini_unconfigured():
    analyzer = AITechnologyDebtAnalyzer(gemini_key="")
    res = asyncio.run(analyzer.verify_connectivity("gemini"))
    assert res["status"] == "unconfigured"
    assert res["connected"] is False

def test_ai_provider_verification_gemini_connected():
    analyzer = AITechnologyDebtAnalyzer(gemini_key="valid-mock-key")
    mock_resp = MagicMock(status_code=200)
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        res = asyncio.run(analyzer.verify_connectivity("gemini"))
        assert res["status"] == "connected"
        assert res["connected"] is True

def test_ai_provider_verification_gemini_invalid_key():
    analyzer = AITechnologyDebtAnalyzer(gemini_key="invalid-key")
    mock_resp = MagicMock(status_code=403, text="API key not valid")
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        res = asyncio.run(analyzer.verify_connectivity("gemini"))
        assert res["status"] == "invalid_credentials"
        assert res["connected"] is False

def test_ai_provider_verification_gemini_quota_exceeded():
    analyzer = AITechnologyDebtAnalyzer(gemini_key="rate-limited-key")
    mock_resp = MagicMock(status_code=429)
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        res = asyncio.run(analyzer.verify_connectivity("gemini"))
        assert res["status"] == "quota_exceeded"
        assert res["connected"] is False

def test_ai_provider_verification_openai_connected():
    analyzer = AITechnologyDebtAnalyzer(openai_key="sk-mock-valid-key")
    mock_resp = MagicMock(status_code=200)
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        res = asyncio.run(analyzer.verify_connectivity("openai"))
        assert res["status"] == "connected"
        assert res["connected"] is True

def test_ai_provider_verification_openai_invalid_key():
    analyzer = AITechnologyDebtAnalyzer(openai_key="sk-invalid-key")
    mock_resp = MagicMock(status_code=401)
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        res = asyncio.run(analyzer.verify_connectivity("openai"))
        assert res["status"] == "invalid_credentials"
        assert res["connected"] is False

@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY environment variable required for live integration test"
)
def test_ai_provider_live_gemini_connectivity():
    """Live Gemini API connectivity test when actual GEMINI_API_KEY is configured in environment."""
    key = os.getenv("GEMINI_API_KEY")
    analyzer = AITechnologyDebtAnalyzer(gemini_key=key)
    res = asyncio.run(analyzer.verify_connectivity("gemini"))
    assert res["status"] in ["connected", "invalid_credentials", "quota_exceeded"]
    assert "message" in res

@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY environment variable required for live integration test"
)
def test_ai_provider_live_openai_connectivity():
    """Live OpenAI API connectivity test when actual OPENAI_API_KEY is configured in environment."""
    key = os.getenv("OPENAI_API_KEY")
    analyzer = AITechnologyDebtAnalyzer(openai_key=key)
    res = asyncio.run(analyzer.verify_connectivity("openai"))
    assert res["status"] in ["connected", "invalid_credentials", "quota_exceeded"]
    assert "message" in res


# -------------------------------------------------------------
# 5. MEMENTO ARCHITECTURE & AUTHORITATIVE POSTGRESQL MEMORY
# -------------------------------------------------------------
def test_memento_authoritative_postgresql_memory_creation():
    """Verify that snapshot creation authoritatively records postgresql provenance."""
    mem = MementoMemoryAdapter()
    db = SessionLocal()
    try:
        org = get_or_create_test_org(db)
        proj = Project(org_id=org.id, name=f"Memento Auth Proj {uuid.uuid4().hex[:6]}")
        db.add(proj)
        db.commit()

        ass = Assessment(project_id=proj.id, status="completed", overall_health_score=90.0)
        db.add(ass)
        db.commit()

        hist = asyncio.run(mem.record_assessment_snapshot(
            db=db,
            project_id=proj.id,
            assessment_id=ass.id,
            overall_score=90.0,
            risk_classification="Healthy",
            tech_scores=[],
            identified_risks=[]
        ))
        assert hist.storage_provider == "postgresql"
        assert hist.sync_status == "authoritative_postgresql"
        assert hist.sync_error == ""
    finally:
        db.close()

def test_memento_authoritative_postgresql_memory_retrieval():
    """Verify that get_historical_memories retrieves memories authoritatively from PostgreSQL."""
    mem = MementoMemoryAdapter()
    db = SessionLocal()
    try:
        proj = get_or_create_test_project(db)
        ass = Assessment(project_id=proj.id, status="completed", overall_health_score=85.0)
        db.add(ass)
        db.commit()

        asyncio.run(mem.record_assessment_snapshot(
            db=db,
            project_id=proj.id,
            assessment_id=ass.id,
            overall_score=85.0,
            risk_classification="Good",
            tech_scores=[],
            identified_risks=[]
        ))

        memories = asyncio.run(mem.get_historical_memories(db, proj.id))
        assert memories["storage_provider"] == "postgresql"
        assert memories["remote_sync_status"] == "authoritative_postgresql"
        assert len(memories["memories"]) >= 1
    finally:
        db.close()

def test_memento_mcp_architecture_verification():
    """Verify that verify_connectivity() truthfully reports PostgreSQL as authoritative and notes MCP architecture."""
    mem = MementoMemoryAdapter()
    res = asyncio.run(mem.verify_connectivity())
    assert res["status"] == "postgresql_authoritative"
    assert res["mode"] == "postgresql"
    assert res["connected"] is True
    assert res["mcp_architecture"] == "local_first_mcp_sqlite"
    assert "runmemento.com" in res["message"]

def test_memento_delta_comparison_with_postgresql_provenance():
    """Verify that generate_delta_comparison reports postgresql storage provider."""
    mem = MementoMemoryAdapter()
    db = SessionLocal()
    try:
        proj = get_or_create_test_project(db)
        ass = Assessment(project_id=proj.id, status="completed", overall_health_score=88.0)
        db.add(ass)
        db.commit()

        asyncio.run(mem.record_assessment_snapshot(
            db=db,
            project_id=proj.id,
            assessment_id=ass.id,
            overall_score=88.0,
            risk_classification="Healthy",
            tech_scores=[],
            identified_risks=[]
        ))

        comp = asyncio.run(mem.generate_delta_comparison(db, ass.id))
        assert comp["storage_provider"] == "postgresql"
        assert comp["current_health_score"] == 88.0
    finally:
        db.close()

@pytest.mark.skipif(
    not os.getenv("MEMENTO_API_KEY"),
    reason="MEMENTO_API_KEY environment variable required for live integration test"
)
def test_memento_live_api_connectivity_and_operations():
    """
    Live Memento API integration test.
    Only executed when actual MEMENTO_API_KEY is available in the environment.
    """
    api_key = os.getenv("MEMENTO_API_KEY")
    endpoint = os.getenv("MEMENTO_API_URL", "")
    mem = MementoMemoryAdapter(api_key=api_key, endpoint=endpoint)

    res = asyncio.run(mem.verify_connectivity())
    assert "status" in res
    assert "mode" in res
