import React, { useEffect, useState } from 'react';
import {
  FolderGit2,
  Cpu,
  AlertTriangle,
  Flame,
  Activity,
  Calendar,
  ArrowUpRight,
  TrendingUp,
  Clock,
  ArrowRight
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  BarChart,
  Bar,
  Cell
} from 'recharts';
import { apiClient } from '../services/api';
import { DashboardOverview } from '../types';
import { HealthBadge } from '../components/HealthBadge';
import { NavItem } from '../components/Sidebar';

interface DashboardViewProps {
  onNavigate: (tab: NavItem) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({ onNavigate }) => {
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboard = async () => {
    try {
      setLoading(true);
      const overview = await apiClient.getDashboardOverview();
      setData(overview);
    } catch (err: any) {
      setError(err.message || 'Failed to load dashboard overview');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-slate-400">Loading technology debt telemetry...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-8">
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
          {error || 'Unable to load dashboard.'}
        </div>
      </div>
    );
  }

  const healthDistData = [
    { name: 'Healthy', count: data.health_distribution['Healthy'] || 0, color: '#10b981' },
    { name: 'Good', count: data.health_distribution['Good'] || 0, color: '#3b82f6' },
    { name: 'Needs Attention', count: data.health_distribution['Needs Attention'] || 0, color: '#f59e0b' },
    { name: 'High Risk', count: data.health_distribution['High Risk'] || 0, color: '#f97316' },
    { name: 'Critical', count: data.health_distribution['Critical'] || 0, color: '#ef4444' },
  ];

  const riskSeverityData = [
    { name: 'Critical', count: data.risk_distribution['Critical'] || 0, color: '#ef4444' },
    { name: 'High', count: data.risk_distribution['High'] || 0, color: '#f97316' },
    { name: 'Medium', count: data.risk_distribution['Medium'] || 0, color: '#f59e0b' },
    { name: 'Low', count: data.risk_distribution['Low'] || 0, color: '#10b981' },
  ];

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Top summary banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border border-slate-800 shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-white tracking-tight">Executive Debt Overview</h2>
            <HealthBadge score={data.overall_health_score} size="md" />
          </div>
          <p className="text-xs text-slate-400">
            Composite health score across {data.total_projects} projects and {data.total_technologies} distinct packages.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => onNavigate('assessments')}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs flex items-center gap-1.5 shadow-md shadow-indigo-600/30 transition-all"
          >
            <Activity className="w-4 h-4" /> Run New Assessment
          </button>
          <button
            onClick={() => onNavigate('risks')}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs border border-slate-700 transition-colors"
          >
            Review Risks ({data.critical_technology_risks})
          </button>
        </div>
      </div>

      {/* 7 Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Overall Health Score */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800/80 space-y-3">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Overall Health Score</span>
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-white">{data.overall_health_score}</span>
            <span className="text-xs text-slate-400">/ 100</span>
          </div>
          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
            <span>Weighted 8-category architecture index</span>
          </div>
        </div>

        {/* Card 2: Critical Risks */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800/80 space-y-3">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Critical Technology Risks</span>
            <Flame className="w-4 h-4 text-rose-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-rose-400">{data.critical_technology_risks}</span>
            <span className="text-xs text-slate-400">active items</span>
          </div>
          <div className="text-[11px] text-slate-400">Requires immediate architectural mitigation</div>
        </div>

        {/* Card 3: Outdated Dependencies */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800/80 space-y-3">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Outdated Dependencies</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-amber-400">{data.outdated_dependencies}</span>
            <span className="text-xs text-slate-400">packages</span>
          </div>
          <div className="text-[11px] text-slate-400">Lagging behind stable major/minor releases</div>
        </div>

        {/* Card 4: Declining Maintenance */}
        <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800/80 space-y-3">
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-medium">Declining Maintenance</span>
            <Clock className="w-4 h-4 text-orange-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-orange-400">{data.declining_maintenance_count}</span>
            <span className="text-xs text-slate-400">technologies</span>
          </div>
          <div className="text-[11px] text-slate-400">Deprecated, EOL, or maintenance-only status</div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Historical Debt Trend Line Chart */}
        <div className="lg:col-span-8 p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-100">Historical Health Score Trend</h3>
              <p className="text-xs text-slate-400">Continuous longitudinal architecture assessments</p>
            </div>
            <span className="text-[11px] font-mono text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-800">
              PostgreSQL Memory Active
            </span>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.historical_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis domain={[0, 100]} stroke="#64748b" fontSize={11} tickLine={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: '#334155',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="health_score"
                  stroke="#6366f1"
                  strokeWidth={2.5}
                  dot={{ fill: '#6366f1', r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Technology Health Distribution */}
        <div className="lg:col-span-4 p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-slate-100">Health Distribution</h3>
            <p className="text-xs text-slate-400">Classification of assessed dependencies</p>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={healthDistData} layout="vertical" margin={{ left: 10, right: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                <XAxis type="number" stroke="#64748b" fontSize={10} />
                <YAxis dataKey="name" type="category" stroke="#64748b" fontSize={10} width={80} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: '#334155',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {healthDistData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Projects Health Breakdown Table */}
      <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-100">Project Debt Portfolio</h3>
            <p className="text-xs text-slate-400">Technical debt posture grouped by software service</p>
          </div>
          <button
            onClick={() => onNavigate('projects')}
            className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-medium"
          >
            Manage Projects <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-800/60 text-slate-400 border-b border-slate-800 font-medium">
              <tr>
                <th className="py-3 px-4">Project Name</th>
                <th className="py-3 px-4">Dependencies Assessed</th>
                <th className="py-3 px-4">Health Score</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {data.project_health_breakdown.map((p) => (
                <tr key={p.project_id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="py-3.5 px-4 font-medium text-white flex items-center gap-2">
                    <FolderGit2 className="w-4 h-4 text-indigo-400" />
                    <span>{p.project_name}</span>
                  </td>
                  <td className="py-3.5 px-4 font-mono">{p.technology_count} packages</td>
                  <td className="py-3.5 px-4">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white">{p.health_score}</span>
                      <div className="w-20 bg-slate-800 h-1.5 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            p.health_score >= 85
                              ? 'bg-emerald-500'
                              : p.health_score >= 70
                              ? 'bg-blue-500'
                              : p.health_score >= 50
                              ? 'bg-amber-500'
                              : 'bg-rose-500'
                          }`}
                          style={{ width: `${Math.min(100, p.health_score)}%` }}
                        />
                      </div>
                    </div>
                  </td>
                  <td className="py-3.5 px-4">
                    <HealthBadge score={p.health_score} classification={p.risk_classification} size="sm" />
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    <button
                      onClick={() => onNavigate('assessments')}
                      className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-indigo-300 border border-slate-700 text-xs font-medium"
                    >
                      View Report
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

