import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string

/**
 * Frontend Supabase client — used purely as a session/token cache.
 *
 * Authentication still flows through our FastAPI backend (POST /api/auth/login),
 * but we hand the returned access_token + refresh_token to this client via
 * `setSession()` so it can:
 *   - Auto-refresh the access token before expiry (autoRefreshToken)
 *   - Be the single source of truth for the current bearer token in api.ts
 *   - Persist across page reloads (persistSession via localStorage)
 *   - Emit `TOKEN_REFRESHED` events so we can mirror the new tokens back into
 *     localStorage and our React state.
 */
export const supabase = createClient(url, anonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false,
  },
})
