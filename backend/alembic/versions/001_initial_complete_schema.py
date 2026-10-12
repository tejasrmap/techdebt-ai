"""initial_complete_schema

Revision ID: 001_initial_complete_schema
Revises: 
Create Date: 2026-11-05 23:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001_initial_complete_schema'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Organizations
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('plan', sa.String(length=50), server_default='enterprise', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('name', name='uq_organizations_name'),
        sa.UniqueConstraint('slug', name='uq_organizations_slug')
    )
    op.create_index('ix_organizations_name', 'organizations', ['name'])
    op.create_index('ix_organizations_slug', 'organizations', ['slug'])

    # 2. Users
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), server_default='', nullable=True),
        sa.Column('role', sa.String(length=50), server_default='Developer', nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name='fk_users_org_id_organizations', ondelete='CASCADE'),
        sa.UniqueConstraint('email', name='uq_users_email')
    )
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_org_id', 'users', ['org_id'])

    # 3. Organization Invitations
    op.create_table(
        'organization_invitations',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), server_default='Developer', nullable=True),
        sa.Column('token', sa.String(length=255), nullable=True),
        sa.Column('token_hash', sa.String(length=64), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('is_accepted', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('invited_by_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['invited_by_id'], ['users.id'], name='fk_invitations_invited_by_id_users', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name='fk_invitations_org_id_organizations', ondelete='CASCADE'),
        sa.UniqueConstraint('token_hash', name='uq_invitation_token_hash')
    )
    op.create_index('idx_invitation_org_email', 'organization_invitations', ['org_id', 'email'])
    op.create_index('ix_organization_invitations_email', 'organization_invitations', ['email'])
    op.create_index('ix_organization_invitations_org_id', 'organization_invitations', ['org_id'])
    op.create_index('ix_organization_invitations_token', 'organization_invitations', ['token'])

    # 4. Revoked Tokens
    op.create_table(
        'revoked_tokens',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('jti', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('jti', name='uq_revoked_tokens_jti')
    )
    op.create_index('ix_revoked_tokens_jti', 'revoked_tokens', ['jti'])

    # 5. Projects
    op.create_table(
        'projects',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=True),
        sa.Column('repository_url', sa.String(length=500), server_default='', nullable=True),
        sa.Column('languages', sa.JSON(), nullable=True),
        sa.Column('frameworks', sa.JSON(), nullable=True),
        sa.Column('owner_name', sa.String(length=255), server_default='Engineering Team', nullable=True),
        sa.Column('last_assessment_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name='fk_projects_org_id_organizations', ondelete='CASCADE'),
        sa.UniqueConstraint('org_id', 'name', name='uq_org_project_name')
    )
    op.create_index('idx_project_org_created', 'projects', ['org_id', 'created_at'])
    op.create_index('ix_projects_name', 'projects', ['name'])
    op.create_index('ix_projects_org_id', 'projects', ['org_id'])

    # 6. Technologies
    op.create_table(
        'technologies',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('ecosystem', sa.String(length=100), server_default='npm', nullable=True),
        sa.Column('category', sa.String(length=100), server_default='Library', nullable=True),
        sa.Column('latest_stable_version', sa.String(length=100), server_default='unknown', nullable=True),
        sa.Column('description', sa.Text(), server_default='', nullable=True),
        sa.Column('website_url', sa.String(length=500), server_default='', nullable=True),
        sa.Column('repo_url', sa.String(length=500), server_default='', nullable=True),
        sa.Column('is_deprecated', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('is_eol', sa.Boolean(), server_default='0', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('name', name='uq_technologies_name')
    )
    op.create_index('ix_technologies_ecosystem', 'technologies', ['ecosystem'])
    op.create_index('ix_technologies_name', 'technologies', ['name'])

    # 7. Project Technologies
    op.create_table(
        'project_technologies',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('technology_id', sa.String(length=36), nullable=False),
        sa.Column('installed_version', sa.String(length=100), server_default='latest', nullable=True),
        sa.Column('is_direct_dep', sa.Boolean(), server_default='1', nullable=True),
        sa.Column('file_source', sa.String(length=255), server_default='manual', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_proj_tech_project_id_projects', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['technology_id'], ['technologies.id'], name='fk_proj_tech_technology_id_technologies', ondelete='CASCADE'),
        sa.UniqueConstraint('project_id', 'technology_id', name='uq_project_technology')
    )
    op.create_index('ix_project_technologies_project_id', 'project_technologies', ['project_id'])
    op.create_index('ix_project_technologies_technology_id', 'project_technologies', ['technology_id'])

    # 8. Assessments
    op.create_table(
        'assessments',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('trigger_type', sa.String(length=50), server_default='manual', nullable=True),
        sa.Column('status', sa.String(length=50), server_default='completed', nullable=True),
        sa.Column('overall_health_score', sa.Float(), nullable=True),
        sa.Column('risk_classification', sa.String(length=50), server_default='Healthy', nullable=True),
        sa.Column('confidence_level', sa.String(length=50), server_default='High', nullable=True),
        sa.Column('summary', sa.Text(), server_default='', nullable=True),
        sa.Column('raw_output', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_assessments_project_id_projects', ondelete='CASCADE')
    )
    op.create_index('idx_assessment_project_created', 'assessments', ['project_id', 'created_at'])
    op.create_index('ix_assessments_created_at', 'assessments', ['created_at'])
    op.create_index('ix_assessments_project_id', 'assessments', ['project_id'])
    op.create_index('ix_assessments_status', 'assessments', ['status'])

    # 9. Technology Scores
    op.create_table(
        'technology_scores',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('assessment_id', sa.String(length=36), nullable=False),
        sa.Column('technology_id', sa.String(length=36), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=False),
        sa.Column('risk_classification', sa.String(length=50), server_default='Good', nullable=True),
        sa.Column('maintenance_health', sa.Float(), nullable=True),
        sa.Column('security_exposure', sa.Float(), nullable=True),
        sa.Column('version_currency', sa.Float(), nullable=True),
        sa.Column('community_activity', sa.Float(), nullable=True),
        sa.Column('documentation_quality', sa.Float(), nullable=True),
        sa.Column('ecosystem_compatibility', sa.Float(), nullable=True),
        sa.Column('sustainability', sa.Float(), nullable=True),
        sa.Column('upgrade_complexity', sa.Float(), nullable=True),
        sa.Column('confidence_level', sa.String(length=50), server_default='High', nullable=True),
        sa.Column('recommended_action', sa.Text(), server_default='', nullable=True),
        sa.Column('upgrade_complexity_level', sa.String(length=50), server_default='Low', nullable=True),
        sa.Column('notes', sa.Text(), server_default='', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], name='fk_tech_scores_assessment_id_assessments', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['technology_id'], ['technologies.id'], name='fk_tech_scores_technology_id_technologies', ondelete='CASCADE')
    )
    op.create_index('ix_technology_scores_assessment_id', 'technology_scores', ['assessment_id'])
    op.create_index('ix_technology_scores_technology_id', 'technology_scores', ['technology_id'])

    # 10. Risk Findings
    op.create_table(
        'risk_findings',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('assessment_id', sa.String(length=36), nullable=False),
        sa.Column('technology_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('severity', sa.String(length=50), server_default='Medium', nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=True),
        sa.Column('business_impact', sa.Text(), server_default='', nullable=True),
        sa.Column('technical_impact', sa.Text(), server_default='', nullable=True),
        sa.Column('status', sa.String(length=50), server_default='Open', nullable=True),
        sa.Column('assigned_to', sa.String(length=36), nullable=True),
        sa.Column('resolution_notes', sa.Text(), server_default='', nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], name='fk_risk_findings_assessment_id_assessments', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], name='fk_risk_findings_assigned_to_users', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_risk_findings_project_id_projects', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['technology_id'], ['technologies.id'], name='fk_risk_findings_technology_id_technologies', ondelete='CASCADE')
    )
    op.create_index('idx_risk_project_status', 'risk_findings', ['project_id', 'status'])
    op.create_index('ix_risk_findings_assessment_id', 'risk_findings', ['assessment_id'])
    op.create_index('ix_risk_findings_created_at', 'risk_findings', ['created_at'])
    op.create_index('ix_risk_findings_project_id', 'risk_findings', ['project_id'])
    op.create_index('ix_risk_findings_severity', 'risk_findings', ['severity'])
    op.create_index('ix_risk_findings_status', 'risk_findings', ['status'])
    op.create_index('ix_risk_findings_technology_id', 'risk_findings', ['technology_id'])

    # 11. Evidence Sources
    op.create_table(
        'evidence_sources',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('assessment_id', sa.String(length=36), nullable=False),
        sa.Column('technology_id', sa.String(length=36), nullable=False),
        sa.Column('url', sa.String(length=1000), nullable=False),
        sa.Column('title', sa.String(length=500), server_default='', nullable=True),
        sa.Column('source_type', sa.String(length=100), server_default='documentation', nullable=True),
        sa.Column('reliability_score', sa.Float(), server_default='1.0', nullable=True),
        sa.Column('publication_date', sa.String(length=100), nullable=True),
        sa.Column('is_official', sa.Boolean(), server_default='1', nullable=True),
        sa.Column('snippet', sa.Text(), server_default='', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], name='fk_evidence_sources_assessment_id_assessments', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['technology_id'], ['technologies.id'], name='fk_evidence_sources_technology_id_technologies', ondelete='CASCADE')
    )
    op.create_index('ix_evidence_sources_assessment_id', 'evidence_sources', ['assessment_id'])
    op.create_index('ix_evidence_sources_technology_id', 'evidence_sources', ['technology_id'])

    # 12. Historical Assessments
    op.create_table(
        'historical_assessments',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('technology_id', sa.String(length=36), nullable=True),
        sa.Column('assessment_id', sa.String(length=36), nullable=False),
        sa.Column('health_score', sa.Float(), nullable=False),
        sa.Column('score_delta', sa.Float(), server_default='0.0', nullable=True),
        sa.Column('risk_classification', sa.String(length=50), server_default='Good', nullable=True),
        sa.Column('snapshot_data', sa.JSON(), nullable=True),
        sa.Column('summary_of_changes', sa.Text(), server_default='', nullable=True),
        sa.Column('new_risks_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('resolved_risks_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('storage_provider', sa.String(length=50), server_default='postgresql', nullable=True),
        sa.Column('sync_status', sa.String(length=50), server_default='local_postgresql_only', nullable=True),
        sa.Column('sync_error', sa.Text(), server_default='', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['assessment_id'], ['assessments.id'], name='fk_historical_assessments_assessment_id_assessments', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_historical_assessments_project_id_projects', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['technology_id'], ['technologies.id'], name='fk_historical_assessments_technology_id_technologies', ondelete='CASCADE')
    )
    op.create_index('idx_history_project_created', 'historical_assessments', ['project_id', 'created_at'])
    op.create_index('ix_historical_assessments_assessment_id', 'historical_assessments', ['assessment_id'])
    op.create_index('ix_historical_assessments_created_at', 'historical_assessments', ['created_at'])
    op.create_index('ix_historical_assessments_project_id', 'historical_assessments', ['project_id'])
    op.create_index('ix_historical_assessments_technology_id', 'historical_assessments', ['technology_id'])

    # 13. Scheduled Reviews
    op.create_table(
        'scheduled_reviews',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('frequency', sa.String(length=50), server_default='Weekly', nullable=True),
        sa.Column('cron_expression', sa.String(length=100), server_default='0 0 * * 1', nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=True),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='fk_scheduled_reviews_project_id_projects', ondelete='CASCADE')
    )
    op.create_index('ix_scheduled_reviews_project_id', 'scheduled_reviews', ['project_id'])

    # 14. Review Jobs
    op.create_table(
        'review_jobs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('scheduled_review_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='Pending', nullable=True),
        sa.Column('error_message', sa.Text(), server_default='', nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['scheduled_review_id'], ['scheduled_reviews.id'], name='fk_review_jobs_scheduled_review_id_scheduled_reviews', ondelete='CASCADE')
    )
    op.create_index('ix_review_jobs_scheduled_review_id', 'review_jobs', ['scheduled_review_id'])
    op.create_index('ix_review_jobs_status', 'review_jobs', ['status'])

    # 15. Audit Logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('resource_id', sa.String(length=100), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True)
    )
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('ix_audit_logs_org_id', 'audit_logs', ['org_id'])

    # 16. Integration Settings
    op.create_table(
        'integration_settings',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('firecrawl_api_key', sa.String(length=500), server_default='', nullable=True),
        sa.Column('openai_api_key', sa.String(length=500), server_default='', nullable=True),
        sa.Column('gemini_api_key', sa.String(length=500), server_default='', nullable=True),
        sa.Column('memento_api_key', sa.String(length=500), server_default='', nullable=True),
        sa.Column('memento_endpoint', sa.String(length=255), server_default='https://api.memento.ai/v1', nullable=True),
        sa.Column('preferences', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], name='fk_integration_settings_org_id_organizations', ondelete='CASCADE'),
        sa.UniqueConstraint('org_id', name='uq_integration_settings_org_id')
    )

    # 17. Distributed Locks
    op.create_table(
        'distributed_locks',
        sa.Column('lock_key', sa.String(length=255), primary_key=True),
        sa.Column('owner_id', sa.String(length=255), nullable=False),
        sa.Column('generation', sa.Integer(), server_default='1', nullable=False),
        sa.Column('acquired_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False)
    )

def downgrade() -> None:
    # Drop in reverse topological order
    op.drop_table('distributed_locks')
    op.drop_table('integration_settings')
    op.drop_table('audit_logs')
    op.drop_table('review_jobs')
    op.drop_table('scheduled_reviews')
    op.drop_table('historical_assessments')
    op.drop_table('evidence_sources')
    op.drop_table('risk_findings')
    op.drop_table('technology_scores')
    op.drop_table('assessments')
    op.drop_table('project_technologies')
    op.drop_table('technologies')
    op.drop_table('projects')
    op.drop_table('revoked_tokens')
    op.drop_table('organization_invitations')
    op.drop_table('users')
    op.drop_table('organizations')
