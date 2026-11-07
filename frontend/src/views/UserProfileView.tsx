import React, { useState, useEffect } from 'react';
import { apiClient } from '../services/api';
import { User } from '../types';

export const UserProfileView: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [fullName, setFullName] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  // MFA state
  const [mfaSecret, setMfaSecret] = useState<string | null>(null);
  const [otpauthUrl, setOtpauthUrl] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaEnabled, setMfaEnabled] = useState(false);

  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    setLoading(true);
    try {
      const u = await apiClient.getMe();
      setUser(u);
      setFullName(u.full_name || '');
      setMfaEnabled((u as any).mfa_enabled || false);
    } catch (err) {
      console.error('Failed to load profile:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    try {
      await apiClient.updateProfile({ full_name: fullName });
      setMessage({ text: 'Profile updated successfully!', type: 'success' });
      await loadProfile();
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Failed to update profile', type: 'error' });
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    if (newPassword !== confirmPassword) {
      setMessage({ text: 'New passwords do not match', type: 'error' });
      return;
    }
    try {
      await apiClient.changePassword({ current_password: currentPassword, new_password: newPassword });
      setMessage({ text: 'Password changed successfully!', type: 'success' });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Failed to change password', type: 'error' });
    }
  };

  const handleStartMFA = async () => {
    setMessage(null);
    try {
      const res = await apiClient.setupMFA();
      setMfaSecret(res.mfa_secret);
      setOtpauthUrl(res.otpauth_url);
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Failed to initiate MFA', type: 'error' });
    }
  };

  const handleVerifyMFA = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    try {
      await apiClient.verifyMFA(mfaCode);
      setMessage({ text: 'Two-Factor Authentication successfully activated!', type: 'success' });
      setMfaEnabled(true);
      setMfaSecret(null);
    } catch (err: any) {
      setMessage({ text: err.response?.data?.detail || 'Invalid verification code', type: 'error' });
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
    <div className="max-w-4xl mx-auto py-6 px-4 sm:px-6 lg:px-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Account & Security Settings</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Manage your identity, authentication credentials, and security keys.</p>
      </div>

      {message && (
        <div
          className={`p-4 rounded-lg text-sm font-medium ${
            message.type === 'success' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-rose-50 text-rose-800 border border-rose-200'
          }`}
        >
          {message.text}
        </div>
      )}

      {/* Profile Form */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h2 className="text-base font-bold text-slate-900 mb-4">Profile Information</h2>
        <form onSubmit={handleUpdateProfile} className="space-y-4 max-w-lg text-xs">
          <div>
            <label className="block font-semibold text-slate-700 mb-1">Email Address</label>
            <input
              type="email"
              disabled
              value={user?.email || ''}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg bg-slate-50 text-slate-500 font-mono"
            />
          </div>
          <div>
            <label className="block font-semibold text-slate-700 mb-1">Full Name</label>
            <input
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block font-semibold text-slate-700 mb-1">Organization & Role</label>
            <p className="text-sm text-slate-800 font-semibold">
              {user?.organization_name || 'Organization'} — <span className="text-indigo-600">{user?.role}</span>
            </p>
          </div>
          <button
            type="submit"
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg font-semibold hover:bg-indigo-700 transition"
          >
            Save Changes
          </button>
        </form>
      </div>

      {/* Password Change */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h2 className="text-base font-bold text-slate-900 mb-4">Change Password</h2>
        <form onSubmit={handleChangePassword} className="space-y-4 max-w-lg text-xs">
          <div>
            <label className="block font-semibold text-slate-700 mb-1">Current Password</label>
            <input
              type="password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block font-semibold text-slate-700 mb-1">New Password (min. 8 characters)</label>
            <input
              type="password"
              required
              minLength={8}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block font-semibold text-slate-700 mb-1">Confirm New Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 bg-slate-900 text-white rounded-lg font-semibold hover:bg-slate-800 transition"
          >
            Update Password
          </button>
        </form>
      </div>

      {/* MFA Security */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-900">Two-Factor Authentication (2FA / MFA)</h2>
            <p className="text-xs text-slate-500 mt-1">
              Add a layer of security using Google Authenticator, Authy, or standard TOTP app.
            </p>
          </div>
          <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
            mfaEnabled ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
          }`}>
            {mfaEnabled ? 'ENABLED' : 'DISABLED'}
          </span>
        </div>

        {!mfaEnabled && !mfaSecret && (
          <button
            onClick={handleStartMFA}
            className="px-4 py-2 border border-slate-300 text-slate-700 text-xs font-semibold rounded-lg hover:bg-slate-50"
          >
            Setup Two-Factor Authentication
          </button>
        )}

        {mfaSecret && (
          <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 space-y-4 text-xs">
            <p className="font-semibold text-slate-800">Scan or manually enter this secret in your Authenticator app:</p>
            <code className="p-2 bg-white rounded border border-slate-300 font-mono text-sm block select-all">
              {mfaSecret}
            </code>
            <form onSubmit={handleVerifyMFA} className="flex items-center gap-3">
              <input
                type="text"
                placeholder="6-digit code"
                maxLength={6}
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
                className="px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono w-36 text-center"
              />
              <button
                type="submit"
                className="px-4 py-2 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-700"
              >
                Verify & Activate
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};

