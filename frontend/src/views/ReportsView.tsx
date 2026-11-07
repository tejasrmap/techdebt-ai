import React, { useState, useEffect } from 'react';
import {
  FileSpreadsheet,
  FileText,
  Download,
  Calendar,
  FolderGit2,
  CheckCircle2,
  ShieldCheck,
  ExternalLink
} from 'lucide-react';
import { apiClient } from '../services/api';
import { HealthBadge } from '../components/HealthBadge';

export const ReportsView: React.FC = () => {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const fetchReports = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getReportsList();
      setReports(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPdf = async (assessmentId: string, projectName: string) => {
    try {
      setDownloadingId(`pdf-${assessmentId}`);
      await apiClient.downloadPdfReport(assessmentId, `${projectName.replace(/[^a-zA-Z0-9_-]/g, '_')}_audit_report.pdf`);
    } catch (err) {
      console.error('Failed to download PDF report', err);
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDownloadCsv = async (assessmentId: string, projectName: string) => {
    try {
      setDownloadingId(`csv-${assessmentId}`);
      await apiClient.downloadCsvReport(assessmentId, `${projectName.replace(/[^a-zA-Z0-9_-]/g, '_')}_audit_report.csv`);
    } catch (err) {
      console.error('Failed to download CSV report', err);
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDownloadPortfolioPdf = async () => {
    try {
      setDownloadingId('portfolio-pdf');
      await apiClient.downloadPortfolioPdf('enterprise_portfolio_report.pdf');
    } catch (err) {
      console.error('Failed to download portfolio PDF', err);
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDownloadPortfolioCsv = async () => {
    try {
      setDownloadingId('portfolio-csv');
      await apiClient.downloadPortfolioCsv('enterprise_portfolio_report.csv');
    } catch (err) {
      console.error('Failed to download portfolio CSV', err);
    } finally {
      setDownloadingId(null);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 rounded-2xl bg-slate-900 border border-slate-800">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5 text-indigo-400" />
            Executive & Audit Reports
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Download professional, board-ready executive PDF summaries and full dependency CSV manifests.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleDownloadPortfolioPdf}
            disabled={downloadingId === 'portfolio-pdf'}
            className="px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" />
            <span>{downloadingId === 'portfolio-pdf' ? 'Preparing PDF...' : 'Portfolio PDF'}</span>
          </button>
          <button
            onClick={handleDownloadPortfolioCsv}
            disabled={downloadingId === 'portfolio-csv'}
            className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
            <span>{downloadingId === 'portfolio-csv' ? 'Preparing CSV...' : 'Portfolio CSV'}</span>
          </button>
        </div>
      </div>

      {/* Reports Table */}
      {loading ? (
        <div className="p-12 text-center text-xs text-slate-500">Loading available reports...</div>
      ) : reports.length === 0 ? (
        <div className="p-12 text-center rounded-2xl bg-slate-900 border border-slate-800 space-y-2">
          <FileText className="w-8 h-8 text-slate-600 mx-auto" />
          <h3 className="text-sm font-semibold text-slate-300">No Assessment Reports Yet</h3>
          <p className="text-xs text-slate-500">Run an assessment to generate downloadable compliance reports.</p>
        </div>
      ) : (
        <div className="rounded-2xl bg-slate-900 border border-slate-800 overflow-hidden shadow-xl">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-800/80 text-slate-400 border-b border-slate-800 font-medium">
              <tr>
                <th className="py-3.5 px-4">Project</th>
                <th className="py-3.5 px-4">Assessment Date</th>
                <th className="py-3.5 px-4">Health Score</th>
                <th className="py-3.5 px-4">Classification</th>
                <th className="py-3.5 px-4 text-right">Downloads</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {reports.map((r) => (
                <tr key={r.assessment_id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="py-3.5 px-4 font-semibold text-white flex items-center gap-2">
                    <FolderGit2 className="w-4 h-4 text-indigo-400" />
                    <span>{r.project_name}</span>
                  </td>
                  <td className="py-3.5 px-4 font-mono text-slate-400">
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td className="py-3.5 px-4 font-bold text-white">
                    {r.health_score} / 100
                  </td>
                  <td className="py-3.5 px-4">
                    <HealthBadge score={r.health_score} classification={r.risk_classification} size="sm" />
                  </td>
                  <td className="py-3.5 px-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleDownloadPdf(r.assessment_id, r.project_name)}
                        disabled={downloadingId === `pdf-${r.assessment_id}`}
                        className="px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        <span>{downloadingId === `pdf-${r.assessment_id}` ? 'Downloading...' : 'PDF Report'}</span>
                      </button>
                      <button
                        onClick={() => handleDownloadCsv(r.assessment_id, r.project_name)}
                        disabled={downloadingId === `csv-${r.assessment_id}`}
                        className="px-3 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
                      >
                        <FileSpreadsheet className="w-3.5 h-3.5" />
                        <span>{downloadingId === `csv-${r.assessment_id}` ? 'Downloading...' : 'CSV Audit'}</span>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

