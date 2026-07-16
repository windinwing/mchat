/**
 * Build / dev edition flag.
 * - core:  make dev, deploy-core  → app.main, no portal/templates in admin nav
 * - cloud: make cloud, deploy-cloud → cloud.main, full SaaS UI
 *
 * These build-time flags are the *default* for first paint. After the app boots,
 * the backend reports its actual runtime edition via /auth/bootstrap, and
 * {@link applyRuntimeEditionFlags} widens the effective flags (backend-on ⇒ on)
 * so a Core-built frontend still shows login/register UI when the server is
 * actually running Cloud. See LoginForm for the bootstrap wiring.
 */
export const isCloudEdition =
  import.meta.env.VITE_MCHAT_EDITION === 'cloud'

/** Phone / 9235 signup on Core builds (mchat.9235.net self-host). */
export const isSignupEnabled =
  isCloudEdition || import.meta.env.VITE_MCHAT_SIGNUP_ENABLED === 'true'

interface RuntimeEditionFlags {
  cloud?: boolean
  signup?: boolean
}

let runtimeFlags: RuntimeEditionFlags | null = null

/**
 * Apply edition flags reported by the backend at runtime. Flags only widen —
 * a build-time Cloud/on value is never turned off by the backend. This avoids
 * the common "deployed the wrong build" mistake where login/register vanish.
 */
export function applyRuntimeEditionFlags(flags: RuntimeEditionFlags): void {
  runtimeFlags = flags
}

/**
 * Effective edition flags: build-time OR runtime-reported. Use this anywhere
 * the login/register UI depends on edition so it reflects the live server.
 */
export function getEditionEffective(): { cloud: boolean; signup: boolean } {
  return {
    cloud: isCloudEdition || !!runtimeFlags?.cloud,
    signup: isSignupEnabled || !!runtimeFlags?.signup,
  }
}
