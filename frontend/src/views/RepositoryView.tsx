import React, { useState, useEffect } from 'react';
import { apiClient } from '../services/api';
import { Project, RepositoryConnection } from '../types';

export const RepositoryView: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [repoConn, setRepoConn] = useState<RepositoryConnection | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [connecting, setConnecting] = useState(false);

  // Form states
  const [repoUrl, setRepoUrl] = useState('');
  const [provider, setProvider] = useState('github');
  const [branch, setBranch] = useState('main');
  const [token, setToken] = useState('');
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    setLoading(true);
    try {
      const list = await apiClient.getProjects();
      setProjects(list);
      if (list.length > 0) {
        setSelectedProjectId(list[0].id);
        await loadRepository(list[0].id);
      }
    } catch (err) {
      console.error('Failed to load projects:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadRepository = async (projId: string) => {
    try {
      const res = await apiClient.getRepository(projId);
      if (res && res.status !== 'unconnected') {
        setRepoConn(res);
      } else {
        setRepoConn(null);
      }
    } catch (err) {
      setRepoConn(null);
    }
  };

  const handleProjectSelect = async (projId: string) => {
    setSelectedProjectId(projId);
    setMessage(null);
    await loadRepository(projId);
  };

  const handleConnectGit = async (e: React.FormEvent) => {
    e.preventDefault();
    setConnecting(true);
    setMessage(null);
    try {
      await apiClient.connectRepository({
        project_id: selectedProjectId,
        provider,
        repo_url: repoUrl,
        branch,
        access_token: token || undefined,
      });
      setMessage({ text: 'Repository connected successfully!', type: 'success' });
      await loadRepository(selectedProjectId);
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Failed to connect repository', type: 'error' });
    } finally {
      setConnecting(false);
    }
  };

  const handleZipUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setMessage(null);
    try {
      const res = await apiClient.uploadRepositoryZip(selectedProjectId, file, branch);
      setMessage({
        text: `ZIP extracted! Analyzed ${res.file_count || ''} files, discovered ${res.dependencies_discovered || 0} dependencies.`,
        type: 'success',
      });
      await loadRepository(selectedProjectId);
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Failed to upload ZIP archive', type: 'error' });
    } finally {
      setUploading(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect this repository and clean workspace?')) return;
    try {
      await apiClient.disconnectRepository(selectedProjectId);
      setMessage({ text: 'Repository disconnected.', type: 'success' });
      setRepoConn(null);
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Failed to disconnect', type: 'error' });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const selectedProj = projects.find((p) => p.id === selectedProjectId);

  return (
    <div className="max-w-6xl mx-auto py-6 px-4 sm:px-6 lg:px-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Repository Intelligence & CI/CD</h1>
          <p className="text-sm text-slate-500 mt-1">
            Connect private/public repositories or upload archives for static code intelligence.
          </p>
        </div>

        {/* Project Selector */}
        <select
          value={selectedProjectId}
          onChange={(e) => handleProjectSelect(e.target.value)}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white font-medium text-slate-700 focus:ring-2 focus:ring-indigo-500"
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
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

      {/* Connected State vs Connect Options */}
      {repoConn ? (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-100">
            <div>
              <div className="flex items-center gap-2.5">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                <h2 className="text-lg font-bold text-slate-900">{repoConn.repo_url || selectedProj?.name}</h2>
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-indigo-50 text-indigo-700 capitalize">
                  {repoConn.provider}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 font-mono">
                Branch: <strong>{repoConn.branch}</strong> | Files: <strong>{repoConn.file_count}</strong> | Size: <strong>{(repoConn.size_bytes / (1024 * 1024)).toFixed(1)} MB</strong>
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleDisconnect}
                className="px-3 py-1.5 border border-rose-200 text-rose-700 rounded-lg text-xs font-semibold hover:bg-rose-50 transition"
              >
                Disconnect Repo
              </button>
            </div>
          </div>

          {/* Languages detected */}
          {selectedProj?.languages && selectedProj.languages.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase text-slate-400 tracking-wider mb-2">Detected Languages</h3>
              <div className="flex flex-wrap gap-2">
                {selectedProj.languages.map((l) => (
                  <span key={l} className="px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-800">
                    {l}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Webhook CI/CD Integration snippet */}
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-100">
            <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">Webhook Automated Ingestion</h3>
            <p className="text-xs text-slate-500 mb-3">
              Configure this webhook URL in GitHub/GitLab settings to automatically trigger review upon push:
            </p>
            <code className="text-xs font-mono bg-white p-2 rounded border border-slate-200 block select-all">
              {window.location.origin}/api/v1/repositories/webhook/{repoConn.provider}
            </code>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {/* Git URL Connect Form */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
            <h2 className="text-base font-bold text-slate-900 mb-1">Connect Remote Repository</h2>
            <p className="text-xs text-slate-500 mb-5">
              Supports public or token-authenticated GitHub, GitLab, and Bitbucket URLs with SSRF protection.
            </p>

            <form onSubmit={handleConnectGit} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Provider</label>
                <select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs bg-white"
                >
                  <option value="github">GitHub</option>
                  <option value="gitlab">GitLab</option>
                  <option value="bitbucket">Bitbucket</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Repository HTTPS URL</label>
                <input
                  type="url"
                  required
                  placeholder="https://github.com/organization/repository.git"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs font-mono"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Branch</label>
                  <input
                    type="text"
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Personal Access Token</label>
                  <input
                    type="password"
                    placeholder="Optional for public"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={connecting}
                className="w-full py-2.5 px-4 bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 transition disabled:opacity-50 mt-2"
              >
                {connecting ? 'Validating & Connecting...' : 'Connect Git Repository'}
              </button>
            </form>
          </div>

          {/* Manual ZIP Upload */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm flex flex-col justify-between">
            <div>
              <h2 className="text-base font-bold text-slate-900 mb-1">Upload Archive (ZIP)</h2>
              <p className="text-xs text-slate-500 mb-5">
                Upload a project source bundle directly. Automatic Zip-Slip path traversal defense and resource cap enforcement.
              </p>

              <div className="border-2 border-dashed border-slate-300 rounded-xl p-8 text-center hover:border-indigo-500 transition">
                <svg className="w-10 h-10 text-slate-400 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <label className="cursor-pointer">
                  <span className="text-sm font-semibold text-indigo-600 hover:text-indigo-800">
                    Click to select ZIP archive
                  </span>
                  <input
                    type="file"
                    accept=".zip"
                    onChange={handleZipUpload}
                    disabled={uploading}
                    className="hidden"
                  />
                </label>
                <p className="text-xs text-slate-400 mt-1">Maximum uncompressed size: 100 MB</p>
              </div>
            </div>

            {uploading && (
              <div className="mt-4 p-3 bg-indigo-50 text-indigo-800 text-xs font-semibold rounded-lg text-center animate-pulse">
                Extracting archive, profiling languages, and scanning manifests...
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

