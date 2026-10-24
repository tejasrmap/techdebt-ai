"""v2_commercial_saas_platform

Revision ID: 003_v2_commercial_saas_platform
Revises: 002_transactional_fencing_and_memento_cleanup
Create Date: 2026-11-06 16:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003_v2_commercial_saas_platform'
down_revision: Union[str, Sequence[str], None] = '002_transactional_fencing_and_memento_cleanup'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. User model columns for verification, reset, and MFA
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('is_verified', sa.Boolean(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('verification_token', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('verification_token_expires_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('reset_password_token', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('reset_password_token_expires_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('mfa_enabled', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('mfa_secret', sa.String(length=255), nullable=True))

    # 2. Assessment model columns for 10-dimension scoring and code metrics
    with op.batch_alter_table('assessments') as batch_op:
        batch_op.add_column(sa.Column('scoring_version', sa.String(length=20), server_default='v2.0.0', nullable=False))
        batch_op.add_column(sa.Column('technical_debt_ratio', sa.Float(), server_default='0.0', nullable=False))
        batch_op.add_column(sa.Column('estimated_remediation_hours', sa.Float(), server_default='0.0', nullable=False))
        batch_op.add_column(sa.Column('lines_of_code', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('files_analyzed', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('code_maintainability_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('architecture_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('dependency_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('security_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('test_quality_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('documentation_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('reliability_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('performance_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('complexity_score', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('upgrade_risk_score', sa.Float(), nullable=True))

    # 3. Create teams table
    op.create_table(
        'teams',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.UniqueConstraint('org_id', 'name', name='uq_org_team_name')
    )
    op.create_index('idx_teams_org', 'teams', ['org_id'])

    # 4. Create team_members table
    op.create_table(
        'team_members',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('team_id', sa.String(length=36), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(length=50), server_default='Member'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.UniqueConstraint('team_id', 'user_id', name='uq_team_user')
    )
    op.create_index('idx_team_members_team', 'team_members', ['team_id'])
    op.create_index('idx_team_members_user', 'team_members', ['user_id'])

    # 5. Create project_team_permissions table
    op.create_table(
        'project_team_permissions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('project_id', sa.String(length=36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('team_id', sa.String(length=36), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('permission', sa.String(length=50), server_default='write'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.UniqueConstraint('project_id', 'team_id', name='uq_project_team')
    )
    op.create_index('idx_ptp_project', 'project_team_permissions', ['project_id'])
    op.create_index('idx_ptp_team', 'project_team_permissions', ['team_id'])

    # 6. Create repository_connections table
    op.create_table(
        'repository_connections',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', sa.String(length=36), sa.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True),
        sa.Column('provider', sa.String(length=50), server_default='github'),
        sa.Column('repo_name', sa.String(length=255), nullable=False),
        sa.Column('repo_full_name', sa.String(length=255), server_default=''),
        sa.Column('repo_url', sa.String(length=500), nullable=False),
        sa.Column('default_branch', sa.String(length=100), server_default='main'),
        sa.Column('selected_branch', sa.String(length=100), server_default='main'),
        sa.Column('is_private', sa.Boolean(), server_default='0'),
        sa.Column('auth_type', sa.String(length=50), server_default='token'),
        sa.Column('encrypted_access_token', sa.String(length=1000), server_default=''),
        sa.Column('webhook_secret', sa.String(length=255), server_default=''),
        sa.Column('status', sa.String(length=50), server_default='connected'),
        sa.Column('last_sync_status', sa.String(length=50), server_default='ready'),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('commit_sha', sa.String(length=100), server_default=''),
        sa.Column('commit_message', sa.Text(), server_default=''),
        sa.Column('commit_author', sa.String(length=255), server_default=''),
        sa.Column('file_count', sa.Integer(), server_default='0'),
        sa.Column('size_bytes', sa.Integer(), server_default='0'),
        sa.Column('metadata_json', sa.JSON(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'))
    )
    op.create_index('idx_repo_org', 'repository_connections', ['org_id'])
    op.create_index('idx_repo_project', 'repository_connections', ['project_id'])
    op.create_index('idx_repo_status', 'repository_connections', ['status'])

    # 7. Create code_findings table
    op.create_table(
        'code_findings',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('assessment_id', sa.String(length=36), sa.ForeignKey('assessments.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', sa.String(length=36), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('line_start', sa.Integer(), nullable=True),
        sa.Column('line_end', sa.Integer(), nullable=True),
        sa.Column('rule_id', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50), server_default='maintainability'),
        sa.Column('severity', sa.String(length=50), server_default='Medium'),
        sa.Column('confidence', sa.String(length=50), server_default='High'),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('explanation', sa.Text(), server_default=''),
        sa.Column('technical_evidence', sa.Text(), server_default=''),
        sa.Column('why_it_matters', sa.Text(), server_default=''),
        sa.Column('recommended_remediation', sa.Text(), server_default=''),
        sa.Column('estimated_remediation_hours', sa.Float(), server_default='1.0'),
        sa.Column('is_auto_verifiable', sa.Boolean(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'))
    )
    op.create_index('idx_code_finding_ass', 'code_findings', ['assessment_id'])
    op.create_index('idx_code_finding_proj', 'code_findings', ['project_id'])
    op.create_index('idx_code_finding_ass_sev', 'code_findings', ['assessment_id', 'severity'])
    op.create_index('idx_code_finding_rule', 'code_findings', ['rule_id'])
    op.create_index('idx_code_finding_cat', 'code_findings', ['category'])

    # 8. Create subscription_plans table
    op.create_table(
        'subscription_plans',
        sa.Column('id', sa.String(length=50), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('price_monthly_cents', sa.Integer(), server_default='0'),
        sa.Column('price_yearly_cents', sa.Integer(), server_default='0'),
        sa.Column('max_projects', sa.Integer(), server_default='3'),
        sa.Column('max_monthly_assessments', sa.Integer(), server_default='10'),
        sa.Column('max_repo_size_mb', sa.Integer(), server_default='25'),
        sa.Column('max_team_members', sa.Integer(), server_default='5'),
        sa.Column('ai_recommendations_enabled', sa.Boolean(), server_default='0'),
        sa.Column('advanced_code_analysis_enabled', sa.Boolean(), server_default='0'),
        sa.Column('retention_days', sa.Integer(), server_default='30'),
        sa.Column('features', sa.JSON(), server_default='[]'),
        sa.Column('is_active', sa.Boolean(), server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'))
    )

    # 9. Create subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan_id', sa.String(length=50), sa.ForeignKey('subscription_plans.id'), server_default='free', nullable=False),
        sa.Column('status', sa.String(length=50), server_default='active'),
        sa.Column('billing_cycle', sa.String(length=20), server_default='monthly'),
        sa.Column('stripe_customer_id', sa.String(length=255), server_default=''),
        sa.Column('stripe_subscription_id', sa.String(length=255), server_default=''),
        sa.Column('current_period_start', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.Column('current_period_end', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.Column('cancel_at_period_end', sa.Boolean(), server_default='0'),
        sa.Column('trial_ends_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.UniqueConstraint('org_id', name='uq_subscription_org')
    )
    op.create_index('idx_subs_org', 'subscriptions', ['org_id'])
    op.create_index('idx_subs_status', 'subscriptions', ['status'])

    # 10. Create usage_records table
    op.create_table(
        'usage_records',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('metric_type', sa.String(length=50), nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('count', sa.Float(), server_default='0.0'),
        sa.Column('limit', sa.Float(), server_default='0.0'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)')),
        sa.UniqueConstraint('org_id', 'metric_type', 'period', name='uq_org_metric_period')
    )
    op.create_index('idx_usage_org_metric', 'usage_records', ['org_id', 'metric_type'])

    # 11. Create invoices table
    op.create_table(
        'invoices',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('invoice_number', sa.String(length=100), unique=True, nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=10), server_default='usd'),
        sa.Column('status', sa.String(length=50), server_default='paid'),
        sa.Column('hosted_invoice_url', sa.String(length=500), server_default=''),
        sa.Column('pdf_url', sa.String(length=500), server_default=''),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'))
    )
    op.create_index('idx_invoices_org', 'invoices', ['org_id'])

    # 12. Create notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('org_id', sa.String(length=36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), server_default=''),
        sa.Column('category', sa.String(length=50), server_default='assessment'),
        sa.Column('severity', sa.String(length=50), server_default='info'),
        sa.Column('link', sa.String(length=500), server_default=''),
        sa.Column('is_read', sa.Boolean(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'))
    )
    op.create_index('idx_notif_org', 'notifications', ['org_id'])
    op.create_index('idx_notif_user', 'notifications', ['user_id'])
    op.create_index('idx_notif_read', 'notifications', ['is_read'])

    # 13. Create notification_preferences table
    op.create_table(
        'notification_preferences',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('email_assessment_completed', sa.Boolean(), server_default='1'),
        sa.Column('email_critical_risk', sa.Boolean(), server_default='1'),
        sa.Column('email_billing_alerts', sa.Boolean(), server_default='1'),
        sa.Column('email_weekly_digest', sa.Boolean(), server_default='1'),
        sa.Column('inapp_notifications', sa.Boolean(), server_default='1'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'))
    )

    # 14. Seed default subscription tiers
    subscription_plans_table = sa.table(
        'subscription_plans',
        sa.column('id', sa.String),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('price_monthly_cents', sa.Integer),
        sa.column('price_yearly_cents', sa.Integer),
        sa.column('max_projects', sa.Integer),
        sa.column('max_monthly_assessments', sa.Integer),
        sa.column('max_repo_size_mb', sa.Integer),
        sa.column('max_team_members', sa.Integer),
        sa.column('ai_recommendations_enabled', sa.Boolean),
        sa.column('advanced_code_analysis_enabled', sa.Boolean),
        sa.column('retention_days', sa.Integer),
        sa.column('features', sa.JSON),
        sa.column('is_active', sa.Boolean)
    )

    op.bulk_insert(
        subscription_plans_table,
        [
            {
                'id': 'free',
                'name': 'Community Free',
                'description': 'Essential dependency analysis for individual developers and open source.',
                'price_monthly_cents': 0,
                'price_yearly_cents': 0,
                'max_projects': 3,
                'max_monthly_assessments': 10,
                'max_repo_size_mb': 25,
                'max_team_members': 1,
                'ai_recommendations_enabled': False,
                'advanced_code_analysis_enabled': False,
                'retention_days': 14,
                'features': ['Dependency vulnerability scanning', 'Basic 8-factor score', 'CSV export', '14-day history'],
                'is_active': True
            },
            {
                'id': 'starter',
                'name': 'Team Starter',
                'description': 'Collaborative repository intelligence for growing engineering teams.',
                'price_monthly_cents': 4900,
                'price_yearly_cents': 47000,
                'max_projects': 10,
                'max_monthly_assessments': 50,
                'max_repo_size_mb': 100,
                'max_team_members': 5,
                'ai_recommendations_enabled': True,
                'advanced_code_analysis_enabled': True,
                'retention_days': 90,
                'features': ['GitHub & GitLab repository sync', 'AST source code analysis', 'Automated weekly schedule', 'PDF & CSV reports', 'AI recommendations', '90-day history'],
                'is_active': True
            },
            {
                'id': 'professional',
                'name': 'Engineering Pro',
                'description': 'Full-featured architectural intelligence, custom rules, and unlimited history.',
                'price_monthly_cents': 14900,
                'price_yearly_cents': 143000,
                'max_projects': 50,
                'max_monthly_assessments': 300,
                'max_repo_size_mb': 500,
                'max_team_members': 25,
                'ai_recommendations_enabled': True,
                'advanced_code_analysis_enabled': True,
                'retention_days': 365,
                'features': ['All Starter features', 'Bitbucket & private repos', '10-factor technical debt ratio', 'Refactoring strategy recipes', 'Team permission control', '1-year history'],
                'is_active': True
            },
            {
                'id': 'enterprise',
                'name': 'Enterprise Scale',
                'description': 'Dedicated scalability, custom SLAs, audit logs, and compliance reporting.',
                'price_monthly_cents': 49900,
                'price_yearly_cents': 479000,
                'max_projects': 200,
                'max_monthly_assessments': 2000,
                'max_repo_size_mb': 2000,
                'max_team_members': 200,
                'ai_recommendations_enabled': True,
                'advanced_code_analysis_enabled': True,
                'retention_days': 1825,
                'features': ['All Professional features', 'Dedicated worker pools', 'Custom compliance exports', 'Priority support & SLA', '5-year historical preservation', 'Single Sign-On (SSO)'],
                'is_active': True
            }
        ]
    )

def downgrade() -> None:
    op.drop_table('notification_preferences')
    op.drop_table('notifications')
    op.drop_table('invoices')
    op.drop_table('usage_records')
    op.drop_table('subscriptions')
    op.drop_table('subscription_plans')
    op.drop_table('code_findings')
    op.drop_table('repository_connections')
    op.drop_table('project_team_permissions')
    op.drop_table('team_members')
    op.drop_table('teams')

    with op.batch_alter_table('assessments') as batch_op:
        batch_op.drop_column('upgrade_risk_score')
        batch_op.drop_column('complexity_score')
        batch_op.drop_column('performance_score')
        batch_op.drop_column('reliability_score')
        batch_op.drop_column('documentation_score')
        batch_op.drop_column('test_quality_score')
        batch_op.drop_column('security_score')
        batch_op.drop_column('dependency_score')
        batch_op.drop_column('architecture_score')
        batch_op.drop_column('code_maintainability_score')
        batch_op.drop_column('files_analyzed')
        batch_op.drop_column('lines_of_code')
        batch_op.drop_column('estimated_remediation_hours')
        batch_op.drop_column('technical_debt_ratio')
        batch_op.drop_column('scoring_version')

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('mfa_secret')
        batch_op.drop_column('mfa_enabled')
        batch_op.drop_column('reset_password_token_expires_at')
        batch_op.drop_column('reset_password_token')
        batch_op.drop_column('verification_token_expires_at')
        batch_op.drop_column('verification_token')
        batch_op.drop_column('is_verified')

