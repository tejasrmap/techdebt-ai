import React, { useState, useEffect } from 'react';
import { apiClient } from '../services/api';
import { Subscription, Invoice } from '../types';

export const BillingView: React.FC = () => {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    loadBillingData();
  }, []);

  const loadBillingData = async () => {
    setLoading(true);
    try {
      const [sub, invs] = await Promise.all([
        apiClient.getSubscription(),
        apiClient.getInvoices(),
      ]);
      setSubscription(sub);
      setInvoices(invs);
    } catch (err: any) {
      console.error('Failed to load billing:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!window.confirm('Are you sure you want to cancel your subscription at the end of the billing period?')) {
      return;
    }
    setCancelling(true);
    try {
      await apiClient.cancelSubscription();
      setMessage('Subscription set to cancel at end of current period.');
      await loadBillingData();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to cancel subscription');
    } finally {
      setCancelling(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const usage = subscription?.current_usage || {};
  const limits = subscription?.limits || { max_projects: 1, max_assessments_per_month: 10, max_team_members: 1 };

  const projectsPct = Math.min(100, Math.round(((usage.projects || 0) / Math.max(1, limits.max_projects)) * 100));
  const assessmentsPct = Math.min(100, Math.round(((usage.monthly_assessments || 0) / Math.max(1, limits.max_assessments_per_month)) * 100));
  const membersPct = Math.min(100, Math.round(((usage.team_members || 0) / Math.max(1, limits.max_team_members)) * 100));

  return (
    <div className="max-w-6xl mx-auto py-6 px-4 sm:px-6 lg:px-8 space-y-8">
      {/* Title */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Subscription & Billing</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Manage your organization plan, resource quotas, and invoice receipts.
        </p>
      </div>

      {message && (
        <div className="p-4 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-sm font-medium">
          {message}
        </div>
      )}

      {/* Subscription Card */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-100 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">{subscription?.plan_name || 'Free Tier'}</h2>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                subscription?.status === 'active' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
              }`}>
                {subscription?.status?.toUpperCase() || 'ACTIVE'}
              </span>
              <span className="text-xs text-slate-400 capitalize">({subscription?.billing_cycle} billing)</span>
            </div>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              Renewal Date: {subscription?.current_period_end ? new Date(subscription.current_period_end).toLocaleDateString() : 'N/A'}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <a
              href="/pricing"
              className="px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition"
            >
              Change Plan
            </a>
            {subscription?.plan_slug !== 'free' && !subscription?.cancel_at_period_end && (
              <button
                onClick={handleCancel}
                disabled={cancelling}
                className="px-3 py-2 border border-slate-300 text-slate-600 text-sm font-medium rounded-lg hover:bg-slate-50 disabled:opacity-50"
              >
                {cancelling ? 'Cancelling...' : 'Cancel'}
              </button>
            )}
          </div>
        </div>

        {/* Live Quota Progress Bars */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-6">
          {/* Repositories */}
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-100">
            <div className="flex justify-between items-center text-sm font-semibold text-slate-700 mb-2">
              <span>Connected Repositories</span>
              <span>{usage.projects || 0} / {limits.max_projects}</span>
            </div>
            <div className="w-full h-2.5 bg-slate-200 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${projectsPct > 90 ? 'bg-rose-500' : 'bg-indigo-600'}`}
                style={{ width: `${projectsPct}%` }}
              />
            </div>
            <p className="text-xs text-slate-400 mt-2">{limits.max_projects - (usage.projects || 0)} available</p>
          </div>

          {/* Monthly Assessments */}
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-100">
            <div className="flex justify-between items-center text-sm font-semibold text-slate-700 mb-2">
              <span>Monthly Assessments</span>
              <span>{usage.monthly_assessments || 0} / {limits.max_assessments_per_month}</span>
            </div>
            <div className="w-full h-2.5 bg-slate-200 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${assessmentsPct > 90 ? 'bg-rose-500' : 'bg-indigo-600'}`}
                style={{ width: `${assessmentsPct}%` }}
              />
            </div>
            <p className="text-xs text-slate-400 mt-2">{limits.max_assessments_per_month - (usage.monthly_assessments || 0)} remaining this month</p>
          </div>

          {/* Team Seats */}
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-100">
            <div className="flex justify-between items-center text-sm font-semibold text-slate-700 mb-2">
              <span>Team Seats</span>
              <span>{usage.team_members || 0} / {limits.max_team_members}</span>
            </div>
            <div className="w-full h-2.5 bg-slate-200 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${membersPct > 90 ? 'bg-rose-500' : 'bg-indigo-600'}`}
                style={{ width: `${membersPct}%` }}
              />
            </div>
            <p className="text-xs text-slate-400 mt-2">{limits.max_team_members - (usage.team_members || 0)} seats free</p>
          </div>
        </div>
      </div>

      {/* Invoices History Table */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">Billing History & Invoices</h2>
        </div>
        {invoices.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500 dark:text-slate-400">
            No billing transactions or invoices recorded yet.
          </div>
        ) : (
          <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800 text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-600 dark:text-slate-300 font-semibold">
              <tr>
                <th className="px-6 py-3 text-left">Invoice</th>
                <th className="px-6 py-3 text-left">Date</th>
                <th className="px-6 py-3 text-left">Amount</th>
                <th className="px-6 py-3 text-left">Status</th>
                <th className="px-6 py-3 text-right">Receipt</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {invoices.map((inv) => (
                <tr key={inv.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                  <td className="px-6 py-4 font-mono font-medium text-slate-900 dark:text-slate-200">{inv.invoice_number}</td>
                  <td className="px-6 py-4 text-slate-500 dark:text-slate-400">{new Date(inv.created_at).toLocaleDateString()}</td>
                  <td className="px-6 py-4 font-semibold text-slate-900 dark:text-white">
                    ${((inv.amount_paid || inv.amount_due || 0)).toFixed(2)} {inv.currency.toUpperCase()}
                  </td>
                  <td className="px-6 py-4">
                    <span className="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800 capitalize">
                      {inv.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    {inv.hosted_invoice_url ? (
                      <a
                        href={inv.hosted_invoice_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-indigo-600 hover:text-indigo-800 font-semibold"
                      >
                        Download PDF
                      </a>
                    ) : (
                      <span className="text-slate-400">Paid Receipt</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

