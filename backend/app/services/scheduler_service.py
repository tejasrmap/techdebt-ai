import logging
import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, Callable, Any, Dict, List
from croniter import croniter
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import SessionLocal
from app.models.all_models import (
    ScheduledReview, ReviewJob, Project, TechnologyScore,
    RiskFinding, EvidenceSource, Assessment, AuditLog, DistributedLock,
    RepositoryConnection, RepositoryAnalysisSnapshot, CodeFinding
)
from app.services.firecrawl_service import FirecrawlIntelligenceService
from app.services.ai_analyzer import AITechnologyDebtAnalyzer
from app.services.historical_memory_adapter import HistoricalAssessmentMemoryAdapter
from app.services.memento_adapter import MementoMemoryAdapter

logger = logging.getLogger(__name__)

class StaleGenerationWriteError(RuntimeError):
    """Raised when a worker attempts a database write with an invalid, expired, or superseded fencing lease."""
    pass

scheduler = BackgroundScheduler()

def acquire_distributed_lock(db: Session, lock_key: str, owner_id: str, ttl_seconds: int = 600) -> bool:
    """
    Atomically acquire a distributed lock in the database.
    Prevents simultaneous execution across multiple worker processes.
    Expired locks are reclaimed atomically via conditional SQL UPDATE with generation increment.
    """
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=ttl_seconds)

    try:
        # 1. Attempt atomic conditional UPDATE to reclaim expired lock
        updated = (
            db.query(DistributedLock)
            .filter(
                DistributedLock.lock_key == lock_key,
                DistributedLock.expires_at <= now
            )
            .update(
                {
                    "owner_id": owner_id,
                    "acquired_at": now,
                    "expires_at": expires_at,
                    "generation": DistributedLock.generation + 1
                },
                synchronize_session=False
            )
        )
        if updated > 0:
            db.commit()
            return True

        # 2. Check if an active, unexpired lock exists
        active = (
            db.query(DistributedLock)
            .filter(
                DistributedLock.lock_key == lock_key,
                DistributedLock.expires_at > now
            )
            .first()
        )
        if active:
            db.rollback()
            return False

        # 3. No lock exists at all: atomically INSERT new lock with generation = 1
        new_lock = DistributedLock(
            lock_key=lock_key,
            owner_id=owner_id,
            generation=1,
            acquired_at=now,
            expires_at=expires_at
        )
        db.add(new_lock)
        db.commit()
        return True
    except IntegrityError:
        # Concurrent worker inserted at the exact same time
        db.rollback()
        return False
    except Exception as e:
        logger.warning(f"Error acquiring lock {lock_key}: {e}")
        db.rollback()
        return False

def get_lock_generation(db: Session, lock_key: str, owner_id: str) -> Optional[int]:
    """Retrieve the current generation fencing token for a held lock."""
    lock = (
        db.query(DistributedLock)
        .filter(
            DistributedLock.lock_key == lock_key,
            DistributedLock.owner_id == owner_id
        )
        .first()
    )
    gen = lock.generation if lock else None
    db.commit()
    return gen

def assert_valid_fenced_lease_transactional(
    db: Session,
    lock_key: str,
    owner_id: str,
    expected_generation: int
) -> DistributedLock:
    """
    Genuine database-level transactional fencing guard for protected writes.
    Locks the distributed lock row with SELECT ... FOR UPDATE (in PostgreSQL)
    and verifies that the current transaction holds a valid, unexpired lease matching the expected generation.
    Raises StaleGenerationWriteError if the lock has been reclaimed, superseded, expired, or stolen.
    Fails closed: Any database error or mismatch rolls back and raises StaleGenerationWriteError.
    """
    now = datetime.utcnow()
    try:
        query = db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key)
        # Apply row-level locking for PostgreSQL / dialects supporting FOR UPDATE
        if db.bind and db.bind.dialect.name != "sqlite":
            query = query.with_for_update()
        lock_rec = query.first()
    except Exception as e:
        logger.error(f"Database error during transactional fencing validation for lock '{lock_key}': {e}")
        db.rollback()
        raise StaleGenerationWriteError(f"Database error during fencing validation for lock '{lock_key}': {e}") from e

    if not lock_rec:
        db.rollback()
        raise StaleGenerationWriteError(
            f"Fencing token validation failed: Lock record '{lock_key}' not found in database."
        )
    if lock_rec.owner_id != owner_id:
        db.rollback()
        raise StaleGenerationWriteError(
            f"Fencing token validation failed for lock '{lock_key}': Worker '{owner_id}' "
            f"lost ownership to '{lock_rec.owner_id}'."
        )
    if lock_rec.generation != expected_generation:
        db.rollback()
        raise StaleGenerationWriteError(
            f"Fencing token validation failed for lock '{lock_key}': Worker '{owner_id}' generation "
            f"({expected_generation}) superseded by generation {lock_rec.generation}."
        )
    if lock_rec.expires_at <= now:
        db.rollback()
        raise StaleGenerationWriteError(
            f"Fencing token validation failed for lock '{lock_key}': Lease for worker '{owner_id}' "
            f"(generation {expected_generation}) expired at {lock_rec.expires_at} (current {now})."
        )
    return lock_rec

