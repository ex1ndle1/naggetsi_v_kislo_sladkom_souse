import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { authAPI, type User } from '../api/client'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  refreshProfile: () => Promise<User | null>
}
const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const logout = () => {
    localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token'); localStorage.removeItem('user'); setUser(null)
  }
  const refreshProfile = useCallback(async () => {
    if (!localStorage.getItem('access_token')) return null
    try {
      const { data } = await authAPI.me()
      setUser(data); localStorage.setItem('user', JSON.stringify(data))
      return data
    } catch {
      localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token'); localStorage.removeItem('user')
      setUser(null); return null
    }
  }, [])
  useEffect(() => { refreshProfile().finally(() => setLoading(false)) }, [refreshProfile])
  useEffect(() => {
    const handler = () => { logout() }
    window.addEventListener('auth:logout', handler)
    return () => window.removeEventListener('auth:logout', handler)
  }, [])
  const login = async (email: string, password: string) => {
    const { data } = await authAPI.login(email, password)
    localStorage.setItem('access_token', data.access_token); localStorage.setItem('refresh_token', data.refresh_token)
    const profile = await refreshProfile()
    if (!profile) throw new Error('Unable to load the authenticated profile')
  }
  return <AuthContext.Provider value={{ user, loading, login, logout, refreshProfile }}>{children}</AuthContext.Provider>
}
export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within an AuthProvider')
  return value
}
