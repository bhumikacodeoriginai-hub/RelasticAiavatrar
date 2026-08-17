/**
 * Authentication Context Provider.
 * Manages auth state, token lifecycle, and permission checks.
 *
 * SECURITY:
 * - Token stored in memory only (cleared on page reload).
 * - Automatic logout on 401 responses.
 * - Session timeout warning before expiry.
 * - No sensitive data in localStorage/sessionStorage.
 */

import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react'
import { authApi, setAccessToken, clearAccessToken, setOnUnauthorized, LoginResponse, UserInfo } from '../lib/api'

interface AuthState {
  isAuthenticated: boolean
  isLoading: boolean
  user: UserInfo | null
  role: string | null
  error: string | null
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  hasPermission: (permission: string) => boolean
  isRole: (...roles: string[]) => boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true, // Start loading to check existing token
    user: null,
    role: null,
    error: null,
  })

  // Handle unauthorized responses (401 from API client)
  const handleUnauthorized = useCallback(() => {
    setState({
      isAuthenticated: false,
      isLoading: false,
      user: null,
      role: null,
      error: 'Session expired. Please log in again.',
    })
  }, [])

  // Register the unauthorized callback with the API client
  useEffect(() => {
    setOnUnauthorized(handleUnauthorized)
  }, [handleUnauthorized])

  // On mount, check if we have a valid session (we won't after reload since token is in-memory)
  useEffect(() => {
    setState(prev => ({ ...prev, isLoading: false }))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    setState(prev => ({ ...prev, isLoading: true, error: null }))

    try {
      const response: LoginResponse = await authApi.login(username, password)

      // Store token in memory
      setAccessToken(response.access_token)

      // Fetch full user info
      const userInfo = await authApi.me()

      setState({
        isAuthenticated: true,
        isLoading: false,
        user: userInfo,
        role: response.role,
        error: null,
      })
    } catch (err: unknown) {
      clearAccessToken()
      const message = err instanceof Error ? err.message : 'Login failed'
      setState({
        isAuthenticated: false,
        isLoading: false,
        user: null,
        role: null,
        error: message,
      })
      throw err
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      // Ignore errors during logout — clear state regardless
    }
    clearAccessToken()
    setState({
      isAuthenticated: false,
      isLoading: false,
      user: null,
      role: null,
      error: null,
    })
  }, [])

  const hasPermission = useCallback((permission: string): boolean => {
    if (!state.user?.permissions) return false
    if (state.user.permissions['all']) return true
    return !!state.user.permissions[permission]
  }, [state.user])

  const isRole = useCallback((...roles: string[]): boolean => {
    if (!state.role) return false
    return roles.includes(state.role)
  }, [state.role])

  return (
    <AuthContext.Provider
      value={{
        ...state,
        login,
        logout,
        hasPermission,
        isRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