def verify_ownership_short_transaction(
    db: Optional[Session],
    lock_key: str,
    owner_id: str,
    expected_generation: int,
    use_isolated_session: bool = False
) -> None:
    """
    Validate worker ownership without prematurely committing or terminating the caller's session.
    
    CRITICAL RELIABILITY PROPERTY:
    Never executes db.commit() on the caller's session! This ensures that pending uncommitted
    business records (assessment updates, scores, evidence, risks, historical snapshots) are
    NEVER prematurely committed, and active row locks (SELECT ... FOR UPDATE) remain held.
    
    When db is None or use_isolated_session=True, a dedicated short-lived read session is created
    and immediately closed in finally, ensuring zero side-effects on caller transactions.
    
    Fails closed: Any database query error or ownership/generation mismatch raises
    StaleGenerationWriteError immediately.
    """
    now = datetime.utcnow()
    owns_session = False
    active_db = db

    if active_db is None:
        active_db = SessionLocal()
        owns_session = True
    elif use_isolated_session:
        from sqlalchemy.orm import sessionmaker
        bound_engine = db.get_bind()
        active_db = sessionmaker(autocommit=False, autoflush=False, bind=bound_engine)()
        owns_session = True

    try:
        lock_rec = (
            active_db.query(DistributedLock)
            .filter(DistributedLock.lock_key == lock_key)
            .first()
        )
    except Exception as e:
        logger.error(f"Database error during short ownership verification for lock '{lock_key}': {e}")
        if owns_session:
            active_db.rollback()
        raise StaleGenerationWriteError(f"Database error during ownership verification for lock '{lock_key}': {e}") from e
    finally:
        if owns_session:
            active_db.close()

    if not lock_rec:
        raise StaleGenerationWriteError(
            f"Fencing token validation failed: Lock record '{lock_key}' not found in database."
        )
    if lock_rec.owner_id != owner_id:
        raise StaleGenerationWriteError(
            f"Fencing token validation failed for lock '{lock_key}': Worker '{owner_id}' "
            f"lost ownership to '{lock_rec.owner_id}'."
        )
    if lock_rec.generation != expected_generation:
        raise StaleGenerationWriteError(
            f"Fencing token validation failed for lock '{lock_key}': Worker '{owner_id}' generation "
            f"({expected_generation}) superseded by generation {lock_rec.generation}."
        )
    if lock_rec.expires_at <= now:
        raise StaleGenerationWriteError(
            f"Fencing token validation failed for lock '{lock_key}': Lease for worker '{owner_id}' "
            f"(generation {expected_generation}) expired at {lock_rec.expires_at} (current {now})."
        )

def verify_ownership_standalone(
    lock_key: str,
    owner_id: str,
    expected_generation: int
) -> None:
    """
    Validate worker ownership using an isolated short-lived read session.
    Guarantees no interaction or side-effects on any caller transaction.
    """
    verify_ownership_short_transaction(
        db=None,
        lock_key=lock_key,
        owner_id=owner_id,
        expected_generation=expected_generation,
        use_isolated_session=True
    )

def assert_valid_fenced_lease(
    db: Session,
    lock_key: str,
    owner_id: str,
    expected_generation: int
) -> bool:
    """
    Verify that the worker holds a valid, unexpired lease with the expected generation fencing token.
    Uses short transaction without holding row locks.
    Raises StaleGenerationWriteError on lease loss or generation mismatch to abort stale writes.
    """
    verify_ownership_short_transaction(db, lock_key, owner_id, expected_generation)
    return True

def release_distributed_lock(
    db: Session,
    lock_key: str,
    owner_id: str,
    expected_generation: Optional[int] = None
) -> bool:
    """Release an active distributed lock owned by owner_id and matching expected_generation."""
    try:
        query = db.query(DistributedLock).filter(
            DistributedLock.lock_key == lock_key,
            DistributedLock.owner_id == owner_id
        )
        if expected_generation is not None:
            query = query.filter(DistributedLock.generation == expected_generation)

        deleted = query.delete(synchronize_session=False)
        db.commit()
        return deleted > 0
    except Exception as e:
        logger.warning(f"Error releasing lock {lock_key}: {e}")
        db.rollback()
        return False

def renew_distributed_lock(
    db: Session,
    lock_key: str,
    owner_id: str,
    extension_seconds: int = 600,
    expected_generation: Optional[int] = None
) -> bool:
    """
    Extend the expiration time of an active lease held by owner_id and matching expected_generation.
    Ensures safe lock renewal for reviews executing longer than lease TTL (e.g. > 10 minutes).
    """
    now = datetime.utcnow()
    new_expires_at = now + timedelta(seconds=extension_seconds)
    try:
        query = db.query(DistributedLock).filter(
            DistributedLock.lock_key == lock_key,
            DistributedLock.owner_id == owner_id,
            DistributedLock.expires_at > now
        )
        if expected_generation is not None:
            query = query.filter(DistributedLock.generation == expected_generation)

        updated = query.update({"expires_at": new_expires_at}, synchronize_session=False)
        db.commit()
        return updated > 0
    except Exception as e:
        logger.warning(f"Error renewing lease {lock_key} for {owner_id}: {e}")
        db.rollback()
        return False

import threading

class LockHeartbeat:
    """
    Background heartbeat thread that periodically renews the distributed lease.
    If renewal fails (indicating lost lock ownership, generation mismatch, or persistent database failure
    exceeding the bounded retry budget), sets `lost_lock_event`, enabling the worker
    to safely abort assessment execution immediately without committing stale results.
    """
    def __init__(
        self,
        lock_key: str,
        worker_id: str,
        interval: float = 15.0,
        lease_extension: int = 600,
        max_retries: int = 3,
        generation: Optional[int] = None,
        session_factory: Optional[Any] = None
    ):
        self.lock_key = lock_key
        self.worker_id = worker_id
        self.interval = float(interval)
        self.lease_extension = lease_extension
        self.max_retries = max_retries
        self.generation = generation
        self.session_factory = session_factory
        self.stop_event = threading.Event()
        self.lost_lock_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self):
        self.thread = threading.Thread(target=self._run, name=f"Heartbeat_{self.lock_key}", daemon=True)
        self.thread.start()

    def _run(self):
        import time
        while not self.stop_event.wait(self.interval):
            if self.stop_event.is_set():
                break

            renewal_successful = False
            # Bounded retry loop for transient database connectivity or locking errors
            for attempt in range(self.max_retries):
                if self.stop_event.is_set():
                    return
                db = (self.session_factory or SessionLocal)()
                try:
                    # Verify lock state and ownership in database
                    now = datetime.utcnow()
                    lock_rec = (
                        db.query(DistributedLock)
                        .filter(DistributedLock.lock_key == self.lock_key)
                        .first()
                    )

                    # If lock record is gone, owned by another worker, has a mismatched generation, or expired:
                    if (
                        not lock_rec
                        or lock_rec.owner_id != self.worker_id
                        or (self.generation is not None and lock_rec.generation != self.generation)
                        or lock_rec.expires_at <= now
                    ):
                        logger.error(
                            f"CRITICAL: Worker {self.worker_id} verified lost ownership for lease {self.lock_key}! "
                            f"(Record owner: {lock_rec.owner_id if lock_rec else 'None'}, "
                            f"generation: {lock_rec.generation if lock_rec else 'None'}, "
                            f"expected_generation: {self.generation}, "
                            f"expired: {lock_rec.expires_at <= now if lock_rec else True})"
                        )
                        self.lost_lock_event.set()
                        return

                    # Extend lease atomically with generation verification
                    renewed = renew_distributed_lock(
                        db,
                        self.lock_key,
                        self.worker_id,
                        extension_seconds=self.lease_extension,
                        expected_generation=self.generation
                    )
                    if not renewed:
                        logger.error(
                            f"CRITICAL: Worker {self.worker_id} failed atomic lease renewal for {self.lock_key}."
                        )
                        self.lost_lock_event.set()
                        return

                    renewal_successful = True
                    break
                except Exception as e:
                    logger.warning(
                        f"Transient DB exception during lock heartbeat attempt {attempt + 1}/{self.max_retries} "
                        f"for {self.lock_key}: {e}"
                    )
                    db.rollback()
                    time.sleep(0.2 * (attempt + 1))
                finally:
                    db.close()

            # If bounded retries exhausted without safe renewal, treat lock as lost
            if not renewal_successful and not self.stop_event.is_set():
                logger.error(
                    f"CRITICAL: Worker {self.worker_id} failed to renew lease {self.lock_key} "
                    f"after {self.max_retries} attempts! Marking lock as lost to protect data safety."
                )
                self.lost_lock_event.set()
                break

    def is_lock_lost(self) -> bool:
        return self.lost_lock_event.is_set()

    def mark_lost(self):
        """Allows tests or external events to signal that lock ownership was lost."""
        self.lost_lock_event.set()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

