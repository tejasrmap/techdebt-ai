# TechDebt AI v1.0.9 — Distributed Scheduler Architecture

**Component:** Background Review Worker & Distributed Locking Engine  
**Product:** TechDebt AI – Technology Debt Review Assistant  
**Release Version:** v1.0.9  

---

## 1. Architectural Philosophy

TechDebt AI executes recurring and on-demand technical debt assessments across repositories containing hundreds of dependencies. In an enterprise deployment with multiple web API containers and worker replicas, background scheduling adheres to strict reliability and consistency principles:

1. **Process Separation:** The web API process (`uvicorn app.main:app`) handles user requests and NEVER initializes APScheduler. Background execution is strictly isolated to dedicated worker processes (`python -m app.worker`).
2. **Atomic Mutual Exclusion:** Only one worker can execute an assessment for a given project at any point in time.
3. **No Long-Held Row Locks Across Network Calls:** External operations (Firecrawl crawling, Google Gemini / OpenAI inference) are executed strictly OUTSIDE open database transactions. Database connections remain idle with no row locks held during external I/O, guaranteeing that the background heartbeat thread can renew leases concurrently without lock contention.
4. **Genuine Transactional Fencing (`generation`):** Reclaiming an expired lease increments a monotonic generation counter. Protected writes are committed inside a transactional fencing guard (`assert_valid_fenced_lease_transactional`) using database row-level locking (`with_for_update`) and conditional SQL updates (`fencing_generation <= generation`).
5. **Fail-Closed Security:** If database fencing verification encounters any error, the system fails closed immediately (`StaleGenerationWriteError`), rolling back uncommitted mutations. Unsafe fallbacks to unlocked SELECT are strictly eliminated.
6. **Stale-Write Rejection & Status Suppression:** Stale workers holding expired or superseded leases are rejected at the database level. When an assessment fails due to lost lock ownership or lease supersession, failure status writes (`assessment.status = 'failed'`) are strictly suppressed, preventing stale workers from corrupting active executions.
7. **Safe Abort on Lost Lease:** If a worker loses its lease (e.g. network partition, GC pause, or lease expiry), it rolls back all uncommitted mutations and terminates safely.

---

## 2. Distributed Locking Table Schema

The `distributed_locks` table stores lease state:

```sql
CREATE TABLE distributed_locks (
    lock_key VARCHAR(255) PRIMARY KEY,
    owner_id VARCHAR(255) NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
    acquired_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);
```

Associated business tables carry `fencing_generation` columns (introduced in migration `002_transactional_fencing_and_memento_cleanup`):
- `assessments.fencing_generation` (INTEGER NOT NULL DEFAULT 1)
- `review_jobs.fencing_generation` (INTEGER NOT NULL DEFAULT 1)
- `historical_assessments.fencing_generation` (INTEGER NOT NULL DEFAULT 1)

---

## 3. Atomic Acquisition Algorithm

The acquisition mechanism in `backend/app/services/scheduler_service.py` prevents race conditions:

```python
def acquire_distributed_lock(db: Session, lock_key: str, owner_id: str, ttl_seconds: int = 600) -> bool:
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=ttl_seconds)

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
    active = db.query(DistributedLock).filter(
        DistributedLock.lock_key == lock_key,
        DistributedLock.expires_at > now
    ).first()
    if active:
        db.rollback()
        return False

    # 3. No lock exists: atomically INSERT new lock with generation = 1
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
```

---

## 4. Transactional Fencing and Stale-Write Protection

In v1.0.6, verification is strictly split between short non-blocking read checks and atomic guarded writes:

```python
def assert_valid_fenced_lease_transactional(
    db: Session,
    lock_key: str,
    owner_id: str,
    expected_generation: int
) -> DistributedLock:
    """
    Genuine database-level transactional fencing guard for protected writes.
    Locks the distributed lock row with SELECT ... FOR UPDATE (in PostgreSQL)
    and verifies that the current transaction holds a valid, unexpired lease.
    Fails closed: Any database error or mismatch rolls back and raises StaleGenerationWriteError.
    """
    now = datetime.utcnow()
    try:
        query = db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key)
        if db.bind and db.bind.dialect.name != "sqlite":
            query = query.with_for_update()
        lock_rec = query.first()
    except Exception as e:
        logger.error(f"Database error during transactional fencing validation: {e}")
        db.rollback()
        raise StaleGenerationWriteError(f"Database error during fencing validation: {e}") from e

    if not lock_rec:
        db.rollback()
        raise StaleGenerationWriteError(f"Lock '{lock_key}' not found.")
    if lock_rec.owner_id != owner_id:
        db.rollback()
        raise StaleGenerationWriteError(f"Lock lost to owner '{lock_rec.owner_id}'.")
    if lock_rec.generation != expected_generation:
        db.rollback()
        raise StaleGenerationWriteError(f"Generation superseded by {lock_rec.generation}.")
    if lock_rec.expires_at <= now:
        db.rollback()
        raise StaleGenerationWriteError("Lease expired.")
    return lock_rec

def verify_ownership_short_transaction(
    db: Optional[Session],
    lock_key: str,
    owner_id: str,
    expected_generation: int,
    use_isolated_session: bool = False
) -> None:
    """
    Validate worker ownership without prematurely committing or terminating caller's session.
    Never executes db.commit() on caller's session, guaranteeing that pending assessment
    scores, risks, and snapshots are NOT prematurely flushed, and row locks remain held.
    """
    now = datetime.utcnow()
    owns_session = False
    active_db = db
    if active_db is None or use_isolated_session:
        active_db = SessionLocal()
        owns_session = True

    try:
        lock_rec = active_db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).first()
    except Exception as e:
        if owns_session:
            active_db.rollback()
        raise StaleGenerationWriteError(f"Database error during ownership verification: {e}") from e
    finally:
        if owns_session:
            active_db.close()

    if not lock_rec or lock_rec.owner_id != owner_id or lock_rec.generation != expected_generation or lock_rec.expires_at <= now:
        raise StaleGenerationWriteError("Ownership verification failed.")
```

