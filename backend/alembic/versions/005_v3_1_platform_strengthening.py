"""v3.1.0 platform strengthening: ingestion snapshots, billing orders, cache, rate limits, and schema reconciliation

Revision ID: 005_v3_1_platform_strengthening
Revises: 004_v3_ai_usage_ledgers_and_indexes
Create Date: 2026-11-07 01:25:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "005_v3_1_platform_strengthening"
down_revision = "004_v3_ai_usage_ledgers_and_indexes"
branch_labels = None
depends_on = None


def _has_table(insp, table_name: str) -> bool:
    return insp.has_table(table_name)


def _has_column(insp, table_name: str, column_name: str) -> bool:
    if not insp.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in insp.get_columns(table_name))


def _has_index(insp, table_name: str, index_name: str) -> bool:
    if not insp.has_table(table_name):
        return False
    return any(idx["name"] == index_name for idx in insp.get_indexes(table_name))


def _add_col_if_missing(insp, table_name: str, column: sa.Column) -> None:
    if not _has_column(insp, table_name, column.name):
        op.add_column(table_name, column)


def _add_index_if_missing(insp, index_name: str, table_name: str, columns, unique: bool = False) -> None:
    if not _has_index(insp, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Reconcile missing / drifted columns from 001-004
    _add_col_if_missing(insp, "projects", sa.Column("is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    _add_col_if_missing(insp, "projects", sa.Column("archived_at", sa.DateTime(), nullable=True))
    _add_index_if_missing(insp, "ix_projects_is_archived", "projects", ["is_archived"])

    _add_col_if_missing(insp, "ai_usage_ledgers", sa.Column("cost_usd", sa.Float(), server_default="0.0", nullable=True))
    _add_col_if_missing(insp, "ai_usage_ledgers", sa.Column("latency_ms", sa.Float(), server_default="0.0", nullable=True))
    _add_index_if_missing(insp, "ix_ai_usage_ledgers_user_id", "ai_usage_ledgers", ["user_id"])

    _add_col_if_missing(insp, "users", sa.Column("password_changed_at", sa.DateTime(), nullable=True))

    _add_col_if_missing(insp, "technologies", sa.Column("license", sa.String(length=150), server_default="UNKNOWN", nullable=True))

    _add_col_if_missing(insp, "project_technologies", sa.Column("latest_version", sa.String(length=100), server_default="unknown", nullable=True))
    _add_col_if_missing(insp, "project_technologies", sa.Column("is_outdated", sa.Boolean(), server_default=sa.text("false"), nullable=True))
    _add_col_if_missing(insp, "project_technologies", sa.Column("license", sa.String(length=150), server_default="UNKNOWN", nullable=True))
    _add_col_if_missing(insp, "project_technologies", sa.Column("vulnerability_status", sa.String(length=50), server_default="UNKNOWN", nullable=True))

    _add_col_if_missing(insp, "assessments", sa.Column("commit_sha", sa.String(length=100), server_default="", nullable=True))
    _add_col_if_missing(insp, "assessments", sa.Column("analyzer_version", sa.String(length=50), server_default="3.1.0", nullable=True))
    _add_index_if_missing(insp, "ix_assessments_commit_sha", "assessments", ["commit_sha"])

    _add_col_if_missing(insp, "risk_findings", sa.Column("estimated_remediation_hours", sa.Float(), server_default="2.0", nullable=True))
    _add_col_if_missing(insp, "risk_findings", sa.Column("fingerprint", sa.String(length=128), nullable=True))
    _add_index_if_missing(insp, "ix_risk_findings_assigned_to", "risk_findings", ["assigned_to"])
    _add_index_if_missing(insp, "ix_risk_findings_fingerprint", "risk_findings", ["fingerprint"])

    _add_col_if_missing(insp, "code_findings", sa.Column("status", sa.String(length=50), server_default="Open", nullable=True))
    _add_col_if_missing(insp, "code_findings", sa.Column("assigned_to", sa.String(length=36), nullable=True))
    _add_col_if_missing(insp, "code_findings", sa.Column("resolved_at", sa.DateTime(), nullable=True))
    _add_col_if_missing(insp, "code_findings", sa.Column("analyzer_name", sa.String(length=100), server_default="SourceCodeAnalyzer", nullable=True))
    _add_col_if_missing(insp, "code_findings", sa.Column("analyzer_version", sa.String(length=50), server_default="3.1.0", nullable=True))
    _add_index_if_missing(insp, "ix_code_findings_status", "code_findings", ["status"])
    _add_index_if_missing(insp, "ix_code_findings_assigned_to", "code_findings", ["assigned_to"])

    _add_col_if_missing(insp, "subscriptions", sa.Column("payment_provider", sa.String(length=50), server_default="razorpay", nullable=True))
    _add_col_if_missing(insp, "subscriptions", sa.Column("provider_customer_id", sa.String(length=255), server_default="", nullable=True))
    _add_col_if_missing(insp, "subscriptions", sa.Column("provider_subscription_id", sa.String(length=255), server_default="", nullable=True))
    _add_col_if_missing(insp, "subscriptions", sa.Column("provider_order_id", sa.String(length=255), server_default="", nullable=True))
    _add_col_if_missing(insp, "subscriptions", sa.Column("provider_payment_id", sa.String(length=255), server_default="", nullable=True))
    _add_index_if_missing(insp, "ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    _add_index_if_missing(insp, "ix_subscriptions_provider_customer_id", "subscriptions", ["provider_customer_id"])
    _add_index_if_missing(insp, "ix_subscriptions_provider_subscription_id", "subscriptions", ["provider_subscription_id"])
    _add_index_if_missing(insp, "ix_subscriptions_provider_order_id", "subscriptions", ["provider_order_id"])
    _add_index_if_missing(insp, "ix_subscriptions_provider_payment_id", "subscriptions", ["provider_payment_id"])

    _add_index_if_missing(insp, "ix_organization_invitations_invited_by_id", "organization_invitations", ["invited_by_id"])

    # 2. New v3.1.0 durable tables
    if not _has_table(insp, "repository_ingestion_runs"):
        op.create_table(
            "repository_ingestion_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("repo_connection_id", sa.String(length=36), sa.ForeignKey("repository_connections.id", ondelete="SET NULL"), nullable=True),
            sa.Column("provider", sa.String(length=50), nullable=False, server_default="github"),
            sa.Column("branch", sa.String(length=100), nullable=False, server_default="main"),
            sa.Column("commit_sha", sa.String(length=100), server_default=""),
            sa.Column("commit_message", sa.Text(), server_default=""),
            sa.Column("commit_author", sa.String(length=255), server_default=""),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="QUEUED"),
            sa.Column("progress_pct", sa.Integer(), server_default="0"),
            sa.Column("analyzer_version", sa.String(length=50), server_default="3.1.0"),
            sa.Column("files_examined", sa.Integer(), server_default="0"),
            sa.Column("files_analyzed", sa.Integer(), server_default="0"),
            sa.Column("files_excluded", sa.Integer(), server_default="0"),
            sa.Column("unsupported_files", sa.Integer(), server_default="0"),
            sa.Column("parser_failures", sa.Integer(), server_default="0"),
            sa.Column("lines_of_code", sa.Integer(), server_default="0"),
            sa.Column("languages_json", sa.JSON(), nullable=True),
            sa.Column("frameworks_json", sa.JSON(), nullable=True),
            sa.Column("dependencies_count", sa.Integer(), server_default="0"),
            sa.Column("findings_count", sa.Integer(), server_default="0"),
            sa.Column("error_message", sa.Text(), server_default=""),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_repository_ingestion_runs_org_id", "repository_ingestion_runs", ["org_id"])
        op.create_index("ix_repository_ingestion_runs_project_id", "repository_ingestion_runs", ["project_id"])
        op.create_index("ix_repository_ingestion_runs_repo_connection_id", "repository_ingestion_runs", ["repo_connection_id"])
        op.create_index("ix_repository_ingestion_runs_commit_sha", "repository_ingestion_runs", ["commit_sha"])
        op.create_index("ix_repository_ingestion_runs_status", "repository_ingestion_runs", ["status"])
        op.create_index("ix_repository_ingestion_runs_created_at", "repository_ingestion_runs", ["created_at"])

    if not _has_table(insp, "repository_analysis_snapshots"):
        op.create_table(
            "repository_analysis_snapshots",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("repo_connection_id", sa.String(length=36), sa.ForeignKey("repository_connections.id", ondelete="SET NULL"), nullable=True),
            sa.Column("ingestion_run_id", sa.String(length=36), sa.ForeignKey("repository_ingestion_runs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("provider", sa.String(length=50), nullable=False, server_default="github"),
            sa.Column("branch", sa.String(length=100), nullable=False, server_default="main"),
            sa.Column("commit_sha", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("commit_message", sa.Text(), server_default=""),
            sa.Column("commit_author", sa.String(length=255), server_default=""),
            sa.Column("analyzer_version", sa.String(length=50), nullable=False, server_default="3.1.0"),
            sa.Column("files_examined", sa.Integer(), server_default="0"),
            sa.Column("files_analyzed", sa.Integer(), server_default="0"),
            sa.Column("files_excluded", sa.Integer(), server_default="0"),
            sa.Column("unsupported_files", sa.Integer(), server_default="0"),
            sa.Column("parser_failures", sa.Integer(), server_default="0"),
            sa.Column("lines_of_code", sa.Integer(), server_default="0"),
            sa.Column("languages_json", sa.JSON(), nullable=True),
            sa.Column("frameworks_json", sa.JSON(), nullable=True),
            sa.Column("code_metrics_json", sa.JSON(), nullable=True),
            sa.Column("findings_json", sa.JSON(), nullable=True),
            sa.Column("dependencies_json", sa.JSON(), nullable=True),
            sa.Column("architecture_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_repository_analysis_snapshots_org_id", "repository_analysis_snapshots", ["org_id"])
        op.create_index("ix_repository_analysis_snapshots_project_id", "repository_analysis_snapshots", ["project_id"])
        op.create_index("ix_repository_analysis_snapshots_repo_connection_id", "repository_analysis_snapshots", ["repo_connection_id"])
        op.create_index("ix_repository_analysis_snapshots_ingestion_run_id", "repository_analysis_snapshots", ["ingestion_run_id"])
        op.create_index("ix_repository_analysis_snapshots_commit_sha", "repository_analysis_snapshots", ["commit_sha"])
        op.create_index("ix_repository_analysis_snapshots_created_at", "repository_analysis_snapshots", ["created_at"])
        op.create_index("idx_repo_snapshot_proj_commit_ver", "repository_analysis_snapshots", ["project_id", "commit_sha", "analyzer_version"])

    if not _has_table(insp, "vulnerability_cache_entries"):
        op.create_table(
            "vulnerability_cache_entries",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("cache_key", sa.String(length=500), nullable=False, unique=True),
            sa.Column("ecosystem", sa.String(length=100), nullable=False),
            sa.Column("package_name", sa.String(length=255), nullable=False),
            sa.Column("version", sa.String(length=100), nullable=False),
            sa.Column("provider", sa.String(length=50), server_default="osv"),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="UNKNOWN"),
            sa.Column("vulnerabilities_json", sa.JSON(), nullable=True),
            sa.Column("license_raw", sa.String(length=255), server_default=""),
            sa.Column("license_spdx", sa.String(length=150), server_default="UNKNOWN"),
            sa.Column("latest_version", sa.String(length=100), server_default="unknown"),
            sa.Column("is_deprecated", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("fetched_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_vulnerability_cache_entries_cache_key", "vulnerability_cache_entries", ["cache_key"], unique=True)
        op.create_index("ix_vulnerability_cache_entries_ecosystem", "vulnerability_cache_entries", ["ecosystem"])
        op.create_index("ix_vulnerability_cache_entries_package_name", "vulnerability_cache_entries", ["package_name"])
        op.create_index("ix_vulnerability_cache_entries_expires_at", "vulnerability_cache_entries", ["expires_at"])

    if not _has_table(insp, "payment_orders"):
        op.create_table(
            "payment_orders",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("provider", sa.String(length=50), nullable=False, server_default="razorpay"),
            sa.Column("provider_order_id", sa.String(length=255), nullable=False, unique=True),
            sa.Column("plan_id", sa.String(length=50), sa.ForeignKey("subscription_plans.id"), nullable=False),
            sa.Column("billing_cycle", sa.String(length=20), nullable=False, server_default="monthly"),
            sa.Column("amount_subunits", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="USD"),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="created"),
            sa.Column("provider_payment_id", sa.String(length=255), nullable=True, unique=True),
            sa.Column("receipt", sa.String(length=100), server_default=""),
            sa.Column("error_message", sa.Text(), server_default=""),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_payment_orders_org_id", "payment_orders", ["org_id"])
        op.create_index("ix_payment_orders_user_id", "payment_orders", ["user_id"])
        op.create_index("ix_payment_orders_provider_order_id", "payment_orders", ["provider_order_id"], unique=True)
        op.create_index("ix_payment_orders_plan_id", "payment_orders", ["plan_id"])
        op.create_index("ix_payment_orders_status", "payment_orders", ["status"])
        op.create_index("ix_payment_orders_provider_payment_id", "payment_orders", ["provider_payment_id"], unique=True)
        op.create_index("ix_payment_orders_created_at", "payment_orders", ["created_at"])

    if not _has_table(insp, "billing_webhook_events"):
        op.create_table(
            "billing_webhook_events",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("event_id", sa.String(length=255), nullable=False, unique=True),
            sa.Column("event_type", sa.String(length=100), nullable=False),
            sa.Column("org_id", sa.String(length=36), nullable=True),
            sa.Column("payload_hash", sa.String(length=64), server_default=""),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="processed"),
            sa.Column("action_taken", sa.String(length=100), server_default="none"),
            sa.Column("error_message", sa.Text(), server_default=""),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_billing_webhook_events_provider", "billing_webhook_events", ["provider"])
        op.create_index("ix_billing_webhook_events_event_id", "billing_webhook_events", ["event_id"], unique=True)
        op.create_index("ix_billing_webhook_events_event_type", "billing_webhook_events", ["event_type"])
        op.create_index("ix_billing_webhook_events_org_id", "billing_webhook_events", ["org_id"])
        op.create_index("ix_billing_webhook_events_created_at", "billing_webhook_events", ["created_at"])

    if not _has_table(insp, "webhook_delivery_events"):
        op.create_table(
            "webhook_delivery_events",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("delivery_id", sa.String(length=255), nullable=False, unique=True),
            sa.Column("org_id", sa.String(length=36), nullable=True),
            sa.Column("project_id", sa.String(length=36), nullable=True),
            sa.Column("repo_connection_id", sa.String(length=36), sa.ForeignKey("repository_connections.id", ondelete="SET NULL"), nullable=True),
            sa.Column("event_type", sa.String(length=100), server_default="push"),
            sa.Column("branch", sa.String(length=100), server_default="main"),
            sa.Column("commit_sha", sa.String(length=100), server_default=""),
            sa.Column("pr_number", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=50), server_default="queued"),
            sa.Column("ingestion_run_id", sa.String(length=36), nullable=True),
            sa.Column("retry_count", sa.Integer(), server_default="0"),
            sa.Column("error_message", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_webhook_delivery_events_provider", "webhook_delivery_events", ["provider"])
        op.create_index("ix_webhook_delivery_events_delivery_id", "webhook_delivery_events", ["delivery_id"], unique=True)
        op.create_index("ix_webhook_delivery_events_org_id", "webhook_delivery_events", ["org_id"])
        op.create_index("ix_webhook_delivery_events_project_id", "webhook_delivery_events", ["project_id"])
        op.create_index("ix_webhook_delivery_events_repo_connection_id", "webhook_delivery_events", ["repo_connection_id"])
        op.create_index("ix_webhook_delivery_events_status", "webhook_delivery_events", ["status"])
        op.create_index("ix_webhook_delivery_events_created_at", "webhook_delivery_events", ["created_at"])

    if not _has_table(insp, "rate_limit_buckets"):
        op.create_table(
            "rate_limit_buckets",
            sa.Column("bucket_key", sa.String(length=255), primary_key=True),
            sa.Column("window_start", sa.Integer(), nullable=False),
            sa.Column("request_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_rate_limit_buckets_expires_at", "rate_limit_buckets", ["expires_at"])

    if not _has_table(insp, "remediation_work_packages"):
        op.create_table(
            "remediation_work_packages",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), server_default=""),
            sa.Column("priority", sa.String(length=50), server_default="Medium"),
            sa.Column("priority_score", sa.Float(), server_default="50.0"),
            sa.Column("priority_rationale", sa.Text(), server_default=""),
            sa.Column("finding_refs_json", sa.JSON(), nullable=True),
            sa.Column("proposed_fix", sa.Text(), server_default=""),
            sa.Column("dependencies_json", sa.JSON(), nullable=True),
            sa.Column("estimated_hours", sa.Float(), server_default="2.0"),
            sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("target_date", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=50), server_default="Planned"),
            sa.Column("verification_criteria", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_remediation_work_packages_org_id", "remediation_work_packages", ["org_id"])
        op.create_index("ix_remediation_work_packages_project_id", "remediation_work_packages", ["project_id"])
        op.create_index("ix_remediation_work_packages_priority", "remediation_work_packages", ["priority"])
        op.create_index("ix_remediation_work_packages_owner_user_id", "remediation_work_packages", ["owner_user_id"])
        op.create_index("ix_remediation_work_packages_status", "remediation_work_packages", ["status"])
        op.create_index("ix_remediation_work_packages_created_at", "remediation_work_packages", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for t in (
        "remediation_work_packages",
        "rate_limit_buckets",
        "webhook_delivery_events",
        "billing_webhook_events",
        "payment_orders",
        "vulnerability_cache_entries",
        "repository_analysis_snapshots",
        "repository_ingestion_runs",
    ):
        if insp.has_table(t):
            op.drop_table(t)
