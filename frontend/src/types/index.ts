export type Role = 'Administrator' | 'Engineering Manager' | 'Developer' | 'Viewer';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  org_id: string;
  organization_name?: string;
  created_at: string;
}

export interface Project {
  id: string;
  org_id: string;
  name: string;
  description: string;
  repository_url: string;
  languages: string[];
  frameworks: string[];
  owner_name: string;
  created_at: string;
  updated_at: string;
  last_assessment_date?: string | null;
  technology_count: number;
  health_score?: number | null;
  risk_classification?: string | null;
}

export interface Technology {
  id: string;
  name: string;
  ecosystem: string;
  category: string;
  installed_version?: string;
  latest_stable_version: string;
  description: string;
  website_url?: string;
  repo_url?: string;
  is_deprecated: boolean;
  is_eol: boolean;
  health_score?: number | null;
  risk_classification?: string | null;
}

export interface EvidenceSource {
  id: string;
  url: string;
  title: string;
  source_type: string;
  reliability_score: number;
  publication_date?: string | null;
  is_official: boolean;
  snippet: string;
}

export interface TechnologyScore {
  technology_id: string;
  technology_name: string;
  installed_version: string;
  latest_stable_version: string;
  overall_score: number;
  risk_classification: string;
  maintenance_health: number;
  security_exposure: number;
  version_currency: number;
  community_activity: number;
  documentation_quality: number;
  ecosystem_compatibility: number;
  sustainability: number;
  upgrade_complexity: number;
  confidence_level: string;
  recommended_action: string;
  upgrade_complexity_level: string;
  notes: string;
  evidence: EvidenceSource[];
}

export interface Assessment {
  id: string;
  project_id: string;
  project_name?: string;
  trigger_type: string;
  status: string;
  overall_health_score: number;
  risk_classification: string;
  confidence_level: string;
  summary: string;
  created_at: string;
  scores: TechnologyScore[];
  risks_count: number;
  scoring_version?: string;
  technical_debt_ratio?: number;
  estimated_remediation_hours?: number;
  lines_of_code?: number;
  files_analyzed?: number;
  code_maintainability_score?: number;
  architecture_score?: number;
  dependency_score?: number;
  security_score?: number;
  test_quality_score?: number;
  documentation_score?: number;
  reliability_score?: number;
  performance_score?: number;
  complexity_score?: number;
  upgrade_risk_score?: number;
}

export interface RiskFinding {
  id: string;
  project_id: string;
  project_name?: string;
  technology_id: string;
  technology_name?: string;
  severity: 'Critical' | 'High' | 'Medium' | 'Low';
  title: string;
  description: string;
  business_impact: string;
  technical_impact: string;
  status: 'Open' | 'Investigating' | 'Planned' | 'In Progress' | 'Resolved' | 'Accepted Risk';
  assigned_to?: string | null;
  assignee_name?: string | null;
  resolution_notes: string;
  resolved_at?: string | null;
  created_at: string;
}

export interface ComparisonCategory {
  category: string;
  scores: Record<string, number>;
  analysis: string;
}

export interface TechnologyComparison {
  technologies: string[];
  categories: ComparisonCategory[];
  balanced_summary: string;
  tradeoffs: Record<string, string[]>;
  recommendations: string;
}

export interface HistoricalRecord {
  id: string;
  project_id: string;
  project_name: string;
  health_score: number;
  score_delta: number;
  risk_classification: string;
  summary_of_changes: string;
  new_risks_count: number;
  resolved_risks_count: number;
  created_at: string;
}

export interface ScheduledReview {
  id: string;
  project_id: string;
  project_name?: string;
  frequency: string;
  cron_expression: string;
  is_active: boolean;
  last_run_at?: string | null;
  next_run_at?: string | null;
  created_at: string;
}

export interface DashboardOverview {
  total_projects: number;
  total_technologies: number;
  technologies_requiring_attention: number;
  critical_technology_risks: number;
  overall_health_score: number;
  outdated_dependencies: number;
  declining_maintenance_count: number;
  health_distribution: Record<string, number>;
  risk_distribution: Record<string, number>;
  recent_assessments: Array<{
    id: string;
    project_name: string;
    overall_health_score: number;
    risk_classification: string;
    confidence_level: string;
    created_at: string;
  }>;
  historical_trend: Array<{
    date: string;
    health_score: number;
    score_delta: number;
  }>;
  project_health_breakdown: Array<{
    project_id: string;
    project_name: string;
    technology_count: number;
    health_score: number;
    risk_classification: string;
  }>;
}

export interface IntegrationSettings {
  firecrawl_configured: boolean;
  openai_configured: boolean;
  gemini_configured: boolean;
  historical_memory_storage?: string;
  memento_configured?: boolean;
  memento_mode?: string;
  memento_endpoint?: string;
  preferences: Record<string, any>;
}


// Commercial SaaS Types (v2.0.0)
export interface CodeFinding {
  id: string;
  assessment_id: string;
  project_id: string;
  file_path: string;
  line_start?: number;
  line_end?: number;
  rule_id: string;
  category: 'maintainability' | 'architecture' | 'security' | 'reliability' | 'complexity';
  severity: 'Critical' | 'High' | 'Medium' | 'Low' | 'Info';
  confidence: string;
  title: string;
  explanation: string;
  technical_evidence: string;
  why_it_matters: string;
  recommended_remediation: string;
  estimated_remediation_hours: number;
  is_auto_verifiable: boolean;
  created_at: string;
}

export interface RepositoryConnection {
  id: string;
  project_id: string;
  provider: string;
  repo_url?: string;
  branch: string;
  status: string;
  commit_sha?: string;
  file_count: number;
  size_bytes: number;
  last_synced_at?: string | null;
}

export interface SubscriptionPlan {
  id: string;
  slug: string;
  name: string;
  description: string;
  price_monthly: number;
  price_annual: number;
  max_projects: number;
  max_assessments_per_month: number;
  max_team_members: number;
  features: string[];
}

export interface Subscription {
  subscription_id: string;
  org_id: string;
  plan_name: string;
  plan_slug: string;
  status: string;
  billing_cycle: string;
  current_period_start?: string;
  current_period_end?: string;
  cancel_at_period_end: boolean;
  price_monthly: number;
  price_annual: number;
  limits: {
    max_projects: number;
    max_assessments_per_month: number;
    max_team_members: number;
  };
  features: Record<string, any>;
  current_usage: Record<string, number>;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  amount_due?: number;
  amount_paid?: number;
  currency: string;
  status: string;
  period_start?: string;
  period_end?: string;
  hosted_invoice_url?: string;
  created_at: string;
}

export interface Team {
  id: string;
  name: string;
  description?: string;
  member_count: number;
  project_count: number;
  created_at: string;
}

export interface Notification {
  id: string;
  title: string;
  message: string;
  category: string;
  severity: string;
  link?: string;
  is_read: boolean;
  created_at: string;
}