### Protected Atomic Write Pattern:
All assessment persistence, technology scores, risk findings, project timestamps, and historical memory snapshots run under the same guarded transaction and commit exactly ONCE:
```python
# Step 1: Acquire SELECT FOR UPDATE lock
assert_valid_fenced_lease_transactional(db, fencing_key, fencing_owner, fencing_generation)

# Step 2: Stage assessment update
db.query(Assessment).filter(Assessment.id == assessment.id, Assessment.fencing_generation <= generation).update(...)

# Step 3: Stage scores, evidence, risks, project timestamp
for s in pending_score_records: db.add(s)
for ev in pending_evidence_records: db.add(ev)
for rf in pending_risk_records: db.add(rf)
db.query(Project).filter(Project.id == project.id).update({"last_assessment_date": datetime.utcnow()})

# Step 4: Checkpoint before snapshot (non-committing)
verify_fenced_lease_stage("9_before_historical_snapshot")

# Step 5: Stage historical snapshot (auto_commit=False)
await historical_memory_adapter.record_assessment_snapshot(..., auto_commit=False)

# Step 6: Atomic single commit (releasing row lock)
db.commit()
db.refresh(assessment)

# Step 7: Post-commit completion boundary (telemetry & logging)
# The database transaction has permanently committed. Even if the lock lease expired
# or was transferred immediately post-commit, this stage NEVER aborts or fails the assessment.
verify_fenced_lease_stage("10_post_completion_telemetry")
return assessment
```
    Assessment.fencing_generation <= expected_generation
).update({ ... "fencing_generation": expected_generation })
```
If rows updated == 0, `StaleGenerationWriteError` is raised and the transaction is aborted.

---

## 5. LockHeartbeat Lifecycle & Safe Abort

The `LockHeartbeat` runs as a dedicated daemon thread on an independent database session:
- **Interval:** Every 15 seconds (configurable).
- **Extension:** Extends `expires_at` by 600 seconds (10 minutes) on each pulse.
- **Verification:** Verifies `owner_id == worker_id` AND `generation == expected_generation`.
- **Bounded Retries:** If transient database errors occur, it retries up to 3 times before setting `lost_lock_event.set()`.
- **Safe Abort:** The worker checks `heartbeat.is_lock_lost()` before and after every network call. Stale workers rolling back will never update `status = "failed"`, preventing interference with the newer active worker.
- **Unblocked Concurrency:** Because the main review pipeline does not hold row locks across Firecrawl or AI network calls, the heartbeat can renew leases smoothly without lock contention or timeouts.
```

At every checkpoint, `assert_valid_fenced_lease()` verifies:
```python
active = db.query(DistributedLock).filter(
    DistributedLock.lock_key == lock_key,
    DistributedLock.owner_id == owner_id,
    DistributedLock.generation == expected_generation,
    DistributedLock.expires_at > datetime.utcnow()
).first()
if not active:
    db.rollback()
    raise RuntimeError(f"Fencing token validation failed: Worker {owner_id} lost lease.")
```

If the lease was lost or claimed by another worker, execution immediately halts, the database transaction rolls back, and no stale records are written.

---

## 5. LockHeartbeat Lifecycle

The `LockHeartbeat` runs as a dedicated daemon thread:
- **Interval:** Every 15 seconds (configurable).
- **Extension:** Extends `expires_at` by 600 seconds (10 minutes) on each pulse.
- **Verification:** Queries the database to verify `owner_id == worker_id` AND `generation == expected_generation`.
- **Bounded Retries:** If a transient database disconnection occurs, it retries up to 3 times with exponential backoff before flagging `lost_lock_event.set()`.
- **Safe Abort:** The worker checks `heartbeat.is_lock_lost()` before and after every network call.

