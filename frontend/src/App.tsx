import type { ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import Landing from './pages/Landing'
import Login from './pages/Login'
import EmployeeDashboard from './pages/EmployeeDashboard'
import CompanyAdminDashboard from './pages/CompanyAdminDashboard'
import MerchantDashboard from './pages/MerchantDashboard'
import PlatformAdminDashboard from './pages/PlatformAdminDashboard'

function PrivateRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return null
  return user ? <>{children}</> : <Navigate to="/login" />
}

function DashboardRouter() {
  const { user } = useAuth()

  if (!user) return <Navigate to="/login" />

  switch (user.role) {
    case 'EMPLOYEE':
      return <EmployeeDashboard />
    case 'COMPANY_ADMIN':
      return <CompanyAdminDashboard />
    case 'MERCHANT':
      return <MerchantDashboard />
    case 'PLATFORM_ADMIN':
      return <PlatformAdminDashboard />
    default:
      return <div>Unknown role</div>
  }
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/dashboard"
            element={
              <PrivateRoute>
                <DashboardRouter />
              </PrivateRoute>
            }
          />
          <Route path="/" element={<Landing />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
