import React, { useState } from 'react';
import {
  GitCompare,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Scale
} from 'lucide-react';
import { apiClient } from '../services/api';
import { TechnologyComparison } from '../types';

export const ComparisonView: React.FC = () => {
  const [techInputs, setTechInputs] = useState<string[]>(['react', 'vue']);
  const [result, setResult] = useState<TechnologyComparison | null>(null);
  const [loading, setLoading] = useState(false);

  const presets = [
    ['react', 'vue'],
    ['fastapi', 'express'],
    ['postgresql', 'mongodb'],
    ['next.js', 'nuxt'],
    ['pydantic', 'marshmallow']
  ];

  const handleCompare = async (techs: string[]) => {
    try {
      setLoading(true);
      const data = await apiClient.compareTechnologies(techs);
      setResult(data);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to generate technology comparison');
    } finally {
      setLoading(false);
    }
  };

  const handlePresetClick = (pair: string[]) => {
    setTechInputs(pair);
    handleCompare(pair);
  };

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 rounded-2xl bg-slate-900 border border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <GitCompare className="w-5 h-5 text-indigo-400" />
            Technology Comparison Engine
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Balanced, multi-dimensional architectural trade-off evaluations powered by GenAI & official registry intelligence.
          </p>
        </div>

        {/* Quick Presets */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[11px] text-slate-400 mr-1">Presets:</span>
          {presets.map((p, idx) => (
            <button
              key={idx}
              onClick={() => handlePresetClick(p)}
              className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-[11px] font-mono text-slate-300 border border-slate-700 transition-colors"
            >
              {p[0]} vs {p[1]}
            </button>
          ))}
        </div>
      </div>

      {/* Input Form */}
      <div className="p-6 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
          Enter 2 to 4 Technologies to Compare
        </h3>

        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={techInputs[0] || ''}
            onChange={(e) => setTechInputs([e.target.value, techInputs[1] || ''])}
            placeholder="Technology 1 (e.g. react)"
            className="flex-1 px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <div className="flex items-center justify-center font-bold text-xs text-slate-500">VS</div>
          <input
            type="text"
            value={techInputs[1] || ''}
            onChange={(e) => setTechInputs([techInputs[0] || '', e.target.value])}
            placeholder="Technology 2 (e.g. angular)"
            className="flex-1 px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <button
            onClick={() => handleCompare(techInputs)}
            disabled={loading}
            className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs flex items-center justify-center gap-2 shadow-md shadow-indigo-600/30 transition-all disabled:opacity-50"
          >
            {loading ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>Evaluating...</span>
              </>
            ) : (
              <>
                <Scale className="w-3.5 h-3.5" />
                <span>Run Comparison</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Comparison Results */}
      {result && (
        <div className="space-y-6">
          {/* Executive Balanced Summary */}
          <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-bold text-white tracking-tight">Architectural Synthesis</h3>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/60 p-4 rounded-xl border border-slate-800">
              {result.balanced_summary}
            </p>
            <p className="text-xs text-indigo-300 leading-relaxed bg-indigo-950/20 p-4 rounded-xl border border-indigo-900/30">
              {result.recommendations}
            </p>
          </div>

          {/* 8 Categories Breakdown */}
          <div className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
            <h3 className="text-sm font-bold text-white tracking-tight">8-Dimension Category Breakdown</h3>
            <div className="space-y-4">
              {result.categories.map((cat, idx) => (
                <div key={idx} className="p-4 rounded-xl bg-slate-950/50 border border-slate-800/80 space-y-2">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <span className="font-semibold text-xs text-white">{cat.category}</span>
                    <div className="flex items-center gap-3">
                      {Object.entries(cat.scores).map(([name, score]) => (
                        <span key={name} className="text-xs font-mono text-slate-300 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
                          {name}: <strong className="text-white">{score}</strong>/100
                        </span>
                      ))}
                    </div>
                  </div>
                  <p className="text-xs text-slate-400 italic">"{cat.analysis}"</p>
                </div>
              ))}
            </div>
          </div>

          {/* Trade-offs Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {Object.entries(result.tradeoffs).map(([name, points]) => (
              <div key={name} className="p-6 rounded-2xl bg-slate-900 border border-slate-800 space-y-3">
                <h4 className="text-sm font-bold text-indigo-300 capitalize">{name} Key Considerations</h4>
                <ul className="space-y-2 text-xs text-slate-300">
                  {points.map((pt, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 shrink-0" />
                      <span>{pt}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

