import React, { useState, useEffect } from 'react';
import {
  Cpu,
  Search,
  Filter,
  ExternalLink,
  AlertTriangle,
  CheckCircle,
  Tag,
  GitBranch,
  Layers,
  Sparkles
} from 'lucide-react';
import { apiClient } from '../services/api';
import { Technology, Project } from '../types';
import { HealthBadge } from '../components/HealthBadge';

export const TechnologiesView: React.FC = () => {
  const [technologies, setTechnologies] = useState<Technology[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEcosystem, setSelectedEcosystem] = useState('all');
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [projList, techList] = await Promise.all([
        apiClient.getProjects(),
        apiClient.getTechnologies(selectedProjectId || undefined),
      ]);
      setProjects(projList);
      setTechnologies(techList);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [selectedProjectId]);

  const filteredTechnologies = technologies.filter((t) => {
    const matchesSearch =
      t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesEcosystem =
      selectedEcosystem === 'all' || t.ecosystem.toLowerCase() === selectedEcosystem.toLowerCase();
    return matchesSearch && matchesEcosystem;
  });

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Cpu className="w-5 h-5 text-indigo-400" />
            Technology & Dependency Inventory
          </h2>
          <p className="text-xs text-slate-400">
            Catalog of all evaluated frameworks, runtimes, and dependencies across your projects.
          </p>
        </div>

        {/* Project Selector Filter */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Filter by Project:</span>
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="">All Projects (Global)</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Search technology by name or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-500" />
          <select
            value={selectedEcosystem}
            onChange={(e) => setSelectedEcosystem(e.target.value)}
            className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Ecosystems</option>
            <option value="npm">npm / Node.js</option>
            <option value="pypi">PyPI / Python</option>
            <option value="maven">Maven</option>
            <option value="cargo">Cargo / Rust</option>
            <option value="go">Go</option>
          </select>
        </div>
      </div>

      {/* Inventory Table */}
      {loading ? (
        <div className="p-12 text-center text-xs text-slate-400">Loading technology inventory...</div>
      ) : filteredTechnologies.length === 0 ? (
        <div className="p-12 text-center rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
          <Cpu className="w-8 h-8 text-slate-600 mx-auto" />
          <p className="text-xs text-slate-400">No technologies found matching criteria.</p>
        </div>
      ) : (
        <div className="rounded-2xl bg-slate-900/80 border border-slate-800 overflow-hidden shadow-xl">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-800/80 text-slate-400 border-b border-slate-800 font-medium">
              <tr>
                <th className="py-3.5 px-4">Technology</th>
                <th className="py-3.5 px-4">Ecosystem</th>
                <th className="py-3.5 px-4">Installed</th>
                <th className="py-3.5 px-4">Latest Stable</th>
                <th className="py-3.5 px-4">Status & Health</th>
                <th className="py-3.5 px-4">Maintenance Mode</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {filteredTechnologies.map((t) => (
                <tr key={t.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="py-3.5 px-4">
                    <div>
                      <div className="font-semibold text-white flex items-center gap-2">
                        <span>{t.name}</span>
                        {t.website_url && (
                          <a
                            href={t.website_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-slate-500 hover:text-indigo-400"
                          >
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-500 truncate max-w-sm">{t.description || 'No description'}</p>
                    </div>
                  </td>
                  <td className="py-3.5 px-4 font-mono">
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 text-[10px]">
                      {t.ecosystem}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 font-mono text-slate-200">
                    {t.installed_version || 'latest'}
                  </td>
                  <td className="py-3.5 px-4 font-mono text-emerald-400">
                    {t.latest_stable_version}
                  </td>
                  <td className="py-3.5 px-4">
                    <HealthBadge score={t.health_score} classification={t.risk_classification} size="sm" />
                  </td>
                  <td className="py-3.5 px-4">
                    {t.is_deprecated ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20">
                        <AlertTriangle className="w-3 h-3" /> Deprecated
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] text-slate-400">
                        <CheckCircle className="w-3 h-3 text-emerald-500" /> Active
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

