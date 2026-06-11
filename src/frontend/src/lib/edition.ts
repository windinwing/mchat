/**
 * Build / dev edition flag.
 * - core:  make dev, deploy-core  → app.main, no portal/templates in admin nav
 * - cloud: make cloud, deploy-cloud → cloud.main, full SaaS UI
 */
export const isCloudEdition =
  import.meta.env.VITE_MCHAT_EDITION === 'cloud'

/** Phone / 9235 signup on Core builds (mchat.9235.net self-host). */
export const isSignupEnabled =
  isCloudEdition || import.meta.env.VITE_MCHAT_SIGNUP_ENABLED === 'true'
