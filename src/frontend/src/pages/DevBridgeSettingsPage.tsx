import { Navigate } from 'react-router-dom'

/** Legacy route — settings live on DevBridge page. */
export function DevBridgeSettingsPage() {
  return <Navigate to="/admin/devbridge?tab=settings" replace />
}
