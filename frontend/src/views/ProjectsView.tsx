import React, { useState, useEffect } from 'react';
import {
  FolderGit2,
  Plus,
  Upload,
  Play,
  Trash2,
  ExternalLink,
  Code2,
  FileCode,
  Calendar,
  Layers,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';
import { apiClient } from '../services/api';
import { Project, Technology } from '../types';
import { HealthBadge } from '../components/HealthBadge';

interface ProjectsViewProps {
  onRunAssessment: (projectId: string) => void;
}

export const ProjectsView: React.FC<ProjectsViewProps> = ({ onRunAssessment }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState<string | null>(null);
  const [showManualModal, setShowManualModal] = useState<string | null>(null);

  // Create form state
  const [projectName, setProjectName] = useState('');
  const [projectDesc, setProjectDesc] = useState('');
  const [repoUrl, setRepoUrl] = useState('');
  const [languagesStr, setLanguagesStr] = useState('TypeScript, React');
  const [ownerName, setOwnerName] = useState('Engineering Team');

  // Import form state
  const [importFileName, setImportFileName] = useState('package.json');
  const [importContent, setImportContent] = useState('');
  const [importSuccess, setImportSuccess] = useState<string | null>(null);

  // Manual Add form state
  const [manualTechName, setManualTechName] = useState('');
  const [manualVersion, setManualVersion] = useState('1.0.0');
  const [manualEcosystem, setManualEcosystem] = useState('npm');

  const fetchProjects = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getProjects();
      setProjects(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const langs = languagesStr.split(',').map((s) => s.trim()).filter(Boolean);
      await apiClient.createProject({
        name: projectName,
        description: projectDesc,
        repository_url: repoUrl,
        languages: langs,
        owner_name: ownerName,
      });
      setShowCreateModal(false);
      setProjectName('');
      setProjectDesc('');
      setRepoUrl('');
      fetchProjects();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to create project');
    }
  };

  const handleDeleteProject = async (id: string, name: string) => {
    if (confirm(`Are you sure you want to delete project '${name}'?`)) {
      await apiClient.deleteProject(id);
      fetchProjects();
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImportFileName(file.name);
      const reader = new FileReader();
      reader.onload = (event) => {
        setImportContent(event.target?.result as string);
      };
      reader.readAsText(file);
    }
  };

  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!showImportModal || !importContent) return;
    try {
      const res = await apiClient.importDependencies(showImportModal, importFileName, importContent);
      setImportSuccess(res.message);
      setTimeout(() => {
        setShowImportModal(null);
        setImportSuccess(null);
        setImportContent('');
        fetchProjects();
      }, 1500);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to parse dependency file');
    }
  };

  const handleManualAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!showManualModal || !manualTechName) return;
    try {
      await apiClient.addTechnology({
        name: manualTechName,
        project_id: showManualModal,
        ecosystem: manualEcosystem,
        installed_version: manualVersion,
      });
      setShowManualModal(null);
      setManualTechName('');
      fetchProjects();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to add technology');
    }
  };

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <FolderGit2 className="w-5 h-5 text-indigo-400" />
            Software Projects
          </h2>
          <p className="text-xs text-slate-400">
            Manage codebases, upload dependency manifests, and run architecture debt audits.
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs flex items-center gap-1.5 shadow-md shadow-indigo-600/30 transition-all"
        >
          <Plus className="w-4 h-4" /> New Project
        </button>
      </div>

      {/* Projects Grid */}
      {loading ? (
        <div className="p-12 text-center text-xs text-slate-400">Loading projects...</div>
      ) : projects.length === 0 ? (
        <div className="p-12 text-center rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
          <FolderGit2 className="w-8 h-8 text-slate-600 mx-auto" />
          <h3 className="text-sm font-semibold text-slate-300">No Projects Found</h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Get started by adding your first software project and importing its dependency manifest.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-xs font-medium"
          >
            Create Project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((p) => (
            <div
              key={p.id}
              className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 flex flex-col justify-between hover:border-slate-700 transition-all shadow-lg shadow-black/20"
            >
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-1">
                    <h3 className="text-base font-bold text-white tracking-tight">{p.name}</h3>
                    <p className="text-xs text-slate-400 line-clamp-2">{p.description || 'No description provided.'}</p>
                  </div>
                  <HealthBadge score={p.health_score} classification={p.risk_classification} size="sm" />
                </div>

                {p.repository_url && (
                  <a
                    href={p.repository_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 font-mono"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span className="truncate max-w-[200px]">{p.repository_url.replace('https://', '')}</span>
                  </a>
                )}

                {/* Tags */}
                <div className="flex flex-wrap gap-1.5">
                  {p.languages.map((l) => (
                    <span key={l} className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] font-mono border border-slate-700">
                      {l}
                    </span>
                  ))}
                  <span className="px-2 py-0.5 rounded bg-indigo-950/60 text-indigo-300 text-[10px] font-mono border border-indigo-800">
                    {p.technology_count} dependencies
                  </span>
                </div>
              </div>

              {/* Action buttons */}
              <div className="pt-6 mt-6 border-t border-slate-800/80 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowImportModal(p.id)}
                    title="Import dependency manifest"
                    className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-xs font-medium flex items-center gap-1"
                  >
                    <Upload className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Import</span>
                  </button>
                  <button
                    onClick={() => setShowManualModal(p.id)}
                    title="Add package manually"
                    className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-xs font-medium"
                  >
                    + Package
                  </button>
                  <button
                    onClick={() => handleDeleteProject(p.id, p.name)}
                    title="Delete project"
                    className="p-2 rounded-lg bg-slate-800/60 hover:bg-rose-500/10 text-slate-400 hover:text-rose-400 border border-slate-800"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                <button
                  onClick={() => onRunAssessment(p.id)}
                  className="px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-indigo-600/30 transition-all"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Audit</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal: Create Project */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl">
            <h3 className="text-base font-bold text-white">Create New Project</h3>
            <form onSubmit={handleCreateProject} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Project Name *</label>
                <input
                  type="text"
                  required
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g. Identity & Access Service"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Description</label>
                <textarea
                  rows={2}
                  value={projectDesc}
                  onChange={(e) => setProjectDesc(e.target.value)}
                  placeholder="Brief architecture overview"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Repository URL</label>
                <input
                  type="url"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  placeholder="https://github.com/org/repo"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Languages (comma separated)</label>
                <input
                  type="text"
                  value={languagesStr}
                  onChange={(e) => setLanguagesStr(e.target.value)}
                  placeholder="TypeScript, Python, Go"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
                >
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Import Dependencies */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-xl w-full p-6 space-y-5 shadow-2xl">
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Upload className="w-5 h-5 text-cyan-400" /> Import Dependency Manifest
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Supports package.json, requirements.txt, pyproject.toml, pom.xml, build.gradle, Cargo.toml, go.mod, composer.json.
              </p>
            </div>

            {importSuccess ? (
              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4" />
                <span>{importSuccess}</span>
              </div>
            ) : (
              <form onSubmit={handleImportSubmit} className="space-y-4 text-xs">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Choose File</label>
                  <input
                    type="file"
                    onChange={handleFileUpload}
                    className="w-full text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-indigo-400 hover:file:bg-slate-700"
                  />
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">
                    Or Paste Manifest Contents ({importFileName})
                  </label>
                  <textarea
                    rows={8}
                    required
                    value={importContent}
                    onChange={(e) => setImportContent(e.target.value)}
                    placeholder='Paste raw file content here (e.g. {"dependencies": {"react": "^18.2.0"}})'
                    className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 font-mono text-[11px] placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div className="flex items-center justify-end gap-3 pt-3">
                  <button
                    type="button"
                    onClick={() => setShowImportModal(null)}
                    className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
                  >
                    Parse & Extract Dependencies
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Modal: Manual Add Package */}
      {showManualModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-5 shadow-2xl">
            <h3 className="text-base font-bold text-white">Add Technology Manually</h3>
            <form onSubmit={handleManualAddSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Package / Technology Name *</label>
                <input
                  type="text"
                  required
                  value={manualTechName}
                  onChange={(e) => setManualTechName(e.target.value)}
                  placeholder="e.g. express, celery, redis"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Installed Version</label>
                <input
                  type="text"
                  value={manualVersion}
                  onChange={(e) => setManualVersion(e.target.value)}
                  placeholder="e.g. 4.18.2"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Ecosystem</label>
                <select
                  value={manualEcosystem}
                  onChange={(e) => setManualEcosystem(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 focus:outline-none focus:border-indigo-500"
                >
                  <option value="npm">npm / Node.js</option>
                  <option value="pypi">PyPI / Python</option>
                  <option value="maven">Maven / Java</option>
                  <option value="cargo">Cargo / Rust</option>
                  <option value="go">Go Modules</option>
                  <option value="packagist">Packagist / PHP</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setShowManualModal(null)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium"
                >
                  Save Technology
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
