import React, { useState, useEffect } from 'react';
import { apiClient } from '../services/api';
import { loadRazorpayCheckoutScript } from '../services/razorpay';
import { SubscriptionPlan, Subscription } from '../types';

export const PricingView: React.FC = () => {
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [currentSub, setCurrentSub] = useState<Subscription | null>(null);
  const [razorpayEnabled, setRazorpayEnabled] = useState<boolean>(
    Boolean(import.meta.env.VITE_RAZORPAY_KEY_ID)
  );
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'annual'>('monthly');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [plansData, subData, rzpConfig] = await Promise.all([
        apiClient.getPlans(),
        apiClient.getSubscription().catch(() => null),
        apiClient.getRazorpayConfig ? apiClient.getRazorpayConfig().catch(() => null) : Promise.resolve(null),
      ]);
      setPlans(plansData);
      setCurrentSub(subData);
      if (rzpConfig && typeof rzpConfig.enabled === 'boolean') {
        setRazorpayEnabled(rzpConfig.enabled);
      }
    } catch (err: any) {
      console.error('Failed to load plans:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectPlan = async (planSlug: string) => {
    setActionLoading(planSlug);
    setMessage(null);
    try {
      if (razorpayEnabled && planSlug !== 'free' && apiClient.createRazorpayOrder) {
        const sdkLoaded = await loadRazorpayCheckoutScript();
        if (!sdkLoaded || !window.Razorpay) {
          throw new Error('Unable to load Razorpay Checkout SDK. Please check your network connection.');
        }

        const orderRes = await apiClient.createRazorpayOrder({
          plan_slug: planSlug,
          billing_cycle: billingCycle,
        });

        if (orderRes.mode === 'live_razorpay' && orderRes.order_id) {
          const rzp = new window.Razorpay({
            key: orderRes.key_id || import.meta.env.VITE_RAZORPAY_KEY_ID,
            amount: orderRes.amount,
            currency: orderRes.currency,
            name: 'TechDebt AI',
            description: `${orderRes.plan_name} (${billingCycle} subscription)`,
            order_id: orderRes.order_id,
            theme: { color: '#4f46e5' },
            handler: async (paymentResp) => {
              try {
                const verifyRes = await apiClient.verifyRazorpayPayment({
                  plan_slug: planSlug,
                  billing_cycle: billingCycle,
                  razorpay_order_id: paymentResp.razorpay_order_id,
                  razorpay_payment_id: paymentResp.razorpay_payment_id,
                  razorpay_signature: paymentResp.razorpay_signature,
                });
                setMessage({
                  text: verifyRes.message || `Payment verified! Upgraded to ${orderRes.plan_name}.`,
                  type: 'success',
                });
                await loadData();
              } catch (verifyErr: any) {
                setMessage({
                  text: verifyErr.response?.data?.detail || 'Payment signature verification failed.',
                  type: 'error',
                });
              } finally {
                setActionLoading(null);
              }
            },
            modal: {
              ondismiss: () => {
                setActionLoading(null);
              },
            },
          });
          rzp.open();
          return;
        }
      }

      const res = await apiClient.subscribeOrUpgrade({
        plan_slug: planSlug,
        billing_cycle: billingCycle,
      });
      if (res.checkout_url) {
        window.location.href = res.checkout_url;
      } else {
        setMessage({
          text: res.message || `Successfully switched to ${planSlug} tier!`,
          type: 'success',
        });
        await loadData();
      }
      setActionLoading(null);
    } catch (err: any) {
      setMessage({
        text: err.response?.data?.detail || err.message || 'Failed to update subscription',
        type: 'error',
      });
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="py-8 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="text-center max-w-3xl mx-auto mb-12">
        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight sm:text-4xl">
          Predictable Pricing for High-Velocity Engineering
        </h1>
        <p className="mt-4 text-lg text-slate-600">
          Scale software intelligence across all your repositories with zero hidden fees.
        </p>

        {/* Cycle Toggle */}
        <div className="mt-8 flex justify-center items-center gap-4">
          <span className={`text-sm font-medium ${billingCycle === 'monthly' ? 'text-slate-900' : 'text-slate-500'}`}>
            Monthly Billing
          </span>
          <button
            type="button"
            onClick={() => setBillingCycle(billingCycle === 'monthly' ? 'annual' : 'monthly')}
            className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
              billingCycle === 'annual' ? 'bg-indigo-600' : 'bg-slate-300'
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                billingCycle === 'annual' ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
          <span className={`text-sm font-medium flex items-center gap-1.5 ${billingCycle === 'annual' ? 'text-slate-900' : 'text-slate-500'}`}>
            Annual Billing
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800">
              Save ~20%
            </span>
          </span>
        </div>
        {razorpayEnabled && (
          <div className="mt-4 inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-100 text-xs font-medium text-indigo-700">
            <span>Secured by Razorpay</span>
            <span aria-hidden="true">&bull;</span>
            <span>Cards, UPI &amp; International Checkout</span>
          </div>
        )}
      </div>

      {message && (
        <div
          className={`mb-8 p-4 rounded-lg text-sm font-medium ${
            message.type === 'success' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-rose-50 text-rose-800 border border-rose-200'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-4 sm:grid-cols-2">
        {plans.map((p) => {
          const isCurrent = currentSub?.plan_slug === p.slug;
          const price = billingCycle === 'annual' ? (p.price_annual ? p.price_annual / 12 : 0) : p.price_monthly;
          const isPopular = p.slug === 'professional';

          return (
            <div
              key={p.id}
              className={`relative flex flex-col rounded-2xl border p-8 shadow-sm transition-all duration-200 ${
                isPopular
                  ? 'border-indigo-600 ring-2 ring-indigo-600 bg-white'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              {isPopular && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 rounded-full bg-indigo-600 py-1 px-3.5 text-xs font-semibold text-white tracking-wide uppercase">
                  Most Popular
                </div>
              )}

              <div className="flex-1">
                <h3 className="text-xl font-bold text-slate-900">{p.name}</h3>
                <p className="mt-2 text-sm text-slate-500 min-h-[40px]">{p.description}</p>

                <div className="mt-6 flex items-baseline gap-1">
                  <span className="text-4xl font-extrabold text-slate-900">${Math.round(price)}</span>
                  <span className="text-sm font-medium text-slate-500">/month</span>
                </div>
                {billingCycle === 'annual' && p.price_annual > 0 && (
                  <p className="mt-1 text-xs text-slate-400">Billed annually (${p.price_annual}/yr)</p>
                )}

                <div className="mt-6 border-t border-slate-100 pt-6">
                  <p className="text-xs font-semibold uppercase text-slate-400 tracking-wider mb-4">Included Limits</p>
                  <ul className="space-y-3 text-sm text-slate-600">
                    <li className="flex items-center gap-2">
                      <svg className="w-4 h-4 text-indigo-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span><strong>{p.max_projects}</strong> Repositories</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <svg className="w-4 h-4 text-indigo-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span><strong>{p.max_assessments_per_month}</strong> Monthly Reviews</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <svg className="w-4 h-4 text-indigo-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span><strong>{p.max_team_members}</strong> Team Seats</span>
                    </li>
                  </ul>
                </div>

                <div className="mt-6 border-t border-slate-100 pt-6">
                  <p className="text-xs font-semibold uppercase text-slate-400 tracking-wider mb-4">Features</p>
                  <ul className="space-y-3 text-sm text-slate-600">
                    {p.features.map((feat, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <svg className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        <span>{feat}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="mt-8">
                {isCurrent ? (
                  <button
                    disabled
                    className="w-full py-2.5 px-4 rounded-lg bg-slate-100 text-slate-500 font-semibold text-sm cursor-not-allowed border border-slate-200"
                  >
                    Current Plan
                  </button>
                ) : (
                  <button
                    onClick={() => handleSelectPlan(p.slug)}
                    disabled={actionLoading !== null}
                    className={`w-full py-2.5 px-4 rounded-lg font-semibold text-sm transition-colors duration-150 ${
                      isPopular
                        ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-md'
                        : 'bg-slate-900 text-white hover:bg-slate-800'
                    } disabled:opacity-50`}
                  >
                    {actionLoading === p.slug ? 'Activating...' : p.slug === 'free' ? 'Downgrade to Free' : 'Upgrade to ' + p.name}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

