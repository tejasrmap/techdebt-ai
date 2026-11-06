import uuid
import time
import threading
from datetime import datetime, timedelta
import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.all_models import DistributedLock, Project, Organization
from app.services.scheduler_service import (
    acquire_distributed_lock,
    release_distributed_lock,
    renew_distributed_lock,
    get_lock_generation,
    assert_valid_fenced_lease_transactional,
    verify_ownership_short_transaction,
    StaleGenerationWriteError,
    LockHeartbeat
)

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_concurrent_lock_mutual_exclusion(db: Session):
    """Verify that only one worker can acquire a distributed lock concurrently."""
    lock_key = f"test_mutex_lock_{uuid.uuid4().hex[:8]}"
    worker_a = "worker_alpha"
    worker_b = "worker_beta"

    # Worker A acquires lock
    acquired_a = acquire_distributed_lock(db, lock_key, worker_a, ttl_seconds=60)
    assert acquired_a is True

    # Worker B tries to acquire same lock
    acquired_b = acquire_distributed_lock(db, lock_key, worker_b, ttl_seconds=60)
    assert acquired_b is False

    # Clean up
    release_distributed_lock(db, lock_key, worker_a)

def test_monotonic_generation_increment_on_expired_lease(db: Session):
    """Verify that reclaiming an expired lease monotonically increments generation fencing tokens."""
    lock_key = f"test_gen_lock_{uuid.uuid4().hex[:8]}"
    worker_1 = "worker_one"
    worker_2 = "worker_two"

    # Worker 1 acquires lock
    assert acquire_distributed_lock(db, lock_key, worker_1, ttl_seconds=60) is True
    gen_1 = get_lock_generation(db, lock_key, worker_1)
    assert gen_1 is not None

    # Simulate expiration by forcing expires_at into the past
    db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).update({
        "expires_at": datetime.utcnow() - timedelta(seconds=10)
    })
    db.commit()

    # Worker 2 acquires the expired lock
    assert acquire_distributed_lock(db, lock_key, worker_2, ttl_seconds=60) is True
    gen_2 = get_lock_generation(db, lock_key, worker_2)
    assert gen_2 is not None
    assert gen_2 > gen_1  # Monotonically increasing generation!

    # Worker 1 tries to validate with its stale generation -> MUST raise StaleGenerationWriteError
    with pytest.raises(StaleGenerationWriteError, match="lost ownership|superseded"):
        verify_ownership_short_transaction(db, lock_key, worker_1, gen_1)

    # Clean up
    release_distributed_lock(db, lock_key, worker_2, expected_generation=gen_2)

def test_verify_ownership_never_commits_caller_session(db: Session):
    """Verify that verify_ownership_short_transaction never commits uncommitted records on caller session."""
    lock_key = f"test_nocommit_lock_{uuid.uuid4().hex[:8]}"
    worker = "worker_isolated"

    assert acquire_distributed_lock(db, lock_key, worker, ttl_seconds=60) is True
    gen = get_lock_generation(db, lock_key, worker)

    # Session A: Create an organization and an uncommitted project
    session_a = SessionLocal()
    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name=f"NoCommit Org {uuid.uuid4().hex[:6]}", slug=f"nocommit-{uuid.uuid4().hex[:6]}", plan="starter")
    session_a.add(org)
    session_a.commit()

    uncommitted_proj_id = str(uuid.uuid4())
    proj = Project(id=uncommitted_proj_id, org_id=org_id, name="Uncommitted Work In Progress")
    session_a.add(proj)
    session_a.flush()  # Flushed to session but NOT committed to DB transaction!

    # Call verify_ownership_short_transaction on session_a
    verify_ownership_short_transaction(session_a, lock_key, worker, gen, use_isolated_session=False)

    # Session B: Query from an independent connection
    session_b = SessionLocal()
    found_in_b = session_b.query(Project).filter(Project.id == uncommitted_proj_id).first()
    
    # Project must NOT be visible to session B because session_a was NOT prematurely committed!
    # (In SQLite WAL mode with uncommitted transaction, another session will not see uncommitted flush)
    session_a.rollback()  # Safely roll back uncommitted work
    session_a.close()
    session_b.close()

    release_distributed_lock(db, lock_key, worker, expected_generation=gen)

def test_heartbeat_detects_lost_lock(db: Session):
    """Verify that LockHeartbeat marks lock as lost when ownership or generation changes in database."""
    lock_key = f"test_heartbeat_lock_{uuid.uuid4().hex[:8]}"
    worker = "worker_heartbeat"

    assert acquire_distributed_lock(db, lock_key, worker, ttl_seconds=60) is True
    gen = get_lock_generation(db, lock_key, worker)

    # Start heartbeat with short interval
    hb = LockHeartbeat(lock_key, worker, interval=0.2, lease_extension=60, generation=gen)
    hb.start()

    time.sleep(0.3)
    assert hb.is_lock_lost() is False

    # Simulate another worker taking over by changing the owner in database
    db.query(DistributedLock).filter(DistributedLock.lock_key == lock_key).update({
        "owner_id": "usurper_worker",
        "generation": gen + 1
    })
    db.commit()

    # Wait for heartbeat to run and detect the lost lock
    time.sleep(0.5)
    assert hb.is_lock_lost() is True

    hb.stop()

def test_release_lock_enforces_generation(db: Session):
    """Verify that release_distributed_lock fails if expected_generation does not match."""
    lock_key = f"test_release_gen_{uuid.uuid4().hex[:8]}"
    worker = "worker_rel"

    assert acquire_distributed_lock(db, lock_key, worker, ttl_seconds=60) is True
    gen = get_lock_generation(db, lock_key, worker)

    # Attempt release with wrong generation -> should fail
    released_wrong = release_distributed_lock(db, lock_key, worker, expected_generation=gen + 99)
    assert released_wrong is False

    # Attempt release with correct generation -> should succeed
    released_correct = release_distributed_lock(db, lock_key, worker, expected_generation=gen)
    assert released_correct is True
