CREATE TABLE IF NOT EXISTS audit_logs (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36), 
	org_id VARCHAR(36) NOT NULL, 
	action VARCHAR(100) NOT NULL, 
	resource_type VARCHAR(100) NOT NULL, 
	resource_id VARCHAR(100), 
	details JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_audit_logs PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action);

CREATE INDEX IF NOT EXISTS ix_audit_logs_org_id ON audit_logs (org_id);

CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at);

CREATE TABLE IF NOT EXISTS distributed_locks (
	lock_key VARCHAR(255) NOT NULL, 
	owner_id VARCHAR(255) NOT NULL, 
	generation INTEGER NOT NULL, 
	acquired_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	CONSTRAINT pk_distributed_locks PRIMARY KEY (lock_key)
);

CREATE TABLE IF NOT EXISTS organizations (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	slug VARCHAR(255) NOT NULL, 
	plan VARCHAR(50), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_organizations PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_organizations_slug ON organizations (slug);

CREATE UNIQUE INDEX IF NOT EXISTS ix_organizations_name ON organizations (name);

CREATE TABLE IF NOT EXISTS revoked_tokens (
	id VARCHAR(36) NOT NULL, 
	jti VARCHAR(255) NOT NULL, 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	revoked_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_revoked_tokens PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_revoked_tokens_jti ON revoked_tokens (jti);

CREATE TABLE IF NOT EXISTS subscription_plans (
	id VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	price_monthly_cents INTEGER, 
	price_yearly_cents INTEGER, 
	max_projects INTEGER, 
	max_monthly_assessments INTEGER, 
	max_repo_size_mb INTEGER, 
	max_team_members INTEGER, 
	ai_recommendations_enabled BOOLEAN, 
	advanced_code_analysis_enabled BOOLEAN, 
	retention_days INTEGER, 
	features JSON, 
	is_active BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_subscription_plans PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS technologies (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	ecosystem VARCHAR(100), 
	category VARCHAR(100), 
	latest_stable_version VARCHAR(100), 
	description TEXT, 
	website_url VARCHAR(500), 
	repo_url VARCHAR(500), 
	is_deprecated BOOLEAN, 
	is_eol BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_technologies PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_technologies_name ON technologies (name);

CREATE INDEX IF NOT EXISTS ix_technologies_ecosystem ON technologies (ecosystem);

CREATE TABLE IF NOT EXISTS integration_settings (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	firecrawl_api_key VARCHAR(500), 
	openai_api_key VARCHAR(500), 
	gemini_api_key VARCHAR(500), 
	preferences JSON, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_integration_settings PRIMARY KEY (id), 
	CONSTRAINT uq_integration_settings_org_id UNIQUE (org_id), 
	CONSTRAINT fk_integration_settings_org_id_organizations FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invoices (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	invoice_number VARCHAR(100) NOT NULL, 
	amount_cents INTEGER NOT NULL, 
	currency VARCHAR(10), 
	status VARCHAR(50), 
	hosted_invoice_url VARCHAR(500), 
	pdf_url VARCHAR(500), 
	paid_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_invoices PRIMARY KEY (id), 
	CONSTRAINT fk_invoices_org_id_organizations FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT uq_invoices_invoice_number UNIQUE (invoice_number)
);

CREATE INDEX IF NOT EXISTS ix_invoices_status ON invoices (status);

CREATE INDEX IF NOT EXISTS ix_invoices_org_id ON invoices (org_id);

CREATE INDEX IF NOT EXISTS ix_invoices_created_at ON invoices (created_at);

CREATE TABLE IF NOT EXISTS projects (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	description TEXT, 
	repository_url VARCHAR(500), 
	languages JSON, 
	frameworks JSON, 
	owner_name VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	last_assessment_date TIMESTAMP WITHOUT TIME ZONE, 
	is_archived BOOLEAN, 
	archived_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_projects PRIMARY KEY (id), 
	CONSTRAINT uq_org_project_name UNIQUE (org_id, name), 
	CONSTRAINT fk_projects_org_id_organizations FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_projects_org_id ON projects (org_id);

CREATE INDEX IF NOT EXISTS ix_projects_created_at ON projects (created_at);

CREATE INDEX IF NOT EXISTS ix_projects_is_archived ON projects (is_archived);

CREATE INDEX IF NOT EXISTS idx_project_org_created ON projects (org_id, created_at);

CREATE TABLE IF NOT EXISTS subscriptions (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	plan_id VARCHAR(50) NOT NULL, 
	status VARCHAR(50), 
	billing_cycle VARCHAR(20), 
	stripe_customer_id VARCHAR(255), 
	stripe_subscription_id VARCHAR(255), 
	current_period_start TIMESTAMP WITHOUT TIME ZONE, 
	current_period_end TIMESTAMP WITHOUT TIME ZONE, 
	cancel_at_period_end BOOLEAN, 
	trial_ends_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_subscriptions PRIMARY KEY (id), 
	CONSTRAINT uq_subscriptions_org_id UNIQUE (org_id), 
	CONSTRAINT fk_subscriptions_org_id_organizations FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_subscriptions_plan_id_subscription_plans FOREIGN KEY(plan_id) REFERENCES subscription_plans (id)
);

CREATE INDEX IF NOT EXISTS ix_subscriptions_status ON subscriptions (status);

CREATE INDEX IF NOT EXISTS ix_subscriptions_stripe_customer_id ON subscriptions (stripe_customer_id);

CREATE INDEX IF NOT EXISTS ix_subscriptions_stripe_subscription_id ON subscriptions (stripe_subscription_id);

CREATE TABLE IF NOT EXISTS teams (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	description TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_teams PRIMARY KEY (id), 
	CONSTRAINT uq_org_team_name UNIQUE (org_id, name), 
	CONSTRAINT fk_teams_org_id_organizations FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_teams_org_id ON teams (org_id);

CREATE TABLE IF NOT EXISTS usage_records (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	metric_type VARCHAR(50) NOT NULL, 
	period VARCHAR(7) NOT NULL, 
	count FLOAT, 
	"limit" FLOAT, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_usage_records PRIMARY KEY (id), 
	CONSTRAINT uq_org_metric_period UNIQUE (org_id, metric_type, period), 
	CONSTRAINT fk_usage_records_org_id_organizations FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_usage_records_org_id ON usage_records (org_id);

CREATE INDEX IF NOT EXISTS ix_usage_records_period ON usage_records (period);

CREATE INDEX IF NOT EXISTS ix_usage_records_metric_type ON usage_records (metric_type);

CREATE TABLE IF NOT EXISTS users (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	hashed_password VARCHAR(255) NOT NULL, 
	full_name VARCHAR(255) NOT NULL, 
	role VARCHAR(50), 
	is_active BOOLEAN, 
	is_verified BOOLEAN, 
	verification_token VARCHAR(255), 
	verification_token_expires_at TIMESTAMP WITHOUT TIME ZONE, 
	reset_password_token VARCHAR(255), 
	reset_password_token_expires_at TIMESTAMP WITHOUT TIME ZONE, 
	mfa_enabled BOOLEAN, 
	mfa_secret VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT fk_users_org_id_organizations FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_users_org_id ON users (org_id);

CREATE INDEX IF NOT EXISTS ix_users_verification_token ON users (verification_token);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE INDEX IF NOT EXISTS ix_users_reset_password_token ON users (reset_password_token);

CREATE TABLE IF NOT EXISTS ai_usage_ledgers (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36), 
	provider VARCHAR(50) NOT NULL, 
	model VARCHAR(100) NOT NULL, 
	operation_type VARCHAR(100), 
	prompt_tokens INTEGER, 
	completion_tokens INTEGER, 
	total_tokens INTEGER, 
	cost_usd FLOAT, 
	latency_ms FLOAT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_ai_usage_ledgers PRIMARY KEY (id), 
	CONSTRAINT fk_ai_usage_ledgers_org_id_organizations FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_ai_usage_ledgers_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_ai_usage_ledgers_user_id ON ai_usage_ledgers (user_id);

CREATE INDEX IF NOT EXISTS ix_ai_usage_ledgers_created_at ON ai_usage_ledgers (created_at);

CREATE INDEX IF NOT EXISTS ix_ai_usage_ledgers_provider ON ai_usage_ledgers (provider);

CREATE INDEX IF NOT EXISTS ix_ai_usage_ledgers_org_id ON ai_usage_ledgers (org_id);

CREATE TABLE IF NOT EXISTS assessments (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	fencing_generation INTEGER NOT NULL, 
	trigger_type VARCHAR(50), 
	status VARCHAR(50), 
	overall_health_score FLOAT, 
	risk_classification VARCHAR(50), 
	confidence_level VARCHAR(50), 
	summary TEXT, 
	raw_output JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	scoring_version VARCHAR(20), 
	technical_debt_ratio FLOAT, 
	estimated_remediation_hours FLOAT, 
	lines_of_code INTEGER, 
	files_analyzed INTEGER, 
	code_maintainability_score FLOAT, 
	architecture_score FLOAT, 
	dependency_score FLOAT, 
	security_score FLOAT, 
	test_quality_score FLOAT, 
	documentation_score FLOAT, 
	reliability_score FLOAT, 
	performance_score FLOAT, 
	complexity_score FLOAT, 
	upgrade_risk_score FLOAT, 
	CONSTRAINT pk_assessments PRIMARY KEY (id), 
	CONSTRAINT fk_assessments_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_assessments_status ON assessments (status);

CREATE INDEX IF NOT EXISTS idx_assessment_project_created ON assessments (project_id, created_at);

CREATE INDEX IF NOT EXISTS ix_assessments_created_at ON assessments (created_at);

CREATE INDEX IF NOT EXISTS ix_assessments_project_id ON assessments (project_id);

CREATE TABLE IF NOT EXISTS notification_preferences (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	email_assessment_completed BOOLEAN, 
	email_critical_risk BOOLEAN, 
	email_billing_alerts BOOLEAN, 
	email_weekly_digest BOOLEAN, 
	inapp_notifications BOOLEAN, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_notification_preferences PRIMARY KEY (id), 
	CONSTRAINT uq_notification_preferences_user_id UNIQUE (user_id), 
	CONSTRAINT fk_notification_preferences_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36), 
	title VARCHAR(255) NOT NULL, 
	message TEXT, 
	category VARCHAR(50), 
	severity VARCHAR(50), 
	link VARCHAR(500), 
	is_read BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_notifications PRIMARY KEY (id), 
	CONSTRAINT fk_notifications_org_id_organizations FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_notifications_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_notifications_org_id ON notifications (org_id);

CREATE INDEX IF NOT EXISTS ix_notifications_is_read ON notifications (is_read);

CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id);

CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications (created_at);

CREATE INDEX IF NOT EXISTS ix_notifications_category ON notifications (category);

CREATE TABLE IF NOT EXISTS organization_invitations (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	role VARCHAR(50), 
	token VARCHAR(255), 
	token_hash VARCHAR(64), 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	is_accepted BOOLEAN, 
	accepted_at TIMESTAMP WITHOUT TIME ZONE, 
	invited_by_id VARCHAR(36), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_organization_invitations PRIMARY KEY (id), 
	CONSTRAINT fk_organization_invitations_org_id_organizations FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_organization_invitations_invited_by_id_users FOREIGN KEY(invited_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_organization_invitations_email ON organization_invitations (email);

CREATE UNIQUE INDEX IF NOT EXISTS ix_organization_invitations_token ON organization_invitations (token);

CREATE INDEX IF NOT EXISTS ix_organization_invitations_org_id ON organization_invitations (org_id);

CREATE UNIQUE INDEX IF NOT EXISTS ix_organization_invitations_token_hash ON organization_invitations (token_hash);

CREATE INDEX IF NOT EXISTS idx_invitation_org_email ON organization_invitations (org_id, email);

CREATE TABLE IF NOT EXISTS project_team_permissions (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	team_id VARCHAR(36) NOT NULL, 
	permission VARCHAR(50), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_project_team_permissions PRIMARY KEY (id), 
	CONSTRAINT uq_project_team UNIQUE (project_id, team_id), 
	CONSTRAINT fk_project_team_permissions_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	CONSTRAINT fk_project_team_permissions_team_id_teams FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_project_team_permissions_project_id ON project_team_permissions (project_id);

CREATE INDEX IF NOT EXISTS ix_project_team_permissions_team_id ON project_team_permissions (team_id);

CREATE TABLE IF NOT EXISTS project_technologies (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	technology_id VARCHAR(36) NOT NULL, 
	installed_version VARCHAR(100), 
	is_direct_dep BOOLEAN, 
	file_source VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_project_technologies PRIMARY KEY (id), 
	CONSTRAINT uq_project_technology UNIQUE (project_id, technology_id), 
	CONSTRAINT fk_project_technologies_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	CONSTRAINT fk_project_technologies_technology_id_technologies FOREIGN KEY(technology_id) REFERENCES technologies (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_project_technologies_project_id ON project_technologies (project_id);

CREATE INDEX IF NOT EXISTS ix_project_technologies_technology_id ON project_technologies (technology_id);

CREATE TABLE IF NOT EXISTS repository_connections (
	id VARCHAR(36) NOT NULL, 
	org_id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36), 
	provider VARCHAR(50), 
	repo_name VARCHAR(255) NOT NULL, 
	repo_full_name VARCHAR(255), 
	repo_url VARCHAR(500) NOT NULL, 
	default_branch VARCHAR(100), 
	selected_branch VARCHAR(100), 
	is_private BOOLEAN, 
	auth_type VARCHAR(50), 
	encrypted_access_token VARCHAR(1000), 
	webhook_secret VARCHAR(255), 
	status VARCHAR(50), 
	last_sync_status VARCHAR(50), 
	last_synced_at TIMESTAMP WITHOUT TIME ZONE, 
	commit_sha VARCHAR(100), 
	commit_message TEXT, 
	commit_author VARCHAR(255), 
	file_count INTEGER, 
	size_bytes INTEGER, 
	metadata_json JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_repository_connections PRIMARY KEY (id), 
	CONSTRAINT fk_repository_connections_org_id_organizations FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_repository_connections_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_repository_connections_org_id ON repository_connections (org_id);

CREATE INDEX IF NOT EXISTS ix_repository_connections_status ON repository_connections (status);

CREATE INDEX IF NOT EXISTS ix_repository_connections_project_id ON repository_connections (project_id);

CREATE TABLE IF NOT EXISTS scheduled_reviews (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	frequency VARCHAR(50), 
	cron_expression VARCHAR(100), 
	is_active BOOLEAN, 
	last_run_at TIMESTAMP WITHOUT TIME ZONE, 
	next_run_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_scheduled_reviews PRIMARY KEY (id), 
	CONSTRAINT fk_scheduled_reviews_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_scheduled_reviews_project_id ON scheduled_reviews (project_id);

CREATE TABLE IF NOT EXISTS team_members (
	id VARCHAR(36) NOT NULL, 
	team_id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	role VARCHAR(50), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_team_members PRIMARY KEY (id), 
	CONSTRAINT uq_team_user UNIQUE (team_id, user_id), 
	CONSTRAINT fk_team_members_team_id_teams FOREIGN KEY(team_id) REFERENCES teams (id) ON DELETE CASCADE, 
	CONSTRAINT fk_team_members_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_team_members_user_id ON team_members (user_id);

CREATE INDEX IF NOT EXISTS ix_team_members_team_id ON team_members (team_id);

CREATE TABLE IF NOT EXISTS code_findings (
	id VARCHAR(36) NOT NULL, 
	assessment_id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	file_path VARCHAR(500) NOT NULL, 
	line_start INTEGER, 
	line_end INTEGER, 
	rule_id VARCHAR(100) NOT NULL, 
	category VARCHAR(50), 
	severity VARCHAR(50), 
	confidence VARCHAR(50), 
	title VARCHAR(255) NOT NULL, 
	explanation TEXT, 
	technical_evidence TEXT, 
	why_it_matters TEXT, 
	recommended_remediation TEXT, 
	estimated_remediation_hours FLOAT, 
	is_auto_verifiable BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_code_findings PRIMARY KEY (id), 
	CONSTRAINT fk_code_findings_assessment_id_assessments FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE, 
	CONSTRAINT fk_code_findings_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_code_findings_category ON code_findings (category);

CREATE INDEX IF NOT EXISTS ix_code_findings_assessment_id ON code_findings (assessment_id);

CREATE INDEX IF NOT EXISTS ix_code_findings_file_path ON code_findings (file_path);

CREATE INDEX IF NOT EXISTS ix_code_findings_created_at ON code_findings (created_at);

CREATE INDEX IF NOT EXISTS ix_code_findings_severity ON code_findings (severity);

CREATE INDEX IF NOT EXISTS ix_code_findings_rule_id ON code_findings (rule_id);

CREATE INDEX IF NOT EXISTS ix_code_findings_project_id ON code_findings (project_id);

CREATE INDEX IF NOT EXISTS idx_code_finding_ass_sev ON code_findings (assessment_id, severity);

CREATE TABLE IF NOT EXISTS evidence_sources (
	id VARCHAR(36) NOT NULL, 
	assessment_id VARCHAR(36) NOT NULL, 
	technology_id VARCHAR(36) NOT NULL, 
	url VARCHAR(1000) NOT NULL, 
	title VARCHAR(500), 
	source_type VARCHAR(100), 
	reliability_score FLOAT, 
	publication_date VARCHAR(100), 
	is_official BOOLEAN, 
	snippet TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_evidence_sources PRIMARY KEY (id), 
	CONSTRAINT fk_evidence_sources_assessment_id_assessments FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE, 
	CONSTRAINT fk_evidence_sources_technology_id_technologies FOREIGN KEY(technology_id) REFERENCES technologies (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_evidence_sources_technology_id ON evidence_sources (technology_id);

CREATE INDEX IF NOT EXISTS ix_evidence_sources_assessment_id ON evidence_sources (assessment_id);

CREATE TABLE IF NOT EXISTS historical_assessments (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	technology_id VARCHAR(36), 
	assessment_id VARCHAR(36) NOT NULL, 
	fencing_generation INTEGER NOT NULL, 
	health_score FLOAT NOT NULL, 
	score_delta FLOAT, 
	risk_classification VARCHAR(50), 
	snapshot_data JSON, 
	summary_of_changes TEXT, 
	new_risks_count INTEGER, 
	resolved_risks_count INTEGER, 
	storage_provider VARCHAR(50), 
	sync_status VARCHAR(50), 
	sync_error TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_historical_assessments PRIMARY KEY (id), 
	CONSTRAINT fk_historical_assessments_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	CONSTRAINT fk_historical_assessments_technology_id_technologies FOREIGN KEY(technology_id) REFERENCES technologies (id) ON DELETE CASCADE, 
	CONSTRAINT fk_historical_assessments_assessment_id_assessments FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_historical_assessments_assessment_id ON historical_assessments (assessment_id);

CREATE INDEX IF NOT EXISTS ix_historical_assessments_technology_id ON historical_assessments (technology_id);

CREATE INDEX IF NOT EXISTS idx_history_project_created ON historical_assessments (project_id, created_at);

CREATE INDEX IF NOT EXISTS ix_historical_assessments_created_at ON historical_assessments (created_at);

CREATE INDEX IF NOT EXISTS ix_historical_assessments_project_id ON historical_assessments (project_id);

CREATE TABLE IF NOT EXISTS review_jobs (
	id VARCHAR(36) NOT NULL, 
	scheduled_review_id VARCHAR(36) NOT NULL, 
	fencing_generation INTEGER NOT NULL, 
	status VARCHAR(50), 
	error_message TEXT, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_review_jobs PRIMARY KEY (id), 
	CONSTRAINT fk_review_jobs_scheduled_review_id_scheduled_reviews FOREIGN KEY(scheduled_review_id) REFERENCES scheduled_reviews (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_review_jobs_scheduled_review_id ON review_jobs (scheduled_review_id);

CREATE INDEX IF NOT EXISTS ix_review_jobs_status ON review_jobs (status);

CREATE TABLE IF NOT EXISTS risk_findings (
	id VARCHAR(36) NOT NULL, 
	assessment_id VARCHAR(36), 
	technology_id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	severity VARCHAR(50), 
	title VARCHAR(255) NOT NULL, 
	description TEXT, 
	business_impact TEXT, 
	technical_impact TEXT, 
	status VARCHAR(50), 
	assigned_to VARCHAR(36), 
	resolution_notes TEXT, 
	resolved_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	CONSTRAINT pk_risk_findings PRIMARY KEY (id), 
	CONSTRAINT fk_risk_findings_assessment_id_assessments FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE SET NULL, 
	CONSTRAINT fk_risk_findings_technology_id_technologies FOREIGN KEY(technology_id) REFERENCES technologies (id) ON DELETE CASCADE, 
	CONSTRAINT fk_risk_findings_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
	CONSTRAINT fk_risk_findings_assigned_to_users FOREIGN KEY(assigned_to) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_risk_findings_severity ON risk_findings (severity);

CREATE INDEX IF NOT EXISTS ix_risk_findings_assessment_id ON risk_findings (assessment_id);

CREATE INDEX IF NOT EXISTS ix_risk_findings_project_id ON risk_findings (project_id);

CREATE INDEX IF NOT EXISTS ix_risk_findings_created_at ON risk_findings (created_at);

CREATE INDEX IF NOT EXISTS idx_risk_proj_status_sev ON risk_findings (project_id, status, severity);

CREATE INDEX IF NOT EXISTS ix_risk_findings_status ON risk_findings (status);

CREATE INDEX IF NOT EXISTS ix_risk_findings_technology_id ON risk_findings (technology_id);

CREATE TABLE IF NOT EXISTS technology_scores (
	id VARCHAR(36) NOT NULL, 
	assessment_id VARCHAR(36) NOT NULL, 
	technology_id VARCHAR(36) NOT NULL, 
	overall_score FLOAT NOT NULL, 
	risk_classification VARCHAR(50), 
	maintenance_health FLOAT, 
	security_exposure FLOAT, 
	version_currency FLOAT, 
	community_activity FLOAT, 
	documentation_quality FLOAT, 
	ecosystem_compatibility FLOAT, 
	sustainability FLOAT, 
	upgrade_complexity FLOAT, 
	confidence_level VARCHAR(50), 
	recommended_action TEXT, 
	upgrade_complexity_level VARCHAR(50), 
	notes TEXT, 
	CONSTRAINT pk_technology_scores PRIMARY KEY (id), 
	CONSTRAINT fk_technology_scores_assessment_id_assessments FOREIGN KEY(assessment_id) REFERENCES assessments (id) ON DELETE CASCADE, 
	CONSTRAINT fk_technology_scores_technology_id_technologies FOREIGN KEY(technology_id) REFERENCES technologies (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_technology_scores_technology_id ON technology_scores (technology_id);

CREATE INDEX IF NOT EXISTS ix_technology_scores_assessment_id ON technology_scores (assessment_id);

CREATE INDEX IF NOT EXISTS idx_tech_score_assessment_tech ON technology_scores (assessment_id, technology_id);


CREATE TABLE IF NOT EXISTS public.alembic_version (
    version_num VARCHAR(64) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO public.alembic_version (version_num)
VALUES ('004_v3_ai_usage_ledgers_and_indexes')
ON CONFLICT (version_num) DO NOTHING;



CREATE INDEX IF NOT EXISTS ix_organization_invitations_invited_by_id
    ON public.organization_invitations (invited_by_id);
CREATE INDEX IF NOT EXISTS ix_risk_findings_assigned_to
    ON public.risk_findings (assigned_to);
CREATE INDEX IF NOT EXISTS ix_subscriptions_plan_id
    ON public.subscriptions (plan_id);
CREATE INDEX IF NOT EXISTS idx_ai_ledger_org_created
    ON public.ai_usage_ledgers (org_id, created_at);



CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA private TO authenticated, service_role;

CREATE OR REPLACE FUNCTION private.current_user_org_id()
RETURNS VARCHAR(36)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT COALESCE(
        NULLIF((SELECT auth.jwt() ->> 'org_id'), ''),
        (
            SELECT u.org_id
            FROM public.users u
            WHERE u.id = (SELECT auth.uid()::text)
               OR u.email = (SELECT auth.jwt() ->> 'email')
            LIMIT 1
        )
    );
$$;

CREATE OR REPLACE FUNCTION private.current_app_user_id()
RETURNS VARCHAR(36)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT COALESCE(
        (
            SELECT u.id
            FROM public.users u
            WHERE u.id = (SELECT auth.uid()::text)
               OR u.email = (SELECT auth.jwt() ->> 'email')
            LIMIT 1
        ),
        (SELECT auth.uid()::text)
    );
$$;

CREATE OR REPLACE FUNCTION private.can_access_project(target_project_id VARCHAR(36))
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM public.projects p
        WHERE p.id = target_project_id
          AND p.org_id = (SELECT private.current_user_org_id())
    );
$$;

REVOKE EXECUTE ON FUNCTION private.current_user_org_id() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION private.current_app_user_id() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION private.can_access_project(VARCHAR) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.current_user_org_id() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.current_app_user_id() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.can_access_project(VARCHAR) TO authenticated, service_role;


ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.distributed_locks ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.revoked_tokens ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.subscription_plans ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.technologies ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.integration_settings ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.invoices ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.teams ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.usage_records ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.ai_usage_ledgers ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.assessments ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.notification_preferences ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.organization_invitations ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.project_team_permissions ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.project_technologies ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.repository_connections ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.scheduled_reviews ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.team_members ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.code_findings ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.evidence_sources ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.historical_assessments ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.review_jobs ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.risk_findings ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.technology_scores ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;


-- Global read-only catalogs for authenticated users
DROP POLICY IF EXISTS subscription_plans_select_authenticated ON public.subscription_plans;
CREATE POLICY subscription_plans_select_authenticated ON public.subscription_plans
    FOR SELECT TO authenticated
    USING (is_active = true);

DROP POLICY IF EXISTS technologies_select_authenticated ON public.technologies;
CREATE POLICY technologies_select_authenticated ON public.technologies
    FOR SELECT TO authenticated
    USING (true);

-- Organization root table
DROP POLICY IF EXISTS organizations_tenant_isolation ON public.organizations;
CREATE POLICY organizations_tenant_isolation ON public.organizations
    FOR SELECT TO authenticated
    USING (id = (SELECT private.current_user_org_id()));

-- Direct org_id tenant-isolated tables
DROP POLICY IF EXISTS users_tenant_isolation ON public.users;
CREATE POLICY users_tenant_isolation ON public.users
    FOR SELECT TO authenticated
    USING (org_id = (SELECT private.current_user_org_id()));

DROP POLICY IF EXISTS organization_invitations_tenant_isolation ON public.organization_invitations;
CREATE POLICY organization_invitations_tenant_isolation ON public.organization_invitations
    FOR SELECT TO authenticated
    USING (org_id = (SELECT private.current_user_org_id()));

DROP POLICY IF EXISTS projects_tenant_isolation ON public.projects;
CREATE POLICY projects_tenant_isolation ON public.projects
    FOR ALL TO authenticated
    USING (org_id = (SELECT private.current_user_org_id()))
    WITH CHECK (org_id = (SELECT private.current_user_org_id()));

DROP POLICY IF EXISTS audit_logs_tenant_isolation ON public.audit_logs;
CREATE POLICY audit_logs_tenant_isolation ON public.audit_logs
    FOR SELECT TO authenticated
    USING (org_id = (SELECT private.current_user_org_id()));

DROP POLICY IF EXISTS teams_tenant_isolation ON public.teams;
CREATE POLICY teams_tenant_isolation ON public.teams
    FOR ALL TO authenticated
    USING (org_id = (SELECT private.current_user_org_id()))
    WITH CHECK (org_id = (SELECT private.current_user_org_id()));

DROP POLICY IF EXISTS repository_connections_tenant_isolation ON public.repository_connections;
CREATE POLICY repository_connections_tenant_isolation ON public.repository_connections
    FOR SELECT TO authenticated
    USING (org_id = (SELECT private.current_user_org_id()));

DROP POLICY IF EXISTS subscriptions_tenant_isolation ON public.subscriptions;
CREATE POLICY subscriptions_tenant_isolation ON public.subscriptions
    FOR SELECT TO authenticated
    USING (org_id = (SELECT private.current_user_org_id()));

DROP POLICY IF EXISTS usage_records_tenant_isolation ON public.usage_records;
CREATE POLICY usage_records_tenant_isolation ON public.usage_records
    FOR SELECT TO authenticated
    USING (org_id = (SELECT private.current_user_org_id()));

DROP POLICY IF EXISTS invoices_tenant_isolation ON public.invoices;
CREATE POLICY invoices_tenant_isolation ON public.invoices
    FOR SELECT TO authenticated
    USING (org_id = (SELECT private.current_user_org_id()));

DROP POLICY IF EXISTS notifications_tenant_isolation ON public.notifications;
CREATE POLICY notifications_tenant_isolation ON public.notifications
    FOR ALL TO authenticated
    USING (
        org_id = (SELECT private.current_user_org_id())
        AND (user_id IS NULL OR user_id = (SELECT private.current_app_user_id()))
    )
    WITH CHECK (
        org_id = (SELECT private.current_user_org_id())
    );

DROP POLICY IF EXISTS ai_usage_ledgers_tenant_isolation ON public.ai_usage_ledgers;
CREATE POLICY ai_usage_ledgers_tenant_isolation ON public.ai_usage_ledgers
    FOR SELECT TO authenticated
    USING (org_id = (SELECT private.current_user_org_id()));

-- Project-scoped child tables
DROP POLICY IF EXISTS project_technologies_tenant_isolation ON public.project_technologies;
CREATE POLICY project_technologies_tenant_isolation ON public.project_technologies
    FOR ALL TO authenticated
    USING ((SELECT private.can_access_project(project_id)))
    WITH CHECK ((SELECT private.can_access_project(project_id)));

DROP POLICY IF EXISTS assessments_tenant_isolation ON public.assessments;
CREATE POLICY assessments_tenant_isolation ON public.assessments
    FOR SELECT TO authenticated
    USING ((SELECT private.can_access_project(project_id)));

DROP POLICY IF EXISTS risk_findings_tenant_isolation ON public.risk_findings;
CREATE POLICY risk_findings_tenant_isolation ON public.risk_findings
    FOR ALL TO authenticated
    USING ((SELECT private.can_access_project(project_id)))
    WITH CHECK ((SELECT private.can_access_project(project_id)));

DROP POLICY IF EXISTS historical_assessments_tenant_isolation ON public.historical_assessments;
CREATE POLICY historical_assessments_tenant_isolation ON public.historical_assessments
    FOR SELECT TO authenticated
    USING ((SELECT private.can_access_project(project_id)));

DROP POLICY IF EXISTS scheduled_reviews_tenant_isolation ON public.scheduled_reviews;
CREATE POLICY scheduled_reviews_tenant_isolation ON public.scheduled_reviews
    FOR ALL TO authenticated
    USING ((SELECT private.can_access_project(project_id)))
    WITH CHECK ((SELECT private.can_access_project(project_id)));

DROP POLICY IF EXISTS code_findings_tenant_isolation ON public.code_findings;
CREATE POLICY code_findings_tenant_isolation ON public.code_findings
    FOR SELECT TO authenticated
    USING ((SELECT private.can_access_project(project_id)));

DROP POLICY IF EXISTS project_team_permissions_tenant_isolation ON public.project_team_permissions;
CREATE POLICY project_team_permissions_tenant_isolation ON public.project_team_permissions
    FOR SELECT TO authenticated
    USING ((SELECT private.can_access_project(project_id)));

-- Assessment/Review/Team/User linked child tables
DROP POLICY IF EXISTS technology_scores_tenant_isolation ON public.technology_scores;
CREATE POLICY technology_scores_tenant_isolation ON public.technology_scores
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.assessments a
            WHERE a.id = technology_scores.assessment_id
              AND (SELECT private.can_access_project(a.project_id))
        )
    );

DROP POLICY IF EXISTS evidence_sources_tenant_isolation ON public.evidence_sources;
CREATE POLICY evidence_sources_tenant_isolation ON public.evidence_sources
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.assessments a
            WHERE a.id = evidence_sources.assessment_id
              AND (SELECT private.can_access_project(a.project_id))
        )
    );

DROP POLICY IF EXISTS review_jobs_tenant_isolation ON public.review_jobs;
CREATE POLICY review_jobs_tenant_isolation ON public.review_jobs
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.scheduled_reviews sr
            WHERE sr.id = review_jobs.scheduled_review_id
              AND (SELECT private.can_access_project(sr.project_id))
        )
    );

DROP POLICY IF EXISTS team_members_tenant_isolation ON public.team_members;
CREATE POLICY team_members_tenant_isolation ON public.team_members
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.teams t
            WHERE t.id = team_members.team_id
              AND t.org_id = (SELECT private.current_user_org_id())
        )
    );

DROP POLICY IF EXISTS notification_preferences_owner_isolation ON public.notification_preferences;
CREATE POLICY notification_preferences_owner_isolation ON public.notification_preferences
    FOR ALL TO authenticated
    USING (user_id = (SELECT private.current_app_user_id()))
    WITH CHECK (user_id = (SELECT private.current_app_user_id()));

-- Internal / encrypted system tables: explicit backend service_role only policies
DROP POLICY IF EXISTS integration_settings_service_only ON public.integration_settings;
CREATE POLICY integration_settings_service_only ON public.integration_settings
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS revoked_tokens_service_only ON public.revoked_tokens;
CREATE POLICY revoked_tokens_service_only ON public.revoked_tokens
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS distributed_locks_service_only ON public.distributed_locks;
CREATE POLICY distributed_locks_service_only ON public.distributed_locks
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS alembic_version_service_only ON public.alembic_version;
CREATE POLICY alembic_version_service_only ON public.alembic_version
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);



INSERT INTO public.subscription_plans (
    id, name, description, price_monthly_cents, price_yearly_cents,
    max_projects, max_monthly_assessments, max_repo_size_mb, max_team_members,
    ai_recommendations_enabled, advanced_code_analysis_enabled, retention_days,
    features, is_active, created_at
) VALUES
(
    'free', 'Community Free',
    'Essential code quality and dependency health for solo developers',
    0, 0, 1, 10, 25, 1, false, true, 30,
    '["1 repository connection", "10 monthly assessments", "10-dimension debt score", "Basic code smell detection"]'::json,
    true, NOW()
),
(
    'starter', 'Team Starter',
    'Collaborative intelligence and dependency remediation for growing teams',
    4900, 49000, 5, 50, 100, 5, true, true, 90,
    '["Up to 5 repositories", "50 monthly assessments", "AI refactoring recipes", "Email & webhook alerts", "5 team seats"]'::json,
    true, NOW()
),
(
    'professional', 'Professional',
    'Complete architecture intelligence and automated governance for engineering organizations',
    19900, 199000, 50, 500, 500, 25, true, true, 365,
    '["Up to 50 repositories", "500 monthly assessments", "30/60/90-day modernization roadmaps", "Priority support", "25 team seats"]'::json,
    true, NOW()
),
(
    'enterprise', 'Enterprise',
    'Custom scale, unlimited repositories, dedicated VPC and SSO governance',
    49900, 499000, 1000, 10000, 2048, 1000, true, true, 1825,
    '["Unlimited repositories", "Unlimited assessments", "SAML SSO & custom RBAC", "Dedicated SLA & architect onboarding"]'::json,
    true, NOW()
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    price_monthly_cents = EXCLUDED.price_monthly_cents,
    price_yearly_cents = EXCLUDED.price_yearly_cents,
    max_projects = EXCLUDED.max_projects,
    max_monthly_assessments = EXCLUDED.max_monthly_assessments,
    max_repo_size_mb = EXCLUDED.max_repo_size_mb,
    max_team_members = EXCLUDED.max_team_members,
    ai_recommendations_enabled = EXCLUDED.ai_recommendations_enabled,
    advanced_code_analysis_enabled = EXCLUDED.advanced_code_analysis_enabled,
    retention_days = EXCLUDED.retention_days,
    features = EXCLUDED.features,
    is_active = EXCLUDED.is_active;

INSERT INTO public.technologies (
    id, name, ecosystem, category, latest_stable_version, description,
    website_url, repo_url, is_deprecated, is_eol, created_at, updated_at
) VALUES
    ('tech-react', 'react', 'npm', 'Framework', '19.0.0', 'The library for web and native user interfaces', 'https://react.dev', 'https://github.com/facebook/react', false, false, NOW(), NOW()),
    ('tech-moment', 'moment', 'npm', 'Library', '2.30.1', 'Parse, validate, manipulate, and display dates and times in JS (Maintenance only)', 'https://momentjs.com', 'https://github.com/moment/moment', true, false, NOW(), NOW()),
    ('tech-lodash', 'lodash', 'npm', 'Library', '4.17.21', 'Lodash modular utilities', 'https://lodash.com', 'https://github.com/lodash/lodash', false, false, NOW(), NOW()),
    ('tech-axios', 'axios', 'npm', 'Library', '1.7.9', 'Promise based HTTP client for the browser and node.js', 'https://axios-http.com', 'https://github.com/axios/axios', false, false, NOW(), NOW()),
    ('tech-fastapi', 'fastapi', 'pypi', 'Framework', '0.115.6', 'FastAPI framework, high performance, easy to learn, fast to code', 'https://fastapi.tiangolo.com', 'https://github.com/fastapi/fastapi', false, false, NOW(), NOW()),
    ('tech-sqlalchemy', 'sqlalchemy', 'pypi', 'ORM', '2.0.36', 'Database Abstraction Library for Python', 'https://www.sqlalchemy.org', 'https://github.com/sqlalchemy/sqlalchemy', false, false, NOW(), NOW()),
    ('tech-pydantic', 'pydantic', 'pypi', 'Library', '2.10.4', 'Data validation using Python type hints', 'https://docs.pydantic.dev', 'https://github.com/pydantic/pydantic', false, false, NOW(), NOW()),
    ('tech-cryptography', 'cryptography', 'pypi', 'Security', '44.0.0', 'Cryptographic recipes and primitives', 'https://cryptography.io', 'https://github.com/pyca/cryptography', false, false, NOW(), NOW())
ON CONFLICT (name) DO NOTHING;
