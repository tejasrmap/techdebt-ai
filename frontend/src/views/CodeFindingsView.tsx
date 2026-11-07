import React, { useState, useEffect } from 'react';
import { apiClient } from '../services/api';
import { Project, Assessment, CodeFinding } from '../types';

export const CodeFindingsView: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<string>('');
  const [findings, setFindings] = useState<CodeFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [findingsLoading, setFindingsLoading] = useState(false);

  // Filters
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    setLoading(true);
    try {
      const projList = await apiClient.getProjects();
      setProjects(projList);
      if (projList.length > 0) {
        setSelectedProjectId(projList[0].id);
        await loadAssessmentsForProject(projList[0].id);
      }
    } catch (err: any) {
      console.error('Failed to load projects:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadAssessmentsForProject = async (projId: string) => {
    try {
      const assessList = await apiClient.getAssessments(projId);
      setAssessments(assessList);
      if (assessList.length > 0) {
        const latest = assessList[0];
        setSelectedAssessmentId(latest.id);
        await loadFindings(latest.id);
      } else {
        setSelectedAssessmentId('');
        setFindings([]);
      }
    } catch (err) {
      console.error('Failed to load assessments:', err);
    }
  };

  const loadFindings = async (assessId: string) => {
    setFindingsLoading(true);
    try {
      const res = await apiClient.getAssessmentCodeFindings(assessId);
      setFindings(res);
    } catch (err) {
      console.error('Failed to load code findings:', err);
    } finally {
      setFindingsLoading(false);
    }
  };

  const handleProjectChange = async (projId: string) => {
    setSelectedProjectId(projId);
    await loadAssessmentsForProject(projId);
  };

  const handleAssessmentChange = async (assessId: string) => {
    setSelectedAssessmentId(assessId);
    await loadFindings(assessId);
  };

  const filteredFindings = findings.filter((f) => {
    const matchesCat = selectedCategory === 'all' || f.category.toLowerCase() === selectedCategory.toLowerCase();
    const matchesSev = selectedSeverity === 'all' || f.severity.toLowerCase() === selectedSeverity.toLowerCase();
    const matchesSearch =
      !searchQuery ||
      f.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.file_path.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.rule_id.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCat && matchesSev && matchesSearch;
  });

  const totalRemediationHours = filteredFindings.reduce((acc, f) => acc + (f.estimated_remediation_hours || 0), 0);
  const criticalCount = filteredFindings.filter((f) => f.severity === 'Critical').length;
  const highCount = filteredFindings.filter((f) => f.severity === 'High').length;

  const getSeverityBadgeClass = (sev: string) => {
    switch (sev.toLowerCase()) {
      case 'critical':
        return 'bg-rose-100 text-rose-800 border-rose-200';
      case 'high':
        return 'bg-amber-100 text-amber-800 border-amber-200';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      case 'low':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      default:
        return 'bg-slate-100 text-slate-800 border-slate-200';
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
    <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Code Diagnostics & Findings</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Fine-grained static analysis, architectural smell detection, and security flaws with remediation recipes.
          </p>
        </div>

        {/* Project & Assessment Selectors */}
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selectedProjectId}
            onChange={(e) => handleProjectChange(e.target.value)}
            className="px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 font-medium text-slate-700 dark:text-slate-200 focus:ring-2 focus:ring-indigo-500"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>

          {assessments.length > 0 && (
            <select
              value={selectedAssessmentId}
              onChange={(e) => handleAssessmentChange(e.target.value)}
              className="px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800 font-medium text-slate-700 dark:text-slate-200 focus:ring-2 focus:ring-indigo-500"
            >
              {assessments.map((a) => (
                <option key={a.id} value={a.id}>
                  {new Date(a.created_at).toLocaleDateString()} — Score: {a.overall_health_score ?? 'N/A'}/100
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Metrics Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
          <p className="text-xs font-semibold uppercase text-slate-400">Total Findings</p>
          <p className="text-2xl font-extrabold text-slate-900 dark:text-white mt-1">{filteredFindings.length}</p>
        </div>
        <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
          <p className="text-xs font-semibold uppercase text-slate-400">Critical Severity</p>
          <p className="text-2xl font-extrabold text-rose-600 mt-1">{criticalCount}</p>
        </div>
        <div className="bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
          <p className="text-xs font-semibold uppercase text-slate-400">High Severity</p>
          <p className="text-2xl font-extrabold text-amber-600 mt-1">{highCount}</p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-xs font-semibold uppercase text-slate-400">Remediation Effort</p>
          <p className="text-2xl font-extrabold text-indigo-600 mt-1">{totalRemediationHours.toFixed(1)} hrs</p>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2 w-full md:w-auto">
          {/* Category Pills */}
          {['all', 'security', 'architecture', 'complexity', 'maintainability'].map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition ${
                selectedCategory === cat ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3 w-full md:w-auto">
          {/* Severity Dropdown */}
          <select
            value={selectedSeverity}
            onChange={(e) => setSelectedSeverity(e.target.value)}
            className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs bg-white text-slate-700 font-medium"
          >
            <option value="all">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          {/* Search Box */}
          <input
            type="text"
            placeholder="Search by file or rule..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs focus:ring-2 focus:ring-indigo-500 w-full sm:w-64"
          />
        </div>
      </div>

      {/* Findings List */}
      {findingsLoading ? (
        <div className="py-12 text-center text-slate-400">Loading code findings...</div>
      ) : filteredFindings.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
          <svg className="w-12 h-12 text-emerald-500 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <h3 className="text-lg font-bold text-slate-900">Zero Diagnostic Violations</h3>
          <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
            No source code findings matching your selected criteria. Your codebase maintainability and security hygiene look clean!
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredFindings.map((f) => (
            <div
              key={f.id}
              className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm hover:border-slate-300 transition"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-100">
                <div className="flex items-center gap-2.5">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold border ${getSeverityBadgeClass(f.severity)}`}>
                    {f.severity}
                  </span>
                  <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                    {f.rule_id}
                  </span>
                  <span className="text-xs font-medium text-slate-400 uppercase tracking-wider capitalize">
                    {f.category}
                  </span>
                </div>
                <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 flex items-center gap-2">
                  <span>Effort: <strong className="text-slate-900 dark:text-white">{f.estimated_remediation_hours}h</strong></span>
                  {f.is_auto_verifiable && (
                    <span className="inline-flex items-center text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10 dark:text-emerald-400 px-2 py-0.5 rounded text-[11px]">
                      Auto-verifiable
                    </span>
                  )}
                </div>
              </div>

              {/* Title & File Anchor */}
              <div className="mt-3">
                <h3 className="text-base font-bold text-slate-900 dark:text-white">{f.title}</h3>
                <div className="flex items-center gap-1.5 text-xs text-indigo-600 font-mono mt-1">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <span>{f.file_path}{f.line_start ? `:${f.line_start}` : ''}{f.line_end && f.line_end !== f.line_start ? `-${f.line_end}` : ''}</span>
                </div>
              </div>

              {/* Technical Evidence */}
              {f.technical_evidence && (
                <div className="mt-3 p-3 rounded-lg bg-slate-900 text-slate-200 text-xs font-mono overflow-x-auto border border-slate-800">
                  <pre>{f.technical_evidence}</pre>
                </div>
              )}

              {/* Explanation & Remediation */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 pt-4 border-t border-slate-100 text-xs">
                <div>
                  <strong className="text-slate-700 block mb-1">Why This Matters:</strong>
                  <p className="text-slate-600 leading-relaxed">{f.why_it_matters || f.explanation}</p>
                </div>
                <div className="bg-indigo-50/50 p-3 rounded-lg border border-indigo-100/70">
                  <strong className="text-indigo-900 block mb-1 flex items-center gap-1">
                    <svg className="w-3.5 h-3.5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Recommended Remediation:
                  </strong>
                  <p className="text-indigo-950 leading-relaxed">{f.recommended_remediation}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

