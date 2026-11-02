import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  Flame,
  CheckCircle2,
  Clock,
  User,
  Filter,
  MessageSquare,
  ShieldAlert,
  ArrowRight
} from 'lucide-react';
import { apiClient } from '../services/api';
import { RiskFinding } from '../types';

export const RiskCenterView: React.FC = () => {
  const [risks, setRisks] = useState<RiskFinding[]>([]);
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [editingRisk, setEditingRisk] = useState<RiskFinding | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [newStatus, setNewStatus] = useState<RiskFinding['status']>('Resolved');

  const fetchRisks = async () => {
    try {
      setLoading(true);
      const params: any = {};
      if (selectedSeverity !== 'all') params.severity = selectedSeverity;
      if (selectedStatus !== 'all') params.status = selectedStatus;
      const data = await apiClient.getRisks(params);
      setRisks(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRisks();
  }, [selectedSeverity, selectedStatus]);

  const handleStatusChange = async (risk: RiskFinding, status: RiskFinding['status']) => {
    try {
      await apiClient.updateRisk(risk.id, { status });
      fetchRisks();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to update risk');
    }
  };

  const handleResolveSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingRisk) return;
    try {
      await apiClient.updateRisk(editingRisk.id, {
        status: newStatus,
        resolution_notes: resolutionNotes,
      });
      setEditingRisk(null);
      setResolutionNotes('');
      fetchRisks();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to submit resolution note');
    }
  };

  const severityBadgeClass = (severity: string) => {
    switch (severity) {
      case 'Critical':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/30';
      case 'High':
        return 'bg-orange-500/10 text-orange-400 border-orange-500/30';
      case 'Medium':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  const statusBadgeClass = (status: string) => {
    switch (status) {
      case 'Resolved':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
      case 'Accepted Risk':
        return 'bg-purple-500/10 text-purple-400 border-purple-500/30';
      case 'In Progress':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/30';
      case 'Investigating':
        return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-rose-400" />
            Risk Management Center
          </h2>
          <p className="text-xs text-slate-400">
            Triage, assign, and resolve security vulnerabilities, deprecation blockers, and version drifts.
          </p>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-slate-400">Severity:</span>
            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              className="px-2.5 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="all">All Severities</option>
              <option value="Critical">Critical</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-xs text-slate-400">Status:</span>
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="px-2.5 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="all">All Statuses</option>
              <option value="Open">Open</option>
              <option value="Investigating">Investigating</option>
              <option value="Planned">Planned</option>
              <option value="In Progress">In Progress</option>
              <option value="Resolved">Resolved</option>
              <option value="Accepted Risk">Accepted Risk</option>
            </select>
          </div>
        </div>
      </div>

      {/* Risks Table / Cards */}
      {loading ? (
        <div className="p-12 text-center text-xs text-slate-500">Loading risk items...</div>
      ) : risks.length === 0 ? (
        <div className="p-12 text-center rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
          <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto" />
          <h3 className="text-sm font-semibold text-slate-200">No matching risks found</h3>
          <p className="text-xs text-slate-500">All current dependencies meet architectural health criteria.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {risks.map((risk) => (
            <div
              key={risk.id}
              className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4 hover:border-slate-700 transition-all shadow-md shadow-black/20"
            >
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border uppercase tracking-wider ${severityBadgeClass(risk.severity)}`}>
                      {risk.severity}
                    </span>
                    <h3 className="text-sm font-bold text-white tracking-tight">{risk.title}</h3>
                    <span className="text-[11px] font-mono text-indigo-400 bg-indigo-950/60 px-2 py-0.5 rounded border border-indigo-800/60">
                      {risk.technology_name}
                    </span>
                    <span className="text-[11px] text-slate-500">• {risk.project_name}</span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">{risk.description}</p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <select
                    value={risk.status}
                    onChange={(e) => handleStatusChange(risk, e.target.value as any)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${statusBadgeClass(risk.status)} focus:outline-none`}
                  >
                    <option value="Open">Open</option>
                    <option value="Investigating">Investigating</option>
                    <option value="Planned">Planned</option>
                    <option value="In Progress">In Progress</option>
                    <option value="Resolved">Resolved</option>
                    <option value="Accepted Risk">Accepted Risk</option>
                  </select>

                  <button
                    onClick={() => {
                      setEditingRisk(risk);
                      setNewStatus(risk.status);
                      setResolutionNotes(risk.resolution_notes || '');
                    }}
                    className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-xs font-medium flex items-center gap-1"
                    title="Add resolution notes"
                  >
                    <MessageSquare className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Notes</span>
                  </button>
                </div>
              </div>

              {/* Impact Breakdown */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs bg-slate-950/40 p-3 rounded-xl border border-slate-800/80">
                <div>
                  <span className="font-semibold text-rose-300">Business Impact:</span>{' '}
                  <span className="text-slate-400">{risk.business_impact || 'Potential stability risk.'}</span>
                </div>
                <div>
                  <span className="font-semibold text-amber-300">Technical Impact:</span>{' '}
                  <span className="text-slate-400">{risk.technical_impact || 'Refactoring required.'}</span>
                </div>
              </div>

              {/* Resolution Notes display if present */}
              {risk.resolution_notes && (
                <div className="text-xs bg-indigo-950/30 border border-indigo-900/40 p-2.5 rounded-lg text-indigo-200">
                  <span className="font-semibold text-indigo-400">Resolution Log:</span> {risk.resolution_notes}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Resolution Modal */}
      {editingRisk && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <h3 className="text-base font-bold text-white">Update Risk Status & Notes</h3>
            <p className="text-xs text-slate-400">{editingRisk.title}</p>

            <form onSubmit={handleResolveSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Status</label>
                <select
                  value={newStatus}
                  onChange={(e) => setNewStatus(e.target.value as any)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-indigo-500"
                >
                  <option value="Open">Open</option>
                  <option value="Investigating">Investigating</option>
                  <option value="Planned">Planned</option>
                  <option value="In Progress">In Progress</option>
                  <option value="Resolved">Resolved</option>
                  <option value="Accepted Risk">Accepted Risk</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Resolution & Audit Notes</label>
                <textarea
                  rows={4}
                  required
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  placeholder="Document upgrade patch PR, mitigation strategy, or architectural exemption..."
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setEditingRisk(null)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
                >
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

