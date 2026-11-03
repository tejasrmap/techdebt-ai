import React, { useState, useEffect } from 'react';
import {
  History,
  TrendingUp,
  TrendingDown,
  Minus,
  Sparkles,
  ShieldAlert,
  CheckCircle2,
  Calendar,
  Layers,
  ArrowRight
} from 'lucide-react';
import { apiClient } from '../services/api';
import { HistoricalRecord, Project } from '../types';
import { HealthBadge } from '../components/HealthBadge';

export const HistoricalIntelligenceView: React.FC = () => {
  const [history, setHistory] = useState<HistoricalRecord[]>([]);
  const [memoryProvider, setMemoryProvider] = useState<string>('postgresql_fallback');
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [loading, setLoading] = useState(true);

  const fetchHistory = async () => {
    try {
      setLoading(true);
      const [projList, histData] = await Promise.all([
        apiClient.getProjects(),
        apiClient.getHistoricalMemory(selectedProjectId || undefined),
      ]);
      setProjects(projList);
      setHistory(histData.records);
      setMemoryProvider(histData.memory_provider);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [selectedProjectId]);

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 rounded-2xl bg-slate-900 border border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <History className="w-5 h-5 text-indigo-400" />
            Historical Architecture Intelligence
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Continuous longitudinal memory tracking score drift, risk progression, and resolution history.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Active Memory Provider Badge */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-800 border border-slate-700 text-xs text-slate-300">
            <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
            <span>
              Memory Layer:{' '}
              <strong className="text-white">
                PostgreSQL Authoritative Memory
              </strong>
            </span>
          </div>

          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="">All Projects</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Historical Timeline */}
      {loading ? (
        <div className="p-12 text-center text-xs text-slate-500">Loading historical intelligence...</div>
      ) : history.length === 0 ? (
        <div className="p-12 text-center rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
          <History className="w-8 h-8 text-slate-600 mx-auto" />
          <h3 className="text-sm font-semibold text-slate-300">No Assessment History Recorded</h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Run technology assessments to begin accumulating longitudinal architecture context in PostgreSQL historical storage.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {history.map((record, index) => {
            const isImprovement = record.score_delta > 0;
            const isDecline = record.score_delta < 0;

            return (
              <div
                key={record.id}
                className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4 relative overflow-hidden shadow-lg shadow-black/20"
              >
                {/* Left Accent Bar */}
                <div
                  className={`absolute left-0 top-0 bottom-0 w-1 ${
                    isImprovement ? 'bg-emerald-500' : isDecline ? 'bg-rose-500' : 'bg-slate-700'
                  }`}
                />

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-bold text-white tracking-tight">{record.project_name}</h3>
                      <span className="text-xs text-slate-500 font-mono">
                        {new Date(record.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed">{record.summary_of_changes}</p>
                  </div>

                  <div className="flex items-center gap-4 shrink-0">
                    {/* Score and Delta */}
                    <div className="text-right">
                      <div className="flex items-center gap-2">
                        <span className="text-2xl font-extrabold text-white">{record.health_score}</span>
                        <span className="text-xs text-slate-400">/100</span>

                        {record.score_delta !== 0 && (
                          <span
                            className={`flex items-center text-xs font-bold font-mono px-2 py-0.5 rounded-full ${
                              isImprovement
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                            }`}
                          >
                            {isImprovement ? <TrendingUp className="w-3.5 h-3.5 mr-0.5" /> : <TrendingDown className="w-3.5 h-3.5 mr-0.5" />}
                            {isImprovement ? `+${record.score_delta}` : record.score_delta}
                          </span>
                        )}
                      </div>
                      <HealthBadge score={record.health_score} classification={record.risk_classification} size="sm" />
                    </div>
                  </div>
                </div>

                {/* Risk progression telemetry */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-xs">
                  <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-400">New Risks:</span>
                    <span className={`font-mono font-bold ${record.new_risks_count > 0 ? 'text-rose-400' : 'text-slate-300'}`}>
                      {record.new_risks_count}
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-400">Resolved Risks:</span>
                    <span className={`font-mono font-bold ${record.resolved_risks_count > 0 ? 'text-emerald-400' : 'text-slate-300'}`}>
                      {record.resolved_risks_count}
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 flex items-center justify-between sm:col-span-2">
                    <span className="text-slate-400">Memory Sync:</span>
                    <span className="text-[11px] font-mono text-cyan-400 truncate">
                      Persisted in PostgreSQL Authoritative Store
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

