import React, { useState, useEffect } from 'react';
import {
  Layers,
  CheckCircle2,
  ExternalLink,
  RefreshCw,
  Lock,
  Save
} from 'lucide-react';
import { apiClient } from '../services/api';
import { IntegrationSettings } from '../types';

export const IntegrationsView: React.FC = () => {
  const [settings, setSettings] = useState<IntegrationSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verifyMessage, setVerifyMessage] = useState<Record<string, string>>({});

  // Input fields for updating keys securely
  const [firecrawlKey, setFirecrawlKey] = useState('');
  const [openaiKey, setOpenaiKey] = useState('');
  const [geminiKey, setGeminiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getSettings();
      setSettings(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const handleVerify = async (service: string) => {
    try {
      setVerifying(service);
      const res = await apiClient.verifyIntegration(service);
      setVerifyMessage((prev) => ({
        ...prev,
        [service]: `${res.status.toUpperCase()}: ${res.message}`,
      }));
      fetchSettings();
    } catch (err: any) {
      setVerifyMessage((prev) => ({
        ...prev,
        [service]: `Error: ${err.response?.data?.detail || err.message}`,
      }));
    } finally {
      setVerifying(null);
    }
  };

  const handleSaveKeys = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      const payload: any = {};
      if (firecrawlKey) payload.firecrawl_api_key = firecrawlKey;
      if (openaiKey) payload.openai_api_key = openaiKey;
      if (geminiKey) payload.gemini_api_key = geminiKey;

      await apiClient.updateSettings(payload);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
      setFirecrawlKey('');
      setOpenaiKey('');
      setGeminiKey('');
      fetchSettings();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to save integration settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading || !settings) {
    return <div className="p-12 text-center text-xs text-slate-500">Loading integration status...</div>;
  }

  const integrationsList = [
    {
      id: 'firecrawl',
      name: 'Firecrawl API',
      category: 'Web Intelligence Engine',
      description: 'Crawls official documentation, release notes, security advisories, and deprecation bulletins.',
      isConfigured: settings.firecrawl_configured,
      statusLabel: settings.firecrawl_configured ? 'API Key Configured' : 'Official Registry Fallback Mode',
      statusClass: settings.firecrawl_configured
        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
        : 'bg-amber-500/10 text-amber-400 border-amber-500/30',
      helpUrl: 'https://firecrawl.dev',
    },
    {
      id: 'memento',
      name: 'Historical Assessment Memory',
      category: 'Historical Context & Memory',
      description: 'Persists longitudinal architecture context and delta trends with strict multi-tenant isolation directly in PostgreSQL.',
      isConfigured: true,
      statusLabel: 'PostgreSQL Authoritative Active',
      statusClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
      helpUrl: '',
    },
    {
      id: 'gemini',
      name: 'Google Gemini API',
      category: 'GenAI Reasoning',
      description: 'Powers 8-dimension weighted debt evaluation with strict JSON schema outputs.',
      isConfigured: settings.gemini_configured,
      statusLabel: settings.gemini_configured ? 'Connected' : 'Deterministic Evidence Rule Fallback',
      statusClass: settings.gemini_configured
        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
        : 'bg-slate-800 text-slate-300 border-slate-700',
      helpUrl: 'https://ai.google.dev',
    },
    {
      id: 'openai',
      name: 'OpenAI API',
      category: 'GenAI Reasoning',
      description: 'Alternative LLM provider for structured technical debt reasoning and trade-off comparison.',
      isConfigured: settings.openai_configured,
      statusLabel: settings.openai_configured ? 'Connected' : 'Unconfigured',
      statusClass: settings.openai_configured
        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
        : 'bg-slate-800 text-slate-400 border-slate-700',
      helpUrl: 'https://platform.openai.com',
    },
  ];

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 rounded-2xl bg-slate-900 border border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Layers className="w-5 h-5 text-indigo-400" />
            Integrations & Service Health
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Status and live connection verification for Firecrawl, PostgreSQL Historical Memory, and GenAI inference models.
          </p>
        </div>
      </div>

      {/* Integration Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {integrationsList.map((item) => (
          <div
            key={item.id}
            className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 flex flex-col justify-between space-y-4 shadow-lg shadow-black/20"
          >
            <div className="space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    {item.name}
                  </h3>
                  <p className="text-[11px] font-mono text-indigo-400 mt-0.5">{item.category}</p>
                </div>
                <span className={`px-2.5 py-1 rounded-full text-[11px] font-medium border ${item.statusClass}`}>
                  {item.statusLabel}
                </span>
              </div>

              <p className="text-xs text-slate-400 leading-relaxed">{item.description}</p>
            </div>

            <div className="pt-4 border-t border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between gap-2">
                {item.helpUrl ? (
                  <a
                    href={item.helpUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-slate-500 hover:text-slate-300 flex items-center gap-1 font-mono"
                  >
                    <span>Documentation</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                ) : (
                  <span className="text-xs text-slate-500 font-mono">
                    PostgreSQL Authoritative Engine
                  </span>
                )}

                <button
                  onClick={() => handleVerify(item.id)}
                  disabled={verifying === item.id}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${verifying === item.id ? 'animate-spin' : ''}`} />
                  <span>Verify Status</span>
                </button>
              </div>

              {verifyMessage[item.id] && (
                <div className="p-2.5 rounded-lg bg-slate-950 text-indigo-300 font-mono text-[11px] border border-slate-800">
                  {verifyMessage[item.id]}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Secure API Key Configuration Form */}
      <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
        <div className="flex items-center gap-2">
          <Lock className="w-4 h-4 text-indigo-400" />
          <h3 className="text-sm font-bold text-white tracking-tight">Configure / Update Secrets</h3>
        </div>
        <p className="text-xs text-slate-400">
          API keys are encrypted and stored in backend environment variables and organization settings. They are never exposed in browser telemetry.
        </p>

        {saveSuccess && (
          <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            <span>Settings saved successfully.</span>
          </div>
        )}

        <form onSubmit={handleSaveKeys} className="space-y-4 text-xs">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-slate-300 font-medium mb-1">Firecrawl API Key</label>
              <input
                type="password"
                value={firecrawlKey}
                onChange={(e) => setFirecrawlKey(e.target.value)}
                placeholder="fc-••••••••••••••••"
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Google Gemini API Key</label>
              <input
                type="password"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder="AIzaSy••••••••••••••••"
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">OpenAI API Key</label>
              <input
                type="password"
                value={openaiKey}
                onChange={(e) => setOpenaiKey(e.target.value)}
                placeholder="sk-••••••••••••••••"
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center gap-2 shadow-md shadow-indigo-600/30 transition-all disabled:opacity-50"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{saving ? 'Updating...' : 'Save Configuration'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

