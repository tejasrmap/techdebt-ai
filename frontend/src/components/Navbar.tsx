import React from 'react';
import { Building2, Shield, Sparkles } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface NavbarProps {
  title: string;
  subtitle?: string;
  onRunGlobalScan?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ title, subtitle }) => {
  const { user } = useAuth();

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-900/60 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-10">
      <div>
        <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
          {title}
        </h2>
        {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-4">
        {/* Organization indicator */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/80 border border-slate-700/80 text-xs text-slate-300">
          <Building2 className="w-3.5 h-3.5 text-indigo-400" />
          <span className="font-medium">{user?.organization_name || 'Acme Engineering'}</span>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 ml-1" />
        </div>

        {/* Intelligence badge */}
        <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-cyan-950/40 border border-cyan-800/40 text-xs text-cyan-300">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400 animate-spin-slow" />
          <span>Firecrawl + Memory Active</span>
        </div>

        {/* Role badge */}
        <div className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 text-[11px] font-mono text-slate-300 border border-slate-700">
          <Shield className="w-3 h-3 text-amber-400" />
          <span>{user?.role}</span>
        </div>
      </div>
    </header>
  );
};

