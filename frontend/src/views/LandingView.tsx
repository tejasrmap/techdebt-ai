import React, { useState } from 'react';
import {
  Sparkles,
  ShieldCheck,
  Zap,
  History,
  ArrowRight,
  Lock,
  Mail,
  Building,
  Terminal,
  Activity,
  Ticket
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { apiClient } from '../services/api';

export const LandingView: React.FC = () => {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register' | 'accept_invite'>('login');
  
  // Login / Register state
  const [email, setEmail] = useState('admin@techdebt.ai');
  const [password, setPassword] = useState('AdminPass123!');
  const [fullName, setFullName] = useState('Sarah Connor');
  const [orgName, setOrgName] = useState('Acme Cloud Engineering');
  
  // Invitation state
  const [inviteToken, setInviteToken] = useState('');
  const [inviteFullName, setInviteFullName] = useState('');
  const [invitePassword, setInvitePassword] = useState('');

  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);
    setLoading(true);

    try {
      if (mode === 'register') {
        await register({
          email,
          password,
          full_name: fullName,
          organization_name: orgName,
        });
      } else if (mode === 'login') {
        await login(email, password);
      } else if (mode === 'accept_invite') {
        const res = await apiClient.acceptInvitation({
          token: inviteToken.trim(),
          full_name: inviteFullName.trim(),
          password: invitePassword,
        });
        localStorage.setItem('techdebt_token', res.access_token);
        localStorage.setItem('techdebt_user', JSON.stringify(res.user));
        window.location.reload();
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Authentication failed. Please check credentials or token.');
    } finally {
      setLoading(false);
    }
  };

  const setDemoAccount = (role: 'admin' | 'manager' | 'dev') => {
    setMode('login');
    if (role === 'admin') {
      setEmail('admin@techdebt.ai');
      setPassword('AdminPass123!');
    } else if (role === 'manager') {
      setEmail('manager@techdebt.ai');
      setPassword('ManagerPass123!');
    } else {
      setEmail('dev@techdebt.ai');
      setPassword('DevPass123!');
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between">
      {/* Top Navbar */}
      <header className="border-b border-slate-800/80 px-8 py-5 flex items-center justify-between max-w-7xl mx-auto w-full">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <span className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              TechDebt <span className="text-cyan-400 font-mono text-xs px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-800">AI</span>
            </span>
            <p className="text-[11px] text-slate-400">Technology Debt Review Assistant</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <a
            href="/pricing"
            className="text-xs font-semibold text-slate-300 hover:text-white transition"
          >
            Pricing & Plans
          </a>
          <a
            href="#auth-section"
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/30 transition-all flex items-center gap-1.5"
          >
            Launch Console <ArrowRight className="w-3.5 h-3.5" />
          </a>
        </div>
      </header>

      {/* Main Hero & Auth Container */}
      <main className="max-w-7xl mx-auto px-6 py-12 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center flex-1">
        {/* Left Column: Hero Content */}
        <div className="lg:col-span-7 space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-950/60 border border-indigo-800/50 text-xs text-indigo-300">
            <Zap className="w-3.5 h-3.5 text-cyan-400" />
            <span>GenAI Autonomous Architecture Assessment</span>
          </div>

          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white leading-[1.15]">
            Master technical debt before it masters{' '}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-cyan-400 to-teal-300">
              your engineering velocity.
            </span>
          </h1>

          <p className="text-base text-slate-300 leading-relaxed max-w-2xl">
            TechDebt AI continuously evaluates your languages, frameworks, packages, and dependencies using{' '}
            <strong className="text-white">Firecrawl</strong> web intelligence,{' '}
            <strong className="text-white">PostgreSQL Historical Storage</strong>, Google OSV vulnerability feeds, and evidence-grounded AI reasoning.
          </p>

          {/* Value Highlights */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 space-y-1.5">
              <div className="flex items-center gap-2 text-cyan-400 font-semibold text-xs">
                <Terminal className="w-4 h-4" />
                <span>Multi-Ecosystem Discovery</span>
              </div>
              <p className="text-xs text-slate-400">
                Parses package.json, requirements.txt, pyproject.toml, pom.xml, build.gradle, Cargo.toml, go.mod, and composer.json.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 space-y-1.5">
              <div className="flex items-center gap-2 text-indigo-400 font-semibold text-xs">
                <Activity className="w-4 h-4" />
                <span>8-Dimension Weighted Scoring</span>
              </div>
              <p className="text-xs text-slate-400">
                Security exposure, maintenance decay, version currency, ecosystem compatibility, and upgrade complexity.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 space-y-1.5">
              <div className="flex items-center gap-2 text-emerald-400 font-semibold text-xs">
                <History className="w-4 h-4" />
                <span>Historical Memory Regression Tracking</span>
              </div>
              <p className="text-xs text-slate-400">
                Tracks health score trends, explains why scores shifted, and alerts on newly emerging vulnerabilities.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 space-y-1.5">
              <div className="flex items-center gap-2 text-amber-400 font-semibold text-xs">
                <ShieldCheck className="w-4 h-4" />
                <span>Executive Reports & Audit CSV</span>
              </div>
              <p className="text-xs text-slate-400">
                Generate downloadable, board-ready executive PDFs and complete audit CSV inventories with one click.
              </p>
            </div>
          </div>
        </div>

        {/* Right Column: Auth Card */}
        <div id="auth-section" className="lg:col-span-5">
          <div className="p-8 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-2xl backdrop-blur-xl space-y-6">
            {/* Mode Switcher Tabs */}
            <div className="flex border-b border-slate-800 pb-2 gap-2 text-xs">
              <button
                type="button"
                onClick={() => { setMode('login'); setError(null); }}
                className={`pb-1 font-semibold transition-colors ${mode === 'login' ? 'text-indigo-400 border-b-2 border-indigo-500' : 'text-slate-400 hover:text-slate-200'}`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => { setMode('register'); setError(null); }}
                className={`pb-1 font-semibold transition-colors ${mode === 'register' ? 'text-indigo-400 border-b-2 border-indigo-500' : 'text-slate-400 hover:text-slate-200'}`}
              >
                New Organization
              </button>
              <button
                type="button"
                onClick={() => { setMode('accept_invite'); setError(null); }}
                className={`pb-1 font-semibold transition-colors ${mode === 'accept_invite' ? 'text-cyan-400 border-b-2 border-cyan-500' : 'text-slate-400 hover:text-slate-200'}`}
              >
                Join with Invite
              </button>
            </div>

            <div className="space-y-1">
              <h2 className="text-xl font-bold text-white tracking-tight">
                {mode === 'register' ? 'Create Organization Account' : mode === 'accept_invite' ? 'Accept Organization Invitation' : 'Sign in to TechDebt AI'}
              </h2>
              <p className="text-xs text-slate-400">
                {mode === 'register' ? 'Set up a new isolated organization workspace.' : mode === 'accept_invite' ? 'Enter your invitation token to join an existing organization.' : 'Access your projects, risks, and health scores.'}
              </p>
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                {error}
              </div>
            )}

            {successMsg && (
              <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs">
                {successMsg}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {mode === 'accept_invite' ? (
                <>
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Invitation Token *</label>
                    <div className="relative">
                      <Ticket className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                      <input
                        type="text"
                        required
                        value={inviteToken}
                        onChange={(e) => setInviteToken(e.target.value)}
                        placeholder="Paste invitation token here"
                        className="w-full pl-9 pr-3 py-2 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 font-mono focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Your Full Name *</label>
                    <input
                      type="text"
                      required
                      value={inviteFullName}
                      onChange={(e) => setInviteFullName(e.target.value)}
                      placeholder="Alex Rivera"
                      className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Set Your Password *</label>
                    <div className="relative">
                      <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                      <input
                        type="password"
                        required
                        value={invitePassword}
                        onChange={(e) => setInvitePassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full pl-9 pr-3 py-2 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full py-2.5 px-4 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-xs tracking-wide uppercase transition-all shadow-md shadow-cyan-600/30 disabled:opacity-50"
                  >
                    {loading ? 'Validating Token...' : 'Join Organization & Launch'}
                  </button>
                </>
              ) : (
                <>
                  {mode === 'register' && (
                    <>
                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">Your Full Name</label>
                        <input
                          type="text"
                          required
                          value={fullName}
                          onChange={(e) => setFullName(e.target.value)}
                          placeholder="Sarah Connor"
                          className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-slate-300 mb-1">New Organization Name</label>
                        <div className="relative">
                          <Building className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                          <input
                            type="text"
                            required
                            value={orgName}
                            onChange={(e) => setOrgName(e.target.value)}
                            placeholder="Acme Cloud Engineering"
                            className="w-full pl-9 pr-3 py-2 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                          />
                        </div>
                      </div>
                    </>
                  )}

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Work Email</label>
                    <div className="relative">
                      <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                      <input
                        type="email"
                        required
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="admin@techdebt.ai"
                        className="w-full pl-9 pr-3 py-2 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">Password</label>
                    <div className="relative">
                      <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                      <input
                        type="password"
                        required
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full pl-9 pr-3 py-2 bg-slate-800/80 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full py-2.5 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs tracking-wide uppercase transition-all shadow-md shadow-indigo-600/30 disabled:opacity-50"
                  >
                    {loading ? 'Authenticating...' : mode === 'register' ? 'Register Organization & Start' : 'Sign In to Workspace'}
                  </button>
                </>
              )}
            </form>

            {/* Quick Demo Login Fillers */}
            <div className="pt-2 border-t border-slate-800/80">
              <p className="text-[11px] text-slate-400 mb-2 text-center">Quick Demo Profiles (Pre-seeded):</p>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => setDemoAccount('admin')}
                  className="px-2 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-300 font-mono transition-colors border border-slate-700 text-center"
                >
                  CTO / Admin
                </button>
                <button
                  type="button"
                  onClick={() => setDemoAccount('manager')}
                  className="px-2 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-300 font-mono transition-colors border border-slate-700 text-center"
                >
                  Eng Manager
                </button>
                <button
                  type="button"
                  onClick={() => setDemoAccount('dev')}
                  className="px-2 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-slate-300 font-mono transition-colors border border-slate-700 text-center"
                >
                  Developer
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-500">
        <p>TechDebt AI — Technology Debt Review Assistant • Production Quality SaaS Application</p>
      </footer>
    </div>
  );
};
