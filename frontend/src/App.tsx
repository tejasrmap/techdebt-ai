import React, { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Sidebar, NavItem } from './components/Sidebar';
import { Navbar } from './components/Navbar';
import { LandingView } from './views/LandingView';
import { DashboardView } from './views/DashboardView';
import { ProjectsView } from './views/ProjectsView';
import { TechnologiesView } from './views/TechnologiesView';
import { AssessmentsView } from './views/AssessmentsView';
import { RiskCenterView } from './views/RiskCenterView';
import { ComparisonView } from './views/ComparisonView';
import { HistoricalIntelligenceView } from './views/HistoricalIntelligenceView';
import { ReportsView } from './views/ReportsView';
import { IntegrationsView } from './views/IntegrationsView';
import { SettingsView } from './views/SettingsView';
import { PricingView } from './views/PricingView';
import { BillingView } from './views/BillingView';
import { CodeFindingsView } from './views/CodeFindingsView';
import { RepositoryView } from './views/RepositoryView';
import { TeamManagementView } from './views/TeamManagementView';
import { NotificationsView } from './views/NotificationsView';
import { UserProfileView } from './views/UserProfileView';

const MainApp: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth();
  const [currentTab, setCurrentTab] = useState<NavItem>('overview');
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [targetAssessmentProjectId, setTargetAssessmentProjectId] = useState<string | undefined>(undefined);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-9 h-9 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs font-mono text-slate-400">Loading TechDebt AI Session...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LandingView />;
  }

  const handleRunAssessmentFromProjects = (projectId: string) => {
    setTargetAssessmentProjectId(projectId);
    setCurrentTab('assessments');
  };

  const getPageInfo = (): { title: string; subtitle?: string } => {
    switch (currentTab) {
      case 'overview':
        return { title: 'Executive Overview', subtitle: 'Architecture health and dependency risk posture' };
      case 'projects':
        return { title: 'Software Projects', subtitle: 'Manage codebases and dependency manifests' };
      case 'repositories':
        return { title: 'Repositories & CI/CD', subtitle: 'Source repository connections and webhook ingestion' };
      case 'findings':
        return { title: 'Code Diagnostics & Findings', subtitle: 'Fine-grained source code smells, security vulnerabilities, and remediation recipes' };
      case 'technologies':
        return { title: 'Technology Catalog', subtitle: 'Catalog of all packages, libraries, and frameworks' };
      case 'assessments':
        return { title: 'Architecture Debt Reviews', subtitle: '10-dimension evidence-grounded AI assessments and Technical Debt Ratio (TDR)' };
      case 'risks':
        return { title: 'Risk Management Center', subtitle: 'Track, prioritize, and remediate technical debt' };
      case 'compare':
        return { title: 'Technology Comparison', subtitle: 'Balanced architectural trade-off evaluations' };
      case 'history':
        return { title: 'Historical Intelligence', subtitle: 'Longitudinal memory and regression trends' };
      case 'reports':
        return { title: 'Audit & Executive Reports', subtitle: 'Download board-ready PDFs and CSV audit logs' };
      case 'billing':
        return { title: 'Subscription & Billing', subtitle: 'Usage quotas, plan management, and invoices' };
      case 'teams':
        return { title: 'Teams & Squads', subtitle: 'Engineering team rosters and repository permissions' };
      case 'notifications':
        return { title: 'Notifications & Alerts', subtitle: 'Real-time assessment completion and critical risk alerts' };
      case 'pricing':
        return { title: 'Commercial Pricing Plans', subtitle: 'Predictable tier comparison and plan upgrades' };
      case 'profile':
        return { title: 'Account & Security', subtitle: 'Personal credentials, profile, and two-factor authentication' };
      case 'integrations':
        return { title: 'Service Integrations', subtitle: 'Web intelligence, historical memory, and GenAI inference connectivity' };
      case 'settings':
        return { title: 'Settings & Schedules', subtitle: 'Organization configuration and review automation' };
      default:
        return { title: 'TechDebt AI' };
    }
  };

  const pageInfo = getPageInfo();

  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Skip to Main Content Link for Keyboard and Screen Reader Accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:px-4 focus:py-2 focus:bg-indigo-600 focus:text-white focus:rounded-md focus:shadow-xl focus:outline-none focus:ring-2 focus:ring-white text-xs font-semibold"
      >
        Skip to main content
      </a>

      {/* Responsive Sidebar Navigation */}
      <Sidebar
        currentTab={currentTab}
        onSelectTab={setCurrentTab}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

      {/* Main Workspace Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Navbar
          title={pageInfo.title}
          subtitle={pageInfo.subtitle}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          isSidebarOpen={isSidebarOpen}
        />

        <main id="main-content" role="main" tabIndex={-1} className="flex-1 overflow-y-auto focus:outline-none">
          {currentTab === 'overview' && <DashboardView onNavigate={setCurrentTab} />}
          {currentTab === 'projects' && <ProjectsView onRunAssessment={handleRunAssessmentFromProjects} />}
          {currentTab === 'repositories' && <RepositoryView />}
          {currentTab === 'findings' && <CodeFindingsView />}
          {currentTab === 'technologies' && <TechnologiesView />}
          {currentTab === 'assessments' && <AssessmentsView initialProjectId={targetAssessmentProjectId} />}
          {currentTab === 'risks' && <RiskCenterView />}
          {currentTab === 'compare' && <ComparisonView />}
          {currentTab === 'history' && <HistoricalIntelligenceView />}
          {currentTab === 'reports' && <ReportsView />}
          {currentTab === 'billing' && <BillingView onNavigate={setCurrentTab} />}
          {currentTab === 'teams' && <TeamManagementView />}
          {currentTab === 'notifications' && <NotificationsView />}
          {currentTab === 'pricing' && <PricingView />}
          {currentTab === 'profile' && <UserProfileView />}
          {currentTab === 'integrations' && <IntegrationsView />}
          {currentTab === 'settings' && <SettingsView />}
        </main>
      </div>
    </div>
  );
};

export default function App() {
  return (
    <AuthProvider>
      <MainApp />
    </AuthProvider>
  );
}
