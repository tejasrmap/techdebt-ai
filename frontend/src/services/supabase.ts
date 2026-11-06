import { createClient, type SupabaseClient } from '@supabase/supabase-js';

export const supabaseProjectId: string =
  import.meta.env.VITE_SUPABASE_PROJECT_ID || '';

export const supabaseUrl: string =
  import.meta.env.VITE_SUPABASE_URL || '';

export const supabasePublishableKey: string =
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ||
  import.meta.env.VITE_SUPABASE_ANON_KEY ||
  '';

export const isSupabaseConfigured = Boolean(supabaseUrl && supabasePublishableKey);

export const supabase: SupabaseClient | null = isSupabaseConfigured
  ? createClient(supabaseUrl, supabasePublishableKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
      },
    })
  : null;

