import React from 'react';
import {
  LayoutDashboard,
  FolderGit2,
  Cpu,
  ShieldCheck,
  AlertTriangle,
  GitCompare,
  History,
  FileSpreadsheet,
  Layers,
  Settings,
  Sparkles,
  LogOut,
  CreditCard,
  Users,
  Bell,
  FileCode2,
  GitBranch,
  BadgePercent,
  UserCheck
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export type NavItem =
  | 'overview'
  | 'projects'
  | 'repositories'
  | 'findings'
  | 'technologies'
  | 'assessments'
  | 'risks'
  | 'compare'
  | 'history'
  | 'reports'
  | 'integrations'
  | 'billing'
  | 'teams'
  | 'notifications'
  | 'pricing'
  | 'profile'
  | 'settings';

interface SidebarProps {
  currentTab: NavItem;
  onSelectTab: (tab: NavItem) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentTab, onSelectTab }) => {
  const { user, logout } = useAuth();

  const navItems = [
    { id: 'overview' as NavItem, label: 'Overview', icon: LayoutDashboard },
    { id: 'projects' as NavItem, label: 'Projects', icon: FolderGit2 },
    { id: 'repositories' as NavItem, label: 'Repositories & CI', icon: GitBranch },
    { id: 'findings' as NavItem, label: 'Code Diagnostics', icon: FileCode2 },
    { id: 'technologies' as NavItem, label: 'Technologies', icon: Cpu },
    { id: 'assessments' as NavItem, label: 'Assessments', icon: ShieldCheck },
    { id: 'risks' as NavItem, label: 'Risk Center', icon: AlertTriangle },
    { id: 'compare' as NavItem, label: 'Tech Comparison', icon: GitCompare },
    { id: 'history' as NavItem, label: 'Historical Intelligence', icon: History },
    { id: 'reports' as NavItem, label: 'Reports', icon: FileSpreadsheet },
    { id: 'billing' as NavItem, label: 'Billing & Plan', icon: CreditCard },
    { id: 'teams' as NavItem, label: 'Teams & Squads', icon: Users },
    { id: 'notifications' as NavItem, label: 'Notifications', icon: Bell },
    { id: 'pricing' as NavItem, label: 'Pricing Plans', icon: BadgePercent },
    { id: 'integrations' as NavItem, label: 'Integrations', icon: Layers },
    { id: 'profile' as NavItem, label: 'Account & Security', icon: UserCheck },
    { id: 'settings' as NavItem, label: 'Settings', icon: Settings },
  ];

  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col justify-between h-screen select-none">
      <div>
        {/* Brand */}
        <div className="p-5 flex items-center gap-3 border-b border-slate-800/80">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-slate-100 text-base leading-tight tracking-tight flex items-center gap-1.5">
              TechDebt <span className="text-cyan-400 font-mono text-xs px-1.5 py-0.5 rounded bg-cyan-950/60 border border-cyan-800/50">AI</span>
            </h1>
            <p className="text-[11px] text-slate-400">Review & Modernization</p>
          </div>
        </div>

        {/* Navigation list */}
        <nav className="p-3 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-indigo-600/15 text-indigo-300 border border-indigo-500/30 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-indigo-400' : 'text-slate-400'}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* User profile & logout */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950/30">
        <div className="flex items-center justify-between p-2 rounded-lg bg-slate-800/40 border border-slate-800">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center font-bold text-xs text-indigo-300 border border-slate-600 shrink-0">
              {user?.full_name?.charAt(0) || 'U'}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-slate-200 truncate">{user?.full_name}</p>
              <p className="text-[10px] text-slate-400 truncate">{user?.role}</p>
            </div>
          </div>
          <button
            onClick={logout}
            title="Log Out"
            className="p-1.5 rounded-md text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
};

