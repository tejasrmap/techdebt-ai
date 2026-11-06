import os
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

from backend.tests.test_postgresql_concurrency import validate_postgres_test_url, UnsafeTestDatabaseError
from app.database import engine

def test_postgres_test_url_safeguards():
    """Verify that validate_postgres_test_url strictly prevents accidental production database mutations."""
    # 1. Valid test database URL passes
    valid_url = "postgresql://postgres:postgres@localhost:5432/techdebt_test_disposable"
    assert validate_postgres_test_url(valid_url) == valid_url

    # 2. SQLite URLs are strictly rejected
    with pytest.raises(UnsafeTestDatabaseError, match="Invalid database dialect"):
        validate_postgres_test_url("sqlite:///./techdebt_test.db")

    # 3. Production database keywords are strictly rejected
    with pytest.raises(UnsafeTestDatabaseError, match="contains 'prod'/'production'"):
        validate_postgres_test_url("postgresql://postgres:postgres@localhost:5432/techdebt_prod_test")

    # 4. System / production database names are strictly rejected
    with pytest.raises(UnsafeTestDatabaseError, match="strictly rejects targeting production or system database"):
        validate_postgres_test_url("postgresql://postgres:postgres@localhost:5432/postgres")

    with pytest.raises(UnsafeTestDatabaseError, match="strictly rejects targeting production or system database"):
        validate_postgres_test_url("postgresql://postgres:postgres@localhost:5432/techdebt")

    # 5. Empty or unset URLs are strictly rejected
    with pytest.raises(UnsafeTestDatabaseError, match="POSTGRES_TEST_DATABASE_URL is not set or empty"):
        validate_postgres_test_url("")

    with pytest.raises(UnsafeTestDatabaseError, match="POSTGRES_TEST_DATABASE_URL is not set or empty"):
        validate_postgres_test_url(None)

def test_alembic_migration_chain_integrity():
    """Verify that Alembic migrations form a complete, continuous chain from 001 to head 004."""
    # Locate alembic.ini relative to this test file
    test_dir = os.path.dirname(os.path.abspath(__file__))
    alembic_ini_path = os.path.join(test_dir, "..", "alembic.ini")
    
    config = Config(alembic_ini_path)
    script_dir = ScriptDirectory.from_config(config)

    # Verify head is 004_v3_ai_usage_ledgers_and_indexes
    heads = script_dir.get_heads()
    assert "004_v3_ai_usage_ledgers_and_indexes" in heads, f"Expected head revision, found: {heads}"

    # Verify linear revision sequence
    revisions = [rev.revision for rev in script_dir.walk_revisions()]
    assert "004_v3_ai_usage_ledgers_and_indexes" in revisions
    assert "003_v2_commercial_saas_platform" in revisions
    assert "002_transactional_fencing_and_memento_cleanup" in revisions
    assert "001_initial_complete_schema" in revisions

    # Verify parent links
    rev_004 = script_dir.get_revision("004_v3_ai_usage_ledgers_and_indexes")
    assert rev_004.down_revision == "003_v2_commercial_saas_platform"

    rev_003 = script_dir.get_revision("003_v2_commercial_saas_platform")
    assert rev_003.down_revision == "002_transactional_fencing_and_memento_cleanup"

    rev_002 = script_dir.get_revision("002_transactional_fencing_and_memento_cleanup")
    assert rev_002.down_revision == "001_initial_complete_schema"

def test_database_engine_configuration():
    """Verify that engine has pool_pre_ping enabled and proper resilience configuration."""
    assert engine.pool is not None
    # pool_pre_ping flag should be True
    assert getattr(engine.pool, "_pre_ping", True) is True