def validate_and_compute_next_run(cron_expr: str) -> datetime:
    """Validate cron expression and return next execution datetime."""
    if not croniter.is_valid(cron_expr):
        raise ValueError(f"Invalid cron expression: '{cron_expr}'")
    iter_obj = croniter(cron_expr, datetime.utcnow())
    return iter_obj.get_next(datetime)

async def execute_project_review(
    project_id: str,
    trigger_type: str = "scheduled",
    db_session: Optional[Session] = None,
    enforce_org_id: Optional[str] = None,
    should_abort: Optional[Callable[[], bool]] = None,
    fencing_key: Optional[str] = None,
    fencing_owner: Optional[str] = None,
    fencing_generation: Optional[int] = None,
    stage_hook: Optional[Callable[[str], None]] = None
) -> Assessment:
    """Core review pipeline executed manually or via scheduler with 10 transactional fencing checkpoints."""
    close_db = False
    if db_session is None:
        db = SessionLocal()
        close_db = True
    else:
        db = db_session

    def verify_fenced_lease_stage(stage_name: str):
        """Transactional fencing token and heartbeat lease validation."""
        if should_abort and should_abort():
            logger.error(
                f"Execution aborted at stage '{stage_name}' for project {project_id}: "
                f"Distributed lock ownership lost or cancelled."
            )
            raise RuntimeError(f"Review aborted at stage '{stage_name}': Worker lost distributed lock ownership")
        if fencing_key and fencing_owner and fencing_generation is not None:
            # For intermediate stages before final persistence (e.g. 2_ through 7_), use an isolated
            # session so caller's db connection remains completely detached from long network I/O.
            # For final protected persistence (stage 8, 9, 10), verify on caller session without committing.
            is_intermediate = stage_name.startswith(("2_", "3_", "4_", "5_", "6_", "7_"))
            verify_ownership_short_transaction(
                db=db,
                lock_key=fencing_key,
                owner_id=fencing_owner,
                expected_generation=fencing_generation,
                use_isolated_session=is_intermediate
            )
        if stage_hook:
            stage_hook(stage_name)

    try:
        query = db.query(Project).filter(Project.id == project_id)
        if enforce_org_id:
            query = query.filter(Project.org_id == enforce_org_id)
        project = query.first()
        db.commit()  # Close read transaction immediately
        if not project:
            raise ValueError(f"Project {project_id} not found or unauthorized")

        from app.services.integration_config_service import (
            get_firecrawl_service_for_org,
            get_ai_analyzer_for_org,
            get_historical_memory_adapter_for_org
        )

        firecrawl_svc = get_firecrawl_service_for_org(project.org_id, db)
        ai_analyzer = get_ai_analyzer_for_org(project.org_id, db)
        historical_memory_adapter = get_historical_memory_adapter_for_org(project.org_id, db)

        # Stage 1: Checkpoint before creating Assessment record
        verify_fenced_lease_stage("1_before_assessment_creation")
        if fencing_key and fencing_owner and fencing_generation is not None:
            assert_valid_fenced_lease_transactional(db, fencing_key, fencing_owner, fencing_generation)
        assessment = Assessment(
            project_id=project_id,
            trigger_type=trigger_type,
            status="processing",
            fencing_generation=fencing_generation or 1,
            overall_health_score=None,
            risk_classification="Healthy",
            confidence_level="High"
        )
        db.add(assessment)
        db.commit()
        db.refresh(assessment)
        db.commit()  # Commit immediately to release row locks before network calls

        # Stage 2: Checkpoint before beginning technology iteration
        verify_fenced_lease_stage("2_before_technology_iteration")
        total_scores = []
        all_risks = []
        tech_score_records = []
        pending_score_records = []
        pending_evidence_records = []
        pending_risk_records = []

        for p_tech in project.project_technologies:
            tech = p_tech.technology

            # Stage 3: Checkpoint before intelligence gathering for each technology
            verify_fenced_lease_stage(f"3_before_intelligence_{tech.name}")
            intel = await firecrawl_svc.gather_technology_intelligence(
                tech_name=tech.name,
                ecosystem=tech.ecosystem,
                installed_version=p_tech.installed_version
            )

            # Stage 4: Checkpoint after intelligence gathering
            verify_fenced_lease_stage(f"4_after_intelligence_{tech.name}")

            # Update tech with latest registry version if unknown
            if tech.latest_stable_version == "unknown" and intel.get("latest_stable_version"):
                if fencing_key and fencing_owner and fencing_generation is not None:
                    assert_valid_fenced_lease_transactional(db, fencing_key, fencing_owner, fencing_generation)
                tech.latest_stable_version = intel["latest_stable_version"]
                tech.is_deprecated = intel.get("is_deprecated", False)
                db.commit()

            # Stage 5: Checkpoint before running AI debt analysis
            verify_fenced_lease_stage(f"5_before_ai_analysis_{tech.name}")
            analysis = await ai_analyzer.analyze_technology(
                tech_name=tech.name,
                installed_version=p_tech.installed_version,
                latest_version=intel.get("latest_stable_version", tech.latest_stable_version),
                is_deprecated=intel.get("is_deprecated", tech.is_deprecated),
                evidence_sources=intel.get("evidence_sources", []),
                project_context=project.description
            )

            # Stage 6: Checkpoint after AI analysis and before saving tech scores/findings
            verify_fenced_lease_stage(f"6_after_ai_analysis_{tech.name}")

            overall_tech_score = analysis.get("overall_score", 85.0)
            total_scores.append(overall_tech_score)

            # Prepare TechnologyScore record for guarded persistence
            score_rec = TechnologyScore(
                assessment_id=assessment.id,
                technology_id=tech.id,
                overall_score=overall_tech_score,
                risk_classification=analysis.get("risk_classification", "Good"),
                maintenance_health=analysis.get("maintenance_health", 90.0),
                security_exposure=analysis.get("security_exposure", 95.0),
                version_currency=analysis.get("version_currency", 90.0),
                community_activity=analysis.get("community_activity", 85.0),
                documentation_quality=analysis.get("documentation_quality", 85.0),
                ecosystem_compatibility=analysis.get("ecosystem_compatibility", 90.0),
                sustainability=analysis.get("sustainability", 90.0),
                upgrade_complexity=analysis.get("upgrade_complexity", 90.0),
                confidence_level=analysis.get("confidence_level", "High"),
                recommended_action=analysis.get("recommended_action", ""),
                upgrade_complexity_level=analysis.get("upgrade_complexity_level", "Low"),
                notes="; ".join(analysis.get("identified_problems", []))
            )
            pending_score_records.append(score_rec)

            # Prepare Evidence Sources
            for ev in intel.get("evidence_sources", []):
                ev_rec = EvidenceSource(
                    assessment_id=assessment.id,
                    technology_id=tech.id,
                    url=ev.get("url", ""),
                    title=ev.get("title", tech.name),
                    source_type=ev.get("source_type", "documentation"),
                    reliability_score=ev.get("reliability_score", 1.0),
                    publication_date=ev.get("publication_date"),
                    is_official=ev.get("is_official", True),
                    snippet=ev.get("snippet", "")
                )
                pending_evidence_records.append(ev_rec)

            # Prepare Risk Findings (with deterministic fingerprint & triage carry-forward)
            for r in analysis.get("risks", []):
                r_title = r.get("title", "")
                fp = hashlib.sha256(
                    f"{project.id}:{tech.id}:{r_title.strip().lower()}".encode("utf-8")
                ).hexdigest()
                prior_triaged = (
                    db.query(RiskFinding)
                    .filter(
                        RiskFinding.project_id == project.id,
                        RiskFinding.fingerprint == fp,
                        RiskFinding.status.in_(["Accepted Risk", "Mitigated"]),
                    )
                    .order_by(RiskFinding.created_at.desc())
                    .first()
                )
                risk_rec = RiskFinding(
                    assessment_id=assessment.id,
                    technology_id=tech.id,
                    project_id=project.id,
                    severity=r.get("severity", "Medium"),
                    title=r_title,
                    description=r.get("description", ""),
                    business_impact=r.get("business_impact", ""),
                    technical_impact=r.get("technical_impact", ""),
                    estimated_remediation_hours=float(r.get("estimated_remediation_hours", 4.0) or 4.0),
                    fingerprint=fp,
                    status=prior_triaged.status if prior_triaged else "Open",
                    assigned_to=prior_triaged.assigned_to if prior_triaged else None,
                    resolution_notes=prior_triaged.resolution_notes if prior_triaged else None,
                    resolved_at=prior_triaged.resolved_at if prior_triaged else None,
                )
                pending_risk_records.append(risk_rec)
                all_risks.append(r)

            tech_score_records.append({
                "technology_name": tech.name,
                "score": overall_tech_score,
                "classification": analysis.get("risk_classification", "Good")
            })

        # Stage 7: Checkpoint before composite project health score calculation
        verify_fenced_lease_stage("7_before_score_calculation")

        # Commercial Source Code Analysis (consumes durable RepositoryAnalysisSnapshot first,
        # falling back to local_path if needed and persisting a snapshot so local_path is never required again)
        repo_conn = db.query(RepositoryConnection).filter(RepositoryConnection.project_id == project.id).first()
        latest_snapshot = (
            db.query(RepositoryAnalysisSnapshot)
            .filter(RepositoryAnalysisSnapshot.project_id == project.id)
            .order_by(RepositoryAnalysisSnapshot.created_at.desc())
            .first()
        )
        code_metrics = None
        code_findings_records = []
        raw_code_findings = []
        snapshot_id: Optional[str] = None
        snapshot_commit_sha: Optional[str] = repo_conn.commit_sha if repo_conn else None
        snapshot_analyzer_version: Optional[str] = None

        if latest_snapshot is not None:
            snapshot_id = latest_snapshot.id
            snapshot_commit_sha = latest_snapshot.commit_sha
            snapshot_analyzer_version = latest_snapshot.analyzer_version
            extra_fm = latest_snapshot.file_metrics_json or {}
            code_metrics = {
                "lines_of_code": latest_snapshot.lines_of_code or 0,
                "files_analyzed": latest_snapshot.files_analyzed or 0,
                "files_examined": latest_snapshot.files_examined or 0,
                "files_excluded": latest_snapshot.files_excluded or 0,
                "test_files_count": latest_snapshot.test_files_count or 0,
                "avg_cyclomatic_complexity": latest_snapshot.avg_cyclomatic_complexity or 1.0,
                "max_cyclomatic_complexity": latest_snapshot.max_cyclomatic_complexity or 1,
                "code_duplication_percentage": latest_snapshot.code_duplication_percentage or 0.0,
                "maintainability_index": latest_snapshot.maintainability_index if latest_snapshot.maintainability_index is not None else 85.0,
                "coverage_percentage": extra_fm.get("coverage_percentage"),
            }
            for cf_dict in (latest_snapshot.code_findings_json or []):
                raw_code_findings.append(cf_dict)
                rec = CodeFinding(
                    assessment_id=assessment.id,
                    project_id=project.id,
                    file_path=cf_dict.get("file_path", ""),
                    line_start=cf_dict.get("line_start", 1),
                    line_end=cf_dict.get("line_end", 1),
                    rule_id=cf_dict.get("rule_id", "GENERIC_FINDING"),
                    category=cf_dict.get("category", "maintainability"),
                    severity=cf_dict.get("severity", "Medium"),
                    confidence=cf_dict.get("confidence", "High"),
                    title=cf_dict.get("title", ""),
                    explanation=cf_dict.get("explanation", ""),
                    technical_evidence=cf_dict.get("technical_evidence", ""),
                    why_it_matters=cf_dict.get("why_it_matters", ""),
                    recommended_remediation=cf_dict.get("recommended_remediation", ""),
                    estimated_remediation_hours=float(cf_dict.get("estimated_remediation_hours", 1.0) or 1.0),
                    is_auto_verifiable=bool(cf_dict.get("is_auto_verifiable", False)),
                    status="Open",
                    analyzer_name="SourceCodeAnalyzer",
                    analyzer_version=snapshot_analyzer_version or "v3.1.0",
                )
                code_findings_records.append(rec)
        elif repo_conn and repo_conn.local_path and os.path.exists(repo_conn.local_path):
            try:
                from app.services.source_code_analyzer import SourceCodeAnalyzer
                analyzer = SourceCodeAnalyzer()
                analysis_res = analyzer.analyze_directory(repo_conn.local_path)
                snapshot_analyzer_version = "v3.1.0"
                snapshot_commit_sha = repo_conn.commit_sha or f"local:{project.id[:16]}"
                code_metrics = {
                    "lines_of_code": analysis_res.total_lines_of_code,
                    "files_analyzed": analysis_res.total_files,
                    "test_files_count": analysis_res.test_files_count,
                    "avg_cyclomatic_complexity": analysis_res.avg_complexity,
                    "max_cyclomatic_complexity": analysis_res.max_complexity,
                    "code_duplication_percentage": analysis_res.code_duplication_percentage,
                    "maintainability_index": analysis_res.maintainability_index,
                }
                for cf in analysis_res.findings:
                    cf_dict = cf.to_dict()
                    raw_code_findings.append(cf_dict)
                    rec = CodeFinding(
                        assessment_id=assessment.id,
                        project_id=project.id,
                        file_path=cf.file_path,
                        line_start=cf.line_start,
                        line_end=cf.line_end,
                        rule_id=cf.rule_id,
                        category=cf.category,
                        severity=cf.severity,
                        confidence=cf.confidence,
                        title=cf.title,
                        explanation=cf.explanation,
                        technical_evidence=cf.technical_evidence,
                        why_it_matters=cf.why_it_matters,
                        recommended_remediation=cf.recommended_remediation,
                        estimated_remediation_hours=cf.estimated_remediation_hours,
                        is_auto_verifiable=cf.is_auto_verifiable,
                        status="Open",
                        analyzer_name="SourceCodeAnalyzer",
                        analyzer_version=snapshot_analyzer_version,
                    )
                    code_findings_records.append(rec)

                # Persist durable snapshot so future assessments never depend on local_path
                auto_snap = RepositoryAnalysisSnapshot(
                    org_id=project.org_id,
                    project_id=project.id,
                    repo_connection_id=repo_conn.id,
                    provider=repo_conn.provider or "local_upload",
                    branch=repo_conn.selected_branch or repo_conn.branch or "main",
                    commit_sha=snapshot_commit_sha,
                    analyzer_version=snapshot_analyzer_version,
                    files_examined=analysis_res.total_files,
                    files_analyzed=analysis_res.total_files,
                    files_excluded=0,
                    lines_of_code=analysis_res.total_lines_of_code,
                    code_metrics_json={
                        "test_files_count": analysis_res.test_files_count,
                        "maintainability_index": analysis_res.maintainability_index,
                        "avg_cyclomatic_complexity": analysis_res.avg_complexity,
                        "max_cyclomatic_complexity": analysis_res.max_complexity,
                        "code_duplication_percentage": analysis_res.code_duplication_percentage,
                        "defect_density": analysis_res.defect_density,
                        "quality_grade": analysis_res.quality_grade,
                        "hotspots": analysis_res.hotspots,
                        "severity_breakdown": analysis_res.severity_breakdown,
                        "category_remediation_hours": analysis_res.category_remediation_hours,
                    },
                    findings_json=raw_code_findings,
                )
                db.add(auto_snap)
                db.flush()
                snapshot_id = auto_snap.id
            except Exception as code_err:
                logger.warning(f"Source code analysis failed for project {project.id}: {code_err}")

        # Check for empty inventory (no technologies and no source code)
        if not total_scores and not code_metrics:
            if fencing_key and fencing_owner and fencing_generation is not None:
                assert_valid_fenced_lease_transactional(db, fencing_key, fencing_owner, fencing_generation)
            updated_rows = (
                db.query(Assessment)
                .filter(
                    Assessment.id == assessment.id,
                    Assessment.fencing_generation <= (fencing_generation or 1)
                )
                .update({
                    "overall_health_score": None,
                    "risk_classification": "Not Assessed",
                    "confidence_level": "Unknown",
                    "status": "completed",
                    "summary": "No technologies or source code detected in project inventory. Please add dependencies or connect a repository.",
                    "fencing_generation": fencing_generation or 1
                }, synchronize_session=False)
            )
            if updated_rows == 0:
                db.rollback()
                raise StaleGenerationWriteError("Assessment stale write rejected for empty inventory.")
            db.query(Project).filter(Project.id == project.id).update({
                "last_assessment_date": datetime.utcnow()
            })

            # Stage 9 (empty inventory): Checkpoint before historical snapshot
            verify_fenced_lease_stage("9_before_historical_snapshot_empty")

            await historical_memory_adapter.record_assessment_snapshot(
                db=db,
                project_id=project.id,
                assessment_id=assessment.id,
                overall_score=None,
                risk_classification="Not Assessed",
                tech_scores=[],
                identified_risks=[],
                project_name=project.name,
                fencing_generation=fencing_generation or 1,
                auto_commit=False
            )

            # Single atomic commit for empty inventory assessment results and snapshot
            db.commit()
            db.refresh(assessment)
            try:
                from app.services.billing_service import BillingService
                BillingService.record_usage(db, project.org_id, "monthly_assessments", 1)
            except Exception as b_err:
                logger.warning(f"Billing usage record warning on empty inventory: {b_err}")
            return assessment

        # Commercial 10-Dimension Technical Debt Scoring
        from app.services.debt_scoring_engine import CommercialDebtScoringEngine
        debt_calc = CommercialDebtScoringEngine.calculate_project_debt(
            code_metrics=code_metrics,
            tech_scores=[
                {
                    "maintenance_health": s.maintenance_health,
                    "version_currency": s.version_currency,
                    "security_exposure": s.security_exposure,
                    "documentation_quality": s.documentation_quality,
                    "sustainability": s.sustainability,
                    "upgrade_complexity": s.upgrade_complexity,
                }
                for s in pending_score_records
            ] if pending_score_records else None,
            risk_findings=all_risks,
            code_findings=raw_code_findings
        )

        avg_score = debt_calc["overall_health_score"]
        project_classification = debt_calc["risk_classification"]

        # Stage 8: Checkpoint immediately before persisting assessment results
        verify_fenced_lease_stage("8_before_assessment_persistence")

        # Step 1-5: Begin short transaction, acquire SELECT FOR UPDATE, verify owner, generation, expiration
        if fencing_key and fencing_owner and fencing_generation is not None:
            assert_valid_fenced_lease_transactional(db, fencing_key, fencing_owner, fencing_generation)

        # Step 6: Persist all assessment results within this protected transaction
        updated_rows = (
            db.query(Assessment)
            .filter(
                Assessment.id == assessment.id,
                Assessment.fencing_generation <= (fencing_generation or 1)
            )
            .update({
                "overall_health_score": avg_score,
                "risk_classification": project_classification,
                "confidence_level": debt_calc["confidence_level"],
                "commit_sha": snapshot_commit_sha,
                "analyzer_version": snapshot_analyzer_version,
                "scoring_version": debt_calc["scoring_version"],
                "technical_debt_ratio": debt_calc["technical_debt_ratio"],
                "estimated_remediation_hours": debt_calc["estimated_remediation_hours"],
                "lines_of_code": debt_calc["lines_of_code"],
                "files_analyzed": debt_calc["files_analyzed"],
                "code_maintainability_score": debt_calc["dimensional_scores"]["code_maintainability"],
                "architecture_score": debt_calc["dimensional_scores"]["architecture_quality"],
                "dependency_score": debt_calc["dimensional_scores"]["dependency_health"],
                "security_score": debt_calc["dimensional_scores"]["security_posture"],
                "test_quality_score": debt_calc["dimensional_scores"]["test_quality"],
                "documentation_score": debt_calc["dimensional_scores"]["documentation_quality"],
                "reliability_score": debt_calc["dimensional_scores"]["reliability"],
                "performance_score": debt_calc["dimensional_scores"]["performance_indicators"],
                "complexity_score": debt_calc["dimensional_scores"]["development_complexity"],
                "upgrade_risk_score": debt_calc["dimensional_scores"]["upgrade_risk"],
                "raw_output": {
                    "snapshot_id": snapshot_id,
                    "commit_sha": snapshot_commit_sha,
                    "analyzer_version": snapshot_analyzer_version,
                    "code_metrics": code_metrics,
                    "code_findings": raw_code_findings,
                    "dimensional_scores": debt_calc["dimensional_scores"],
                    "missing_signals": debt_calc.get("missing_signals", []),
                    "coverage_summary": debt_calc.get("coverage_summary", {}),
                },
                "status": "completed",
                "summary": (
                    f"Commercial assessment completed (engine {debt_calc['scoring_version']}). "
                    f"Evaluated {len(total_scores)} technologies and {debt_calc['files_analyzed']} source files ({debt_calc['lines_of_code']} LOC). "
                    f"Overall score {avg_score}/100 ({project_classification}) with {debt_calc['technical_debt_ratio']}% TDR. "
                    f"Identified {len(all_risks)} dependency risks and {len(code_findings_records)} code findings ({debt_calc['estimated_remediation_hours']}h remediation)."
                ),
                "fencing_generation": fencing_generation or 1
            }, synchronize_session=False)
        )
        if updated_rows == 0:
            db.rollback()
            raise StaleGenerationWriteError(
                f"Assessment {assessment.id} stale write rejected: current generation {fencing_generation} "
                f"superseded by a newer assessment commit."
            )

        # Persist technology scores, evidence, risks, and code findings within this short guarded transaction
        for s in pending_score_records:
            db.add(s)
        for ev in pending_evidence_records:
            db.add(ev)
        for rf in pending_risk_records:
            db.add(rf)
        for cf_rec in code_findings_records:
            db.add(cf_rec)

        db.query(Project).filter(Project.id == project.id).update({
            "last_assessment_date": datetime.utcnow()
        })

        # Stage 9: Checkpoint immediately before historical snapshot creation
        verify_fenced_lease_stage("9_before_historical_snapshot")

        # Step 7: Persist historical snapshot within the SAME protected transaction (auto_commit=False)
        await historical_memory_adapter.record_assessment_snapshot(
            db=db,
            project_id=project.id,
            assessment_id=assessment.id,
            overall_score=avg_score,
            risk_classification=project_classification,
            tech_scores=tech_score_records,
            identified_risks=all_risks,
            project_name=project.name,
            fencing_generation=fencing_generation or 1,
            auto_commit=False
        )

        # Step 8-9: Commit once atomically, releasing the row lock
        db.commit()
        db.refresh(assessment)

        # Commercial usage metering and notifications
        try:
            from app.services.billing_service import BillingService
            BillingService.record_usage(db, project.org_id, "monthly_assessments", 1)
        except Exception as b_err:
            logger.warning(f"Billing usage record warning: {b_err}")

        try:
            from app.services.notification_service import NotificationService
            NotificationService.create_notification(
                db=db,
                user_id=None,
                org_id=project.org_id,
                title=f"Assessment Complete: {project.name}",
                message=f"Score: {avg_score}/100. TDR: {debt_calc['technical_debt_ratio']}%. Estimated remediation: {debt_calc['estimated_remediation_hours']}h.",
                type="assessment_completed",
                link=f"/projects/{project.id}"
            )
        except Exception as n_err:
            logger.warning(f"Notification creation warning: {n_err}")

        # Stage 10: Post-commit completion boundary
        # The atomic database transaction has committed durably.
        # Ownership check at this point is safe, non-aborting telemetry logging.
        # Even if lease ownership expired or was transferred to another worker immediately
        # post-commit, this MUST NEVER fail or rollback the completed assessment.
        if stage_hook:
            try:
                stage_hook("10_post_completion_telemetry")
            except Exception as hook_err:
                logger.info(f"Post-completion stage hook executed: {hook_err}")

        if fencing_key and fencing_owner and fencing_generation is not None:
            try:
                verify_ownership_short_transaction(
                    db=None,
                    lock_key=fencing_key,
                    owner_id=fencing_owner,
                    expected_generation=fencing_generation,
                    use_isolated_session=True
                )
            except Exception as post_commit_err:
                logger.info(
                    f"Post-commit telemetry notice: Lock ownership or lease ended immediately after successful commit: {post_commit_err}. "
                    f"Assessment {assessment.id} remains durably committed as 'completed'."
                )

        return assessment

    except Exception as e:
        logger.error(f"Error executing assessment for project {project_id}: {e}")

        # If the assessment was already committed as "completed", do not rollback or alter to "failed"
        if 'assessment' in locals() and assessment:
            try:
                if getattr(assessment, "status", None) == "completed":
                    logger.info(
                        f"Assessment {assessment.id} was already durably committed as 'completed'. "
                        f"Suppressing failure mutation on post-commit exception: {e}"
                    )
                    return assessment
            except Exception:
                pass

        db.rollback()

        # CRITICAL: If lock ownership was lost or superseded, suppress status mutation to prevent stale commit
        is_stale_loss = (
            isinstance(e, StaleGenerationWriteError)
            or (should_abort and should_abort())
        )
        if not is_stale_loss and fencing_key and fencing_owner and fencing_generation is not None:
            try:
                verify_ownership_short_transaction(
                    db=None,
                    lock_key=fencing_key,
                    owner_id=fencing_owner,
                    expected_generation=fencing_generation,
                    use_isolated_session=True
                )
            except Exception:
                is_stale_loss = True

        if is_stale_loss:
            logger.warning(
                f"Worker lost lock or lease superseded for project {project_id}; "
                f"suppressing status write to prevent stale commit."
            )
            raise e

        if 'assessment' in locals() and assessment:
            try:
                if fencing_key and fencing_owner and fencing_generation is not None:
                    assert_valid_fenced_lease_transactional(db, fencing_key, fencing_owner, fencing_generation)
                (
                    db.query(Assessment)
                    .filter(
                        Assessment.id == assessment.id,
                        Assessment.fencing_generation <= (fencing_generation or 1)
                    )
                    .update({
                        "status": "failed",
                        "summary": f"Review failed: {str(e)}",
                        "fencing_generation": fencing_generation or 1
                    }, synchronize_session=False)
                )
                db.commit()
            except Exception:
                db.rollback()
        raise e
    finally:
        if close_db:
            db.close()

