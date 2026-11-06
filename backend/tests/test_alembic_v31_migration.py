import os
import tempfile
import sqlalchemy as sa
from alembic.config import Config
from alembic import command


def test_alembic_upgrade_from_empty_database_to_005_head():
    fd, tmp_db_path = tempfile.mkstemp(suffix=".db", prefix="test_mig_005_")
    os.close(fd)
    try:
        db_url = f"sqlite:///{tmp_db_path}"
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg = Config(os.path.join(backend_dir, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
        cfg.set_main_option("sqlalchemy.url", db_url)

        command.upgrade(cfg, "head")
        # Running upgrade a second time must be idempotent
        command.upgrade(cfg, "head")

        eng = sa.create_engine(db_url)
        try:
            insp = sa.inspect(eng)
            tables = set(insp.get_table_names())
            required_v31_tables = {
                "repository_ingestion_runs",
                "repository_analysis_snapshots",
                "vulnerability_cache_entries",
                "payment_orders",
                "billing_webhook_events",
                "webhook_delivery_events",
                "rate_limit_buckets",
                "remediation_work_packages",
            }
            assert required_v31_tables.issubset(tables)

            proj_cols = {c["name"] for c in insp.get_columns("projects")}
            assert {"is_archived", "archived_at"}.issubset(proj_cols)

            ai_cols = {c["name"] for c in insp.get_columns("ai_usage_ledgers")}
            assert {"cost_usd", "latency_ms"}.issubset(ai_cols)
        finally:
            eng.dispose()
    finally:
        if os.path.exists(tmp_db_path):
            os.remove(tmp_db_path)
