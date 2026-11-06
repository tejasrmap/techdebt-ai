import React from 'react';
import { Building2, Shield, Sparkles, Menu } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface NavbarProps {
  title: string;
  subtitle?: string;
  onRunGlobalScan?: () => void;
  onToggleSidebar?: () => void;
  isSidebarOpen?: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  title,
  subtitle,
  onToggleSidebar,
  isSidebarOpen = false
}) => {
  const { user } = useAuth();

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-900/60 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between sticky top-0 z-10">
      <div className="flex items-center gap-3">
        {onToggleSidebar && (
          <button
            type="button"
            onClick={onToggleSidebar}
            aria-label="Toggle navigation menu"
            aria-expanded={isSidebarOpen}
            aria-controls="sidebar-navigation"
            className="md:hidden p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            <Menu className="w-5 h-5" aria-hidden="true" />
          </button>
        )}
        <div>
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2">
            {title}
          </h2>
          {subtitle && <p className="text-xs text-slate-400 mt-0.5 hidden sm:block">{subtitle}</p>}
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-4">
        {/* Organization indicator */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/80 border border-slate-700/80 text-xs text-slate-300">
          <Building2 className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />
          <span className="font-medium truncate max-w-[120px] sm:max-w-none">{user?.organization_name || 'Acme Engineering'}</span>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 ml-1 shrink-0" aria-label="Online" />
        </div>

        {/* Intelligence badge */}
        <div className="hidden lg:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-cyan-950/40 border border-cyan-800/40 text-xs text-cyan-300">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400 animate-spin-slow" aria-hidden="true" />
          <span>Firecrawl + Memory Active</span>
        </div>

        {/* Role badge */}
        <div className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 text-[11px] font-mono text-slate-300 border border-slate-700">
          <Shield className="w-3 h-3 text-amber-400" aria-hidden="true" />
          <span>{user?.role}</span>
        </div>
      </div>
    </header>
  );
};
