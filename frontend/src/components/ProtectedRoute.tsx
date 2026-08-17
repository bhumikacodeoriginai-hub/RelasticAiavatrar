/**
 * Protected Route Component.
 * Redirects to /login if user is not authenticated.
 * Optionally checks for specific roles.
 */

import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

interface ProtectedRouteProps {
  children: React.ReactNode
  requiredRoles?: string[]
}

export default function ProtectedRoute({ children, requiredRoles }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, role } = useAuth()
  const location = useLocation()

  // Show nothing while checking auth state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="text-gray-400 text-sm">Loading...</div>
      </div>
    )
  }

  // Not authenticated — redirect to login
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // Check role requirements
  if (requiredRoles && requiredRoles.length > 0 && role) {
    if (!requiredRoles.includes(role)) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-900">
          <div className="glass-panel p-8 text-center max-w-md">
            <h2 className="text-xl font-bold text-red-400 mb-2">Access Denied</h2>
            <p className="text-gray-400 text-sm">
              You do not have permission to access this page.
              Required role: {requiredRoles.join(' or ')}
            </p>
          </div>
        </div>
      )
    }
  }

  return <>{children}</>
}