def run_scheduled_job(scheduled_review_id: str, max_retries: int = 2, worker_id: Optional[str] = None) -> bool:
    """
    APScheduler sync worker execution with atomic distributed locking, retries and status logging.
    Returns True if job was executed, False if skipped due to lock or inactive state.
    """
    db = SessionLocal()
    assigned_worker = worker_id or f"worker_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    lock_key = f"review_job_lock_{scheduled_review_id}"
    lock_acquired = False

    try:
        review = db.query(ScheduledReview).filter(ScheduledReview.id == scheduled_review_id).first()
        if not review or not review.is_active:
            return False

        # 1. Atomic distributed lock acquisition
        lock_acquired = acquire_distributed_lock(db, lock_key, assigned_worker, ttl_seconds=600)
        if not lock_acquired:
            logger.info(
                f"Duplicate review execution prevented for schedule {scheduled_review_id}: "
                f"Lock currently held by another worker process."
            )
            return False

        # 2. Secondary check for active Running job
        active_running = (
            db.query(ReviewJob)
            .filter(
                ReviewJob.scheduled_review_id == scheduled_review_id,
                ReviewJob.status == "Running",
                ReviewJob.started_at > datetime.utcnow() - timedelta(minutes=10)
            )
            .first()
        )
        if active_running:
            logger.info(f"Active running job {active_running.id} already in progress for schedule {scheduled_review_id}.")
            return False

        generation = get_lock_generation(db, lock_key, assigned_worker) or 1

        job = ReviewJob(
            scheduled_review_id=scheduled_review_id,
            status="Running",
            started_at=datetime.utcnow(),
            fencing_generation=generation
        )
        db.add(job)
        db.commit()

        # Start reliable lock heartbeat to extend lease periodically during execution with generation fencing
        heartbeat = LockHeartbeat(
            lock_key,
            assigned_worker,
            interval=15,
            lease_extension=600,
            generation=generation
        )
        heartbeat.start()

        # 3. Run review pipeline with retry backoff, fencing validation and lock loss detection
        success = False
        last_error = ""
        for attempt in range(max_retries):
            if heartbeat.is_lock_lost():
                last_error = "Distributed lock ownership was lost by this worker."
                logger.error(f"Scheduled review {scheduled_review_id} aborted: worker lost distributed lock.")
                break

            try:
                asyncio.run(execute_project_review(
                    project_id=review.project_id,
                    trigger_type="scheduled",
                    db_session=db,
                    should_abort=heartbeat.is_lock_lost,
                    fencing_key=lock_key,
                    fencing_owner=assigned_worker,
                    fencing_generation=generation
                ))
                success = True
                break
            except Exception as e:
                last_error = str(e)
                if heartbeat.is_lock_lost():
                    logger.error(f"Review job for {scheduled_review_id} safely aborted due to lost lock: {e}")
                    break
                logger.warning(f"Review job attempt {attempt + 1} failed for schedule {scheduled_review_id}: {e}")
                import time
                time.sleep(1.0 * (attempt + 1))

        if success:
            if heartbeat.is_lock_lost():
                logger.error(
                    f"Scheduled review {scheduled_review_id}: Review finished but worker lost lock before job status commit; "
                    f"suppressing job commit to prevent stale update."
                )
                db.rollback()
                return False

            try:
                assert_valid_fenced_lease_transactional(db, lock_key, assigned_worker, generation)
                job_updated = (
                    db.query(ReviewJob)
                    .filter(
                        ReviewJob.id == job.id,
                        ReviewJob.fencing_generation <= generation
                    )
                    .update({
                        "status": "Completed",
                        "completed_at": datetime.utcnow(),
                        "fencing_generation": generation
                    }, synchronize_session=False)
                )
                if job_updated == 0:
                    logger.warning(f"ReviewJob {job.id} superseded by newer generation.")
                    db.rollback()
                    return False

                review.last_run_at = datetime.utcnow()
                review.next_run_at = validate_and_compute_next_run(review.cron_expression)
                db.commit()
                return True
            except StaleGenerationWriteError as se:
                logger.warning(f"Suppressed ReviewJob completion commit due to stale generation: {se}")
                db.rollback()
                return False
        else:
            if heartbeat.is_lock_lost():
                logger.warning(
                    f"Scheduled review {scheduled_review_id}: Worker lost lock during execution; "
                    f"suppressing job status commit so active lock owner controls execution."
                )
                db.rollback()
                return False

            try:
                assert_valid_fenced_lease_transactional(db, lock_key, assigned_worker, generation)
                (
                    db.query(ReviewJob)
                    .filter(
                        ReviewJob.id == job.id,
                        ReviewJob.fencing_generation <= generation
                    )
                    .update({
                        "status": "Failed",
                        "error_message": f"Failed after {max_retries} attempts: {last_error}",
                        "completed_at": datetime.utcnow(),
                        "fencing_generation": generation
                    }, synchronize_session=False)
                )
                db.commit()
            except Exception as se:
                logger.warning(f"Suppressed ReviewJob failure commit due to lost lease or stale generation: {se}")
                db.rollback()
            return False

    except Exception as e:
        logger.error(f"Error in scheduled job execution: {e}")
        db.rollback()
        return False
    finally:
        lock_lost_state = False
        if 'heartbeat' in locals() and heartbeat:
            lock_lost_state = heartbeat.is_lock_lost()
            heartbeat.stop()

        if lock_acquired and not lock_lost_state:
            release_distributed_lock(
                db,
                lock_key,
                assigned_worker,
                expected_generation=locals().get("generation")
            )
        db.close()

