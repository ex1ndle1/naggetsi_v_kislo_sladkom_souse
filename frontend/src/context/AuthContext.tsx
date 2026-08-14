import React, { createContext, useContext, useState, useEffect } from 'react'
import { authAPI } from '../api/client'

interface User {
  id: string
  email: string
  role: 'EMPLOYEE' | 'COMPANY_ADMIN' | 'MERCHANT' | 'PLATFORM_ADMIN'
  first_name: string
  last_name: string
  company_id?: string
  merchant_id?: string
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Загружаем пользователя из localStorage при инициализации
    const storedUser = localStorage.getItem('user')
    if (storedUser) {
      setUser(JSON.parse(storedUser))
    }
    setLoading(false)
  }, [])

  const login = async (email: string, password: string) => {
    const response = await authAPI.login(email, password)
    const { access_token, refresh_token } = response.data

    localStorage.setItem('access_token', access_token)
    localStorage.setItem('refresh_token', refresh_token)

    // Декодируем JWT чтобы получить user info (в production лучше отдельный /me endpoint)
    const payload = JSON.parse(atob(access_token.split('.')[1]))
    const userData: User = {
      id: payload.sub,
      email,
      role: payload.role || 'EMPLOYEE',
      first_name: payload.first_name || '',
      last_name: payload.last_name || '',
      company_id: payload.company_id,
      merchant_id: payload.merchant_id,
    }

    setUser(userData)
    localStorage.setItem('user', JSON.stringify(userData))
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
