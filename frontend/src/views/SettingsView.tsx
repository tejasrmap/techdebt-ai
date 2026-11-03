import React, { useState, useEffect } from 'react';
import {
  Settings,
  Calendar,
  Clock,
  Play,
  Trash2,
  Plus,
  Building,
  Shield,
  CheckCircle2,
  AlertCircle,
  UserPlus,
  Mail,
  Copy,
  Ticket
} from 'lucide-react';
import { apiClient } from '../services/api';
import { ScheduledReview, Project } from '../types';
import { useAuth } from '../context/AuthContext';

export const SettingsView: React.FC = () => {
  const { user } = useAuth();
  const [schedules, setSchedules] = useState<ScheduledReview[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [invitations, setInvitations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // New schedule form
  const [newProjectId, setNewProjectId] = useState('');
  const [newFrequency, setNewFrequency] = useState('Weekly');
  const [newCron, setNewCron] = useState('0 0 * * 1');
  const [triggering, setTriggering] = useState<string | null>(null);

  // Invitation form
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('Developer');
  const [copiedToken, setCopiedToken] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [schedList, projList] = await Promise.all([
        apiClient.getSchedules(),
        apiClient.getProjects(),
      ]);
      setSchedules(schedList);
      setProjects(projList);
      if (projList.length > 0 && !newProjectId) {
        setNewProjectId(projList[0].id);
      }

      if (user?.role === 'Administrator' || user?.role === 'Engineering Manager') {
        const inviteList = await apiClient.listInvitations();
        setInvitations(inviteList);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreateSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectId) return;
    try {
      await apiClient.createSchedule({
        project_id: newProjectId,
        frequency: newFrequency,
        cron_expression: newCron,
      });
      fetchData();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to create schedule');
    }
  };

  const handleTriggerNow = async (id: string) => {
    try {
      setTriggering(id);
      const res = await apiClient.triggerScheduleNow(id);
      alert(res.message);
      fetchData();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Execution failed');
    } finally {
      setTriggering(null);
    }
  };

  const handleDeleteSchedule = async (id: string) => {
    if (confirm('Delete this automated review schedule?')) {
      await apiClient.deleteSchedule(id);
      fetchData();
    }
  };

  const handleCreateInvitation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail) return;
    try {
      await apiClient.createInvitation({
        email: inviteEmail.trim(),
        role: inviteRole,
      });
      setInviteEmail('');
      fetchData();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to send invitation');
    }
  };

  const handleRevokeInvitation = async (id: string) => {
    if (confirm('Revoke this invitation?')) {
      await apiClient.revokeInvitation(id);
      fetchData();
    }
  };

  const handleCopyToken = (token: string) => {
    navigator.clipboard.writeText(token);
    setCopiedToken(token);
    setTimeout(() => setCopiedToken(null), 2500);
  };

  const isPrivileged = user?.role === 'Administrator' || user?.role === 'Engineering Manager';

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 rounded-2xl bg-slate-900 border border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Settings className="w-5 h-5 text-indigo-400" />
            Settings & Review Automation
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Configure automated background review cadence and manage organization membership.
          </p>
        </div>
      </div>

      {/* Organization Details */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
        <h3 className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
          <Building className="w-4 h-4 text-indigo-400" />
          Organization Profile
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800">
            <span className="text-slate-400">Organization Name</span>
            <p className="font-semibold text-white mt-1">{user?.organization_name || 'Acme Engineering'}</p>
          </div>
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800">
            <span className="text-slate-400">Active User Role</span>
            <p className="font-semibold text-indigo-400 mt-1">{user?.role}</p>
          </div>
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800">
            <span className="text-slate-400">Access Mode</span>
            <p className="font-semibold text-emerald-400 mt-1">Strict Tenant Isolation</p>
          </div>
        </div>
      </div>

      {/* Team Invitations Section (Admin / Manager only) */}
      {isPrivileged && (
        <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
                <UserPlus className="w-4 h-4 text-cyan-400" />
                Team Membership & Invitations
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Invite developers, engineering managers, and viewers into your organization workspace.
              </p>
            </div>
          </div>

          {/* Pending Invitations Table */}
          {invitations.length > 0 && (
            <div className="rounded-xl border border-slate-800 overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-800/80 text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4">Invited Email</th>
                    <th className="py-3 px-4">Role Assigned</th>
                    <th className="py-3 px-4">Invitation Token</th>
                    <th className="py-3 px-4">Expires</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  {invitations.map((inv) => (
                    <tr key={inv.id} className="hover:bg-slate-800/30">
                      <td className="py-3 px-4 font-semibold text-white">{inv.email}</td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded bg-cyan-950/60 text-cyan-300 border border-cyan-800 text-[10px] font-mono">
                          {inv.role}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-400">
                        <button
                          onClick={() => handleCopyToken(inv.token)}
                          className="flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 font-mono bg-slate-800 px-2 py-1 rounded"
                          title="Copy invitation token"
                        >
                          <Copy className="w-3 h-3" />
                          <span>{copiedToken === inv.token ? 'Copied!' : `${inv.token.substring(0, 12)}...`}</span>
                        </button>
                      </td>
                      <td className="py-3 px-4 text-slate-400 font-mono">
                        {new Date(inv.expires_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => handleRevokeInvitation(inv.id)}
                          className="p-1 rounded bg-slate-800/60 hover:bg-rose-500/10 text-slate-400 hover:text-rose-400"
                          title="Revoke invitation"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Issue New Invitation Form */}
          <div className="pt-2 border-t border-slate-800 space-y-3">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Issue New Team Invitation</h4>
            <form onSubmit={handleCreateInvitation} className="flex flex-col sm:flex-row gap-3 text-xs">
              <input
                type="email"
                required
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="colleague@yourcompany.com"
                className="flex-1 px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />

              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
                className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-cyan-500"
              >
                <option value="Developer">Developer</option>
                <option value="Engineering Manager">Engineering Manager</option>
                <option value="Viewer">Viewer</option>
                <option value="Administrator">Administrator</option>
              </select>

              <button
                type="submit"
                className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-xs flex items-center justify-center gap-1.5 shadow-md shadow-cyan-600/30 transition-all shrink-0"
              >
                <Plus className="w-3.5 h-3.5" /> Create Invitation
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Automated Review Schedules */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-6">
        <div>
          <h3 className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
            <Calendar className="w-4 h-4 text-cyan-400" />
            Automated Architecture Review Scheduler
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Configured background jobs will periodically crawl technology documentation, compute health deltas, and store historical assessments.
          </p>
        </div>

        {/* Existing Schedules Table */}
        {loading ? (
          <div className="p-8 text-center text-xs text-slate-500">Loading schedules...</div>
        ) : schedules.length === 0 ? (
          <div className="p-6 rounded-xl bg-slate-950 text-center text-xs text-slate-500">
            No scheduled review jobs configured yet.
          </div>
        ) : (
          <div className="rounded-xl border border-slate-800 overflow-hidden">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-800/80 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">Project</th>
                  <th className="py-3 px-4">Cadence</th>
                  <th className="py-3 px-4">Cron Pattern</th>
                  <th className="py-3 px-4">Next Run</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {schedules.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-800/30">
                    <td className="py-3 px-4 font-semibold text-white">{s.project_name || 'Project'}</td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded bg-indigo-950/60 text-indigo-300 border border-indigo-800 font-mono text-[10px]">
                        {s.frequency}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-400">{s.cron_expression}</td>
                    <td className="py-3 px-4 font-mono text-slate-400">
                      {s.next_run_at ? new Date(s.next_run_at).toLocaleString() : 'Calculating...'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {isPrivileged && (
                          <>
                            <button
                              onClick={() => handleTriggerNow(s.id)}
                              disabled={triggering === s.id}
                              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-indigo-300 border border-slate-700 text-xs font-medium flex items-center gap-1 disabled:opacity-50"
                            >
                              <Play className="w-3 h-3 fill-current" />
                              <span>{triggering === s.id ? 'Running...' : 'Run Now'}</span>
                            </button>
                            <button
                              onClick={() => handleDeleteSchedule(s.id)}
                              className="p-1 rounded bg-slate-800/60 hover:bg-rose-500/10 text-slate-400 hover:text-rose-400"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Add New Schedule Form (Privileged only) */}
        {isPrivileged && (
          <div className="pt-4 border-t border-slate-800 space-y-3">
            <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Add New Review Schedule</h4>
            <form onSubmit={handleCreateSchedule} className="flex flex-col sm:flex-row gap-3 text-xs">
              <select
                value={newProjectId}
                onChange={(e) => setNewProjectId(e.target.value)}
                className="flex-1 px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-indigo-500"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>

              <select
                value={newFrequency}
                onChange={(e) => {
                  setNewFrequency(e.target.value);
                  if (e.target.value === 'Weekly') setNewCron('0 0 * * 1');
                  else if (e.target.value === 'Monthly') setNewCron('0 0 1 * *');
                  else if (e.target.value === 'Daily') setNewCron('0 0 * * *');
                }}
                className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-indigo-500"
              >
                <option value="Weekly">Weekly (Every Monday)</option>
                <option value="Monthly">Monthly (1st of Month)</option>
                <option value="Daily">Daily</option>
              </select>

              <button
                type="submit"
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center justify-center gap-1.5 shadow-md shadow-indigo-600/30 transition-all shrink-0"
              >
                <Plus className="w-3.5 h-3.5" /> Schedule Review
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};