def register_job_in_scheduler(schedule: ScheduledReview):
    """
    Register or update recurring job in APScheduler.
    Prevents duplicate scheduling or timer reset during periodic schedule synchronization.
    """
    job_id = f"review_job_{schedule.id}"
    try:
        existing = scheduler.get_job(job_id)
        if not schedule.is_active:
            if existing:
                scheduler.remove_job(job_id)
                logger.info(f"Removed inactive review job from scheduler: {job_id}")
            return

        trigger = CronTrigger.from_crontab(schedule.cron_expression)
        if existing:
            # If job already exists with matching trigger expression, avoid duplicate rescheduling
            if str(existing.trigger) == str(trigger):
                return
            scheduler.reschedule_job(job_id, trigger=trigger)
            logger.info(f"Updated recurring review job trigger: {job_id} ({schedule.cron_expression})")
        else:
            scheduler.add_job(
                run_scheduled_job,
                trigger=trigger,
                args=[schedule.id],
                id=job_id,
                replace_existing=True
            )
            logger.info(f"Registered recurring review job: {job_id} ({schedule.cron_expression})")
    except Exception as e:
        logger.error(f"Failed to register job {job_id}: {e}")
        raise ValueError(f"Failed to register recurring schedule in APScheduler: {str(e)}")

def unregister_job_from_scheduler(schedule_id: str):
    """Remove recurring job from APScheduler."""
    job_id = f"review_job_{schedule_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Removed review job from scheduler: {job_id}")

def restore_all_scheduled_jobs():
    """Restore all active recurring review jobs and prune stale inactive jobs."""
    db = SessionLocal()
    try:
        active_reviews = db.query(ScheduledReview).filter(ScheduledReview.is_active == True).all()
        active_job_ids = {f"review_job_{r.id}" for r in active_reviews}

        # Prune zombie APScheduler jobs that were deleted or deactivated in DB
        for existing_job in list(scheduler.get_jobs()):
            if existing_job.id.startswith("review_job_") and existing_job.id not in active_job_ids:
                try:
                    scheduler.remove_job(existing_job.id)
                    logger.info(f"Pruned stale scheduled job: {existing_job.id}")
                except Exception:
                    pass

        for r in active_reviews:
            try:
                r.next_run_at = validate_and_compute_next_run(r.cron_expression)
                register_job_in_scheduler(r)
            except Exception as e:
                logger.warning(f"Could not restore schedule {r.id}: {e}")
        db.commit()
        logger.info(f"Restored {len(active_reviews)} scheduled review jobs.")
    except Exception as e:
        logger.error(f"Error restoring scheduled jobs: {e}")
        db.rollback()
    finally:
        db.close()

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        restore_all_scheduled_jobs()
