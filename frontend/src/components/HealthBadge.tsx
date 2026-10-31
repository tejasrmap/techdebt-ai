import React from 'react';

interface HealthBadgeProps {
  score?: number | null;
  classification?: string | null;
  size?: 'sm' | 'md' | 'lg';
}

export const HealthBadge: React.FC<HealthBadgeProps> = ({ score, classification, size = 'md' }) => {
  let label = classification || (score !== undefined && score !== null ? '' : 'Not Assessed');
  if (score !== undefined && score !== null && !classification) {
    if (score >= 85) label = 'Healthy';
    else if (score >= 70) label = 'Good';
    else if (score >= 50) label = 'Needs Attention';
    else if (score >= 30) label = 'High Risk';
    else label = 'Critical';
  }

  let colorClasses = 'bg-slate-800 text-slate-400 border-slate-700';

  if (label === 'Healthy') {
    colorClasses = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
  } else if (label === 'Good') {
    colorClasses = 'bg-blue-500/10 text-blue-400 border-blue-500/30';
  } else if (label === 'Needs Attention') {
    colorClasses = 'bg-amber-500/10 text-amber-400 border-amber-500/30';
  } else if (label === 'High Risk') {
    colorClasses = 'bg-orange-500/10 text-orange-400 border-orange-500/30';
  } else if (label === 'Critical') {
    colorClasses = 'bg-rose-500/10 text-rose-400 border-rose-500/30';
  }

  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-xs px-2.5 py-1 font-medium',
    lg: 'text-sm px-3 py-1.5 font-semibold',
  }[size];

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border ${colorClasses} ${sizeClasses}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      {label}
      {score !== undefined && score !== null && (
        <span className="opacity-80 font-mono text-[11px]">({score})</span>
      )}
    </span>
  );
};
