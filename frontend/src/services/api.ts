import axios from 'axios';
import {
  User, Project, Technology, Assessment, RiskFinding,
  TechnologyComparison, HistoricalRecord, ScheduledReview,
  DashboardOverview, IntegrationSettings
} from '../types';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('techdebt_token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear token if invalid
      localStorage.removeItem('techdebt_token');
      localStorage.removeItem('techdebt_user');
    }
    return Promise.reject(error);
  }
);

export const apiClient = {
  // Auth & Team Invitations
  login: async (email: string, password: string) => {
    const res = await api.post('/auth/login', { email, password });
    return res.data;
  },
  register: async (payload: { email: string; password: string; full_name: string; organization_name: string }) => {
    const res = await api.post('/auth/register', payload);
    return res.data;
  },
  getMe: async (): Promise<User> => {
    const res = await api.get('/auth/me');
    return res.data;
  },
  createInvitation: async (payload: { email: string; role: string }) => {
    const res = await api.post('/auth/invitations', payload);
    return res.data;
  },
  listInvitations: async () => {
    const res = await api.get('/auth/invitations');
    return res.data;
  },
  revokeInvitation: async (id: string) => {
    await api.delete(`/auth/invitations/${id}`);
  },
  acceptInvitation: async (payload: { token: string; full_name: string; password: string }) => {
    const res = await api.post('/auth/accept-invitation', payload);
    return res.data;
  },

  // Dashboard
  getDashboardOverview: async (): Promise<DashboardOverview> => {
    const res = await api.get('/dashboard/overview');
    return res.data;
  },

  // Projects
  getProjects: async (): Promise<Project[]> => {
    const res = await api.get('/projects');
    return res.data;
  },
  getProject: async (id: string): Promise<Project> => {
    const res = await api.get(`/projects/${id}`);
    return res.data;
  },
  createProject: async (project: Partial<Project>): Promise<Project> => {
    const res = await api.post('/projects', project);
    return res.data;
  },
  updateProject: async (id: string, project: Partial<Project>): Promise<Project> => {
    const res = await api.put(`/projects/${id}`, project);
    return res.data;
  },
  deleteProject: async (id: string) => {
    await api.delete(`/projects/${id}`);
  },

  // Technologies
  getTechnologies: async (projectId?: string): Promise<Technology[]> => {
    const res = await api.get('/technologies', { params: { project_id: projectId } });
    return res.data;
  },
  addTechnology: async (payload: { name: string; project_id?: string; ecosystem?: string; installed_version?: string }): Promise<Technology> => {
    const res = await api.post('/technologies', payload);
    return res.data;
  },
  importDependencies: async (projectId: string, fileName: string, content: string) => {
    const res = await api.post('/technologies/import', {
      project_id: projectId,
      file_name: fileName,
      content,
    });
    return res.data;
  },
  removeTechnologyFromProject: async (projectId: string, techId: string) => {
    const res = await api.delete(`/technologies/${projectId}/remove/${techId}`);
    return res.data;
  },

  // Assessments
  runAssessment: async (projectId: string): Promise<Assessment> => {
    const res = await api.post('/assessments/run', { project_id: projectId });
    return res.data;
  },
  getAssessments: async (projectId?: string): Promise<Assessment[]> => {
    const res = await api.get('/assessments', { params: { project_id: projectId } });
    return res.data;
  },
  getAssessment: async (id: string): Promise<Assessment> => {
    const res = await api.get(`/assessments/${id}`);
    return res.data;
  },
  getAssessmentComparison: async (id: string) => {
    const res = await api.get(`/assessments/${id}/comparison`);
    return res.data;
  },

  // Risks
  getRisks: async (params?: { project_id?: string; status?: string; severity?: string }): Promise<RiskFinding[]> => {
    const res = await api.get('/risks', { params });
    return res.data;
  },
  updateRisk: async (id: string, update: Partial<RiskFinding>): Promise<RiskFinding> => {
    const res = await api.put(`/risks/${id}`, update);
    return res.data;
  },
  resolveRisk: async (id: string, notes?: string): Promise<RiskFinding> => {
    const res = await api.post(`/risks/${id}/resolve`, null, { params: { resolution_notes: notes } });
    return res.data;
  },

  // Intelligence & Comparison
  crawlTechnology: async (technology: string, ecosystem = 'npm', installedVersion = 'latest') => {
    const res = await api.post('/intelligence/crawl', null, {
      params: { technology, ecosystem, installed_version: installedVersion },
    });
    return res.data;
  },
  compareTechnologies: async (techNames: string[]): Promise<TechnologyComparison> => {
    const res = await api.post('/intelligence/compare', { technology_names: techNames });
    return res.data;
  },
  getHistoricalMemory: async (projectId?: string): Promise<{ memory_provider: string; records: HistoricalRecord[] }> => {
    const res = await api.get('/intelligence/history', { params: { project_id: projectId } });
    return res.data;
  },

  // Reports
  getReportsList: async () => {
    const res = await api.get('/reports');
    return res.data;
  },
  getPdfReportUrl: (assessmentId: string) => `/api/v1/reports/pdf/${assessmentId}`,
  getCsvReportUrl: (assessmentId: string) => `/api/v1/reports/csv/${assessmentId}`,

  // Scheduler
  getSchedules: async (): Promise<ScheduledReview[]> => {
    const res = await api.get('/scheduler');
    return res.data;
  },
  createSchedule: async (payload: { project_id: string; frequency: string; cron_expression?: string }): Promise<ScheduledReview> => {
    const res = await api.post('/scheduler', payload);
    return res.data;
  },
  triggerScheduleNow: async (scheduleId: string) => {
    const res = await api.post(`/scheduler/trigger/${scheduleId}`);
    return res.data;
  },
  deleteSchedule: async (scheduleId: string) => {
    await api.delete(`/scheduler/${scheduleId}`);
  },

  // Settings
  getSettings: async (): Promise<IntegrationSettings> => {
    const res = await api.get('/settings');
    return res.data;
  },
  updateSettings: async (settings: Partial<IntegrationSettings>): Promise<IntegrationSettings> => {
    const res = await api.post('/settings', settings);
    return res.data;
  },
  verifyIntegration: async (serviceName: string) => {
    const res = await api.post(`/settings/verify/${serviceName}`);
    return res.data;
  },

  // Repositories
  getRepository: async (projectId: string) => {
    const res = await api.get(`/repositories/${projectId}`);
    return res.data;
  },
  connectRepository: async (payload: { project_id: string; provider: string; repo_url: string; branch?: string; access_token?: string }) => {
    const res = await api.post('/repositories/connect', payload);
    return res.data;
  },
  uploadRepositoryZip: async (projectId: string, file: File, branch = 'main') => {
    const formData = new FormData();
    formData.append('project_id', projectId);
    formData.append('branch', branch);
    formData.append('file', file);
    const res = await api.post('/repositories/upload-zip', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },
  disconnectRepository: async (projectId: string) => {
    const res = await api.delete(`/repositories/${projectId}`);
    return res.data;
  },

  // Commercial Billing & Subscriptions
  getPlans: async () => {
    const res = await api.get('/billing/plans');
    return res.data;
  },
  getSubscription: async () => {
    const res = await api.get('/billing/subscription');
    return res.data;
  },
  subscribeOrUpgrade: async (payload: { plan_slug: string; billing_cycle?: string }) => {
    const res = await api.post('/billing/subscribe', payload);
    return res.data;
  },
  cancelSubscription: async () => {
    const res = await api.post('/billing/cancel');
    return res.data;
  },
  getInvoices: async () => {
    const res = await api.get('/billing/invoices');
    return res.data;
  },
  getUsage: async () => {
    const res = await api.get('/billing/usage');
    return res.data;
  },

  // Teams & RBAC
  getTeams: async () => {
    const res = await api.get('/teams');
    return res.data;
  },
  createTeam: async (payload: { name: string; description?: string }) => {
    const res = await api.post('/teams', payload);
    return res.data;
  },
  getTeamDetail: async (teamId: string) => {
    const res = await api.get(`/teams/${teamId}`);
    return res.data;
  },
  addTeamMember: async (teamId: string, payload: { user_id: string; role: string }) => {
    const res = await api.post(`/teams/${teamId}/members`, payload);
    return res.data;
  },
  removeTeamMember: async (teamId: string, userId: string) => {
    const res = await api.delete(`/teams/${teamId}/members/${userId}`);
    return res.data;
  },
  assignProjectToTeam: async (teamId: string, projectId: string, payload: { permission_level: string }) => {
    const res = await api.post(`/teams/${teamId}/projects/${projectId}`, payload);
    return res.data;
  },

  // Code Findings & Diagnostics
  getAssessmentCodeFindings: async (assessmentId: string, params?: { severity?: string; category?: string }) => {
    const res = await api.get(`/code-findings/assessment/${assessmentId}`, { params });
    return res.data;
  },
  getProjectLatestFindings: async (projectId: string) => {
    const res = await api.get(`/code-findings/project/${projectId}`);
    return res.data;
  },
  getCodeFindingDetail: async (findingId: string) => {
    const res = await api.get(`/code-findings/${findingId}`);
    return res.data;
  },

  // Notifications
  getNotifications: async (unreadOnly = false) => {
    const res = await api.get('/notifications', { params: { unread_only: unreadOnly } });
    return res.data;
  },
  markNotificationRead: async (notificationId: string) => {
    const res = await api.post(`/notifications/${notificationId}/read`);
    return res.data;
  },
  markAllNotificationsRead: async () => {
    const res = await api.post('/notifications/read-all');
    return res.data;
  },

  // Extended Auth
  verifyEmail: async (token: string) => {
    const res = await api.post('/auth/verify-email', { token });
    return res.data;
  },
  forgotPassword: async (email: string) => {
    const res = await api.post('/auth/forgot-password', { email });
    return res.data;
  },
  resetPassword: async (payload: { token: string; new_password: string }) => {
    const res = await api.post('/auth/reset-password', payload);
    return res.data;
  },
  updateProfile: async (payload: { full_name?: string }) => {
    const res = await api.put('/auth/me', payload);
    return res.data;
  },
  changePassword: async (payload: { current_password: string; new_password: string }) => {
    const res = await api.post('/auth/change-password', payload);
    return res.data;
  },
  setupMFA: async () => {
    const res = await api.post('/auth/mfa/setup');
    return res.data;
  },
  verifyMFA: async (code: string) => {
    const res = await api.post('/auth/mfa/verify', { code });
    return res.data;
  },
  deleteAccount: async () => {
    const res = await api.delete('/auth/account');
    return res.data;
  },
};

