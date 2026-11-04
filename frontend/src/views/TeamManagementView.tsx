import React, { useState, useEffect } from 'react';
import { apiClient } from '../services/api';
import { Team } from '../types';

export const TeamManagementView: React.FC = () => {
  const [teams, setTeams] = useState<Team[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState<string>('');
  const [teamDetail, setTeamDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Form states
  const [newTeamName, setNewTeamName] = useState('');
  const [newTeamDesc, setNewTeamDesc] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('Developer');
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    loadTeams();
  }, []);

  const loadTeams = async () => {
    setLoading(true);
    try {
      const list = await apiClient.getTeams();
      setTeams(list);
      if (list.length > 0) {
        setSelectedTeamId(list[0].id);
        await loadTeamDetail(list[0].id);
      }
    } catch (err) {
      console.error('Failed to load teams:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadTeamDetail = async (teamId: string) => {
    try {
      const detail = await apiClient.getTeamDetail(teamId);
      setTeamDetail(detail);
    } catch (err) {
      console.error('Failed to load team detail:', err);
    }
  };

  const handleSelectTeam = async (teamId: string) => {
    setSelectedTeamId(teamId);
    await loadTeamDetail(teamId);
  };

  const handleCreateTeam = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiClient.createTeam({ name: newTeamName, description: newTeamDesc });
      setMessage({ text: `Team '${newTeamName}' created!`, type: 'success' });
      setShowCreateModal(false);
      setNewTeamName('');
      setNewTeamDesc('');
      await loadTeams();
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Failed to create team', type: 'error' });
    }
  };

  const handleSendInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await apiClient.createInvitation({ email: inviteEmail, role: inviteRole });
      setMessage({ text: `Invitation dispatched to ${inviteEmail}`, type: 'success' });
      setInviteEmail('');
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Failed to send invitation', type: 'error' });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto py-6 px-4 sm:px-6 lg:px-8 space-y-8">
      {/* Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Teams & Organization Governance</h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage engineering squads, invitations, and project access permissions.
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition"
        >
          + Create Squad
        </button>
      </div>

      {message && (
        <div
          className={`p-4 rounded-lg text-sm font-medium ${
            message.type === 'success' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-rose-50 text-rose-800 border border-rose-200'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Grid: Squads on left, Details on right */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Squads List */}
        <div className="space-y-4">
          <h2 className="text-sm font-bold text-slate-700 uppercase tracking-wider">Engineering Teams</h2>
          {teams.length === 0 ? (
            <div className="p-6 bg-white rounded-xl border border-slate-200 text-center text-sm text-slate-500">
              No teams created yet.
            </div>
          ) : (
            teams.map((t) => (
              <div
                key={t.id}
                onClick={() => handleSelectTeam(t.id)}
                className={`p-4 rounded-xl border cursor-pointer transition ${
                  selectedTeamId === t.id
                    ? 'border-indigo-600 bg-indigo-50/40 shadow-sm'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <h3 className="font-bold text-slate-900 text-base">{t.name}</h3>
                {t.description && <p className="text-xs text-slate-500 mt-1 line-clamp-1">{t.description}</p>}
                <div className="mt-3 flex items-center gap-4 text-xs font-medium text-slate-400">
                  <span>{t.member_count} member(s)</span>
                  <span>{t.project_count} project(s)</span>
                </div>
              </div>
            ))
          )}

          {/* Quick Invite Box */}
          <div className="p-4 bg-white rounded-xl border border-slate-200 shadow-sm mt-6">
            <h3 className="text-sm font-bold text-slate-900 mb-2">Invite Collaborator</h3>
            <form onSubmit={handleSendInvite} className="space-y-3 text-xs">
              <div>
                <input
                  type="email"
                  required
                  placeholder="colleague@company.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg"
                />
              </div>
              <div>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white"
                >
                  <option value="Administrator">Administrator</option>
                  <option value="Engineering Manager">Engineering Manager</option>
                  <option value="Developer">Developer</option>
                  <option value="Viewer">Viewer</option>
                </select>
              </div>
              <button
                type="submit"
                className="w-full py-2 bg-slate-900 text-white rounded-lg font-semibold hover:bg-slate-800 transition"
              >
                Send Invite
              </button>
            </form>
          </div>
        </div>

        {/* Team Details Panel */}
        <div className="lg:col-span-2 space-y-6">
          {teamDetail ? (
            <>
              {/* Member Roster */}
              <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
                <h2 className="text-base font-bold text-slate-900 mb-4">{teamDetail.name} — Members</h2>
                <div className="divide-y divide-slate-100">
                  {teamDetail.members?.map((m: any) => (
                    <div key={m.user_id} className="py-3 flex items-center justify-between">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{m.full_name}</p>
                        <p className="text-xs text-slate-400 font-mono">{m.email}</p>
                      </div>
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 capitalize">
                        {m.team_role}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Assigned Projects */}
              <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
                <h2 className="text-base font-bold text-slate-900 mb-4">Assigned Repositories & Permissions</h2>
                {teamDetail.assigned_projects?.length === 0 ? (
                  <p className="text-xs text-slate-400">No specific project boundaries assigned. Squad has default org visibility.</p>
                ) : (
                  <div className="divide-y divide-slate-100">
                    {teamDetail.assigned_projects?.map((p: any) => (
                      <div key={p.project_id} className="py-3 flex items-center justify-between">
                        <span className="text-sm font-semibold text-slate-800">{p.name}</span>
                        <span className="px-2 py-0.5 rounded text-xs font-mono font-medium bg-indigo-50 text-indigo-700 uppercase">
                          {p.permission_level}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="p-12 text-center text-slate-400">Select a team to review membership and permissions.</div>
          )}
        </div>
      </div>

      {/* Modal: Create Team */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-slate-900/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-xl">
            <h3 className="text-lg font-bold text-slate-900 mb-3">Create Engineering Team</h3>
            <form onSubmit={handleCreateTeam} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Team Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Core Backend, Payments, SRE"
                  value={newTeamName}
                  onChange={(e) => setNewTeamName(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                />
              </div>
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Description</label>
                <textarea
                  placeholder="Team mission and repository scope..."
                  value={newTeamDesc}
                  onChange={(e) => setNewTeamDesc(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                  rows={3}
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700"
                >
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

