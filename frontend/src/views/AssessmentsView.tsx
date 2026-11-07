import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  Play,
  FileSpreadsheet,
  FileText,
  AlertTriangle,
  ExternalLink,
  ChevronRight,
  Sparkles,
  Info,
  Clock,
  ArrowRight
} from 'lucide-react';
import { apiClient } from '../services/api';
import { Assessment, Project, TechnologyScore } from '../types';
import { HealthBadge } from '../components/HealthBadge';

interface AssessmentsViewProps {
  initialProjectId?: string;
}

export const AssessmentsView: React.FC<AssessmentsViewProps> = ({ initialProjectId }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>(initialProjectId || '');
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [activeAssessment, setActiveAssessment] = useState<Assessment | null>(null);
  const [selectedTechScore, setSelectedTechScore] = useState<TechnologyScore | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchAssessments = async () => {
    try {
      setLoading(true);
      const [projList, assessList] = await Promise.all([
        apiClient.getProjects(),
        apiClient.getAssessments(selectedProjectId || undefined),
      ]);
      setProjects(projList);
      setAssessments(assessList);
      if (assessList.length > 0) {
        // Load details for first assessment
        const detailed = await apiClient.getAssessment(assessList[0].id);
        setActiveAssessment(detailed);
        if (detailed.scores.length > 0) {
          setSelectedTechScore(detailed.scores[0]);
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAssessments();
  }, [selectedProjectId]);

  const handleRunAssessment = async () => {
    if (!selectedProjectId && projects.length > 0) {
      setSelectedProjectId(projects[0].id);
    }
    const targetProject = selectedProjectId || (projects[0] ? projects[0].id : null);
    if (!targetProject) {
      alert('Please create or select a project first.');
      return;
    }

    try {
      setIsRunning(true);
      const result = await apiClient.runAssessment(targetProject);
      setActiveAssessment(result);
      if (result.scores.length > 0) {
        setSelectedTechScore(result.scores[0]);
      }
      fetchAssessments();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Assessment execution failed');
    } finally {
      setIsRunning(false);
    }
  };

  const handleSelectAssessment = async (id: string) => {
    try {
      const detailed = await apiClient.getAssessment(id);
      setActiveAssessment(detailed);
      if (detailed.scores.length > 0) {
        setSelectedTechScore(detailed.scores[0]);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const categories = [
    { key: 'maintenance_health', label: 'Maintenance Health', weight: '20%' },
    { key: 'security_exposure', label: 'Security Exposure', weight: '20%' },
    { key: 'version_currency', label: 'Version Currency', weight: '15%' },
    { key: 'community_activity', label: 'Community Activity', weight: '10%' },
    { key: 'documentation_quality', label: 'Documentation Quality', weight: '10%' },
    { key: 'ecosystem_compatibility', label: 'Ecosystem Compatibility', weight: '10%' },
    { key: 'sustainability', label: 'Sustainability', weight: '10%' },
    { key: 'upgrade_complexity', label: 'Upgrade Complexity', weight: '5%' },
  ];

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Top Header & Trigger Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 rounded-2xl bg-slate-900 border border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-400" />
            AI Technology Debt Assessments
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Evidence-grounded 8-category evaluation using Firecrawl live intel and historical memory.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          >
            <option value="">Select Project...</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>

          <button
            onClick={handleRunAssessment}
            disabled={isRunning}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs flex items-center gap-2 shadow-md shadow-indigo-600/30 transition-all disabled:opacity-50"
          >
            {isRunning ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>Crawling & Analyzing...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                <span>Run Architecture Review</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Main Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column: Assessment History List */}
        <div className="lg:col-span-4 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 px-1">
            Assessment Runs ({assessments.length})
          </h3>

          {loading ? (
            <div className="p-8 text-center text-xs text-slate-500">Loading runs...</div>
          ) : assessments.length === 0 ? (
            <div className="p-8 text-center rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-400">
              No assessments run yet for this project. Click 'Run Architecture Review' above.
            </div>
          ) : (
            <div className="space-y-2">
              {assessments.map((a) => {
                const isSelected = activeAssessment?.id === a.id;
                return (
                  <button
                    key={a.id}
                    onClick={() => handleSelectAssessment(a.id)}
                    className={`w-full text-left p-4 rounded-xl border transition-all ${
                      isSelected
                        ? 'bg-indigo-600/10 border-indigo-500/40 shadow-sm'
                        : 'bg-slate-900/80 border-slate-800/80 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-xs text-white truncate">{a.project_name || 'Project'}</span>
                      <HealthBadge score={a.overall_health_score} size="sm" />
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-400">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(a.created_at).toLocaleDateString()}
                      </span>
                      <span>{a.risks_count} risk(s)</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: Detailed Assessment Breakdown */}
        <div className="lg:col-span-8 space-y-6">
          {activeAssessment ? (
            <>
              {/* Executive Assessment Header */}
              <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <span className="text-[10px] font-mono uppercase tracking-wider text-indigo-400">
                      Audit Report • {activeAssessment.project_name}
                    </span>
                    <h3 className="text-xl font-bold text-white tracking-tight flex items-center gap-3 mt-0.5">
                      Overall Health Score: {activeAssessment.overall_health_score}/100
                      <HealthBadge score={activeAssessment.overall_health_score} classification={activeAssessment.risk_classification} size="sm" />
                    </h3>
                  </div>

                  {/* Export Buttons */}
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => apiClient.downloadPdfReport(activeAssessment.id, `${projects.find(p => p.id === selectedProjectId)?.name || 'project'}_audit.pdf`)}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                      <FileText className="w-3.5 h-3.5 text-rose-400" />
                      <span>PDF</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => apiClient.downloadCsvReport(activeAssessment.id, `${projects.find(p => p.id === selectedProjectId)?.name || 'project'}_audit.csv`)}
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                      <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
                      <span>CSV</span>
                    </button>
                  </div>
                </div>

                <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/40 p-3 rounded-lg border border-slate-800">
                  {activeAssessment.summary}
                </p>

                {/* Commercial v2.0.0 10-Dimension Architecture Score Cards */}
                {activeAssessment.scoring_version === 'v2.0.0' && (
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-2">
                    <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800 text-center">
                      <span className="text-[10px] uppercase font-mono text-slate-400 block">TDR Ratio</span>
                      <span className="text-base font-extrabold text-cyan-400">{activeAssessment.technical_debt_ratio ?? 0}%</span>
                    </div>
                    <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800 text-center">
                      <span className="text-[10px] uppercase font-mono text-slate-400 block">Remediation</span>
                      <span className="text-base font-extrabold text-amber-400">{activeAssessment.estimated_remediation_hours ?? 0}h</span>
                    </div>
                    <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800 text-center">
                      <span className="text-[10px] uppercase font-mono text-slate-400 block">Maintainability</span>
                      <span className="text-base font-extrabold text-indigo-400">{activeAssessment.code_maintainability_score ?? 'N/A'}</span>
                    </div>
                    <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800 text-center">
                      <span className="text-[10px] uppercase font-mono text-slate-400 block">Architecture</span>
                      <span className="text-base font-extrabold text-emerald-400">{activeAssessment.architecture_score ?? 'N/A'}</span>
                    </div>
                    <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800 text-center">
                      <span className="text-[10px] uppercase font-mono text-slate-400 block">Security</span>
                      <span className="text-base font-extrabold text-rose-400">{activeAssessment.security_score ?? 'N/A'}</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Technology Selection Tabs */}
              {activeAssessment.scores.length > 0 && (
                <div className="space-y-4">
                  <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Assessed Technologies ({activeAssessment.scores.length})
                  </h4>

                  <div className="flex gap-2 overflow-x-auto pb-1">
                    {activeAssessment.scores.map((score) => {
                      const isSelected = selectedTechScore?.technology_id === score.technology_id;
                      return (
                        <button
                          key={score.technology_id}
                          onClick={() => setSelectedTechScore(score)}
                          className={`px-3 py-2 rounded-xl text-xs font-medium transition-all shrink-0 flex items-center gap-2 border ${
                            isSelected
                              ? 'bg-indigo-600 text-white border-indigo-500 shadow-md shadow-indigo-600/30'
                              : 'bg-slate-900 text-slate-300 border-slate-800 hover:border-slate-700'
                          }`}
                        >
                          <span>{score.technology_name}</span>
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${isSelected ? 'bg-indigo-800 text-white' : 'bg-slate-800 text-slate-400'}`}>
                            {score.overall_score}
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  {/* 8 Weighted Categories Grid for Selected Technology */}
                  {selectedTechScore && (
                    <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-6">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                        <div>
                          <h4 className="text-base font-bold text-white flex items-center gap-2">
                            <span>{selectedTechScore.technology_name}</span>
                            <span className="text-xs font-mono text-slate-400">
                              (Installed: {selectedTechScore.installed_version} • Latest: {selectedTechScore.latest_stable_version})
                            </span>
                          </h4>
                          <p className="text-xs text-slate-400 mt-1">
                            Recommended Action: <strong className="text-slate-200">{selectedTechScore.recommended_action}</strong>
                          </p>
                        </div>
                        <HealthBadge score={selectedTechScore.overall_score} classification={selectedTechScore.risk_classification} size="md" />
                      </div>

                      {/* 8 Categories */}
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        {categories.map((cat) => {
                          const val = (selectedTechScore as any)[cat.key] || 0;
                          return (
                            <div key={cat.key} className="p-3 rounded-xl bg-slate-800/50 border border-slate-800 space-y-1">
                              <div className="flex items-center justify-between text-[11px] text-slate-400">
                                <span className="truncate">{cat.label}</span>
                                <span className="text-[10px] text-slate-500 font-mono">{cat.weight}</span>
                              </div>
                              <div className="flex items-baseline gap-1">
                                <span className="text-lg font-bold text-white">{val}</span>
                                <span className="text-[10px] text-slate-400">/100</span>
                              </div>
                              <div className="w-full bg-slate-700/60 h-1 rounded-full overflow-hidden">
                                <div
                                  className={`h-full ${
                                    val >= 85 ? 'bg-emerald-500' : val >= 70 ? 'bg-blue-500' : val >= 50 ? 'bg-amber-500' : 'bg-rose-500'
                                  }`}
                                  style={{ width: `${Math.min(100, val)}%` }}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {/* Grounded Evidence Sources */}
                      {selectedTechScore.evidence && selectedTechScore.evidence.length > 0 && (
                        <div className="space-y-3 pt-2">
                          <h5 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                            <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                            Grounded Verification Evidence ({selectedTechScore.evidence.length} sources)
                          </h5>
                          <div className="space-y-2">
                            {selectedTechScore.evidence.map((ev) => (
                              <div key={ev.id} className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-1 text-xs">
                                <div className="flex items-center justify-between">
                                  <a
                                    href={ev.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="font-semibold text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
                                  >
                                    <span>{ev.title || ev.url}</span>
                                    <ExternalLink className="w-3 h-3" />
                                  </a>
                                  <span className="text-[10px] font-mono text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                                    Reliability: {Math.round(ev.reliability_score * 100)}%
                                  </span>
                                </div>
                                <p className="text-[11px] text-slate-400 line-clamp-2 italic">"{ev.snippet}"</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="p-12 text-center rounded-2xl bg-slate-900 border border-slate-800 text-xs text-slate-400">
              Select or run an assessment to explore category telemetry.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

