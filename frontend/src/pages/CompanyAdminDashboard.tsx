import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { applicationsAPI, aiAPI } from '../api/client'

interface Application {
  id: string
  status: string
  price: number
  currency: string
  created_at: string
  employee_id: string
}

export default function CompanyAdminDashboard() {
  const { user, logout } = useAuth()
  const [applications, setApplications] = useState<Application[]>([])
  const [stats, setStats] = useState({ pending: 0, approved: 0, total_spent: 0 })
  const [report, setReport] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const [applicationsRes, reportRes] = await Promise.all([
        applicationsAPI.list({ page: 1, page_size: 50 }),
        aiAPI.getCompanyReport().catch(() => ({ data: { report: 'Report unavailable' } })),
      ])

      const apps = applicationsRes.data.items || []
      setApplications(apps)

      const pending = apps.filter((a: Application) => a.status === 'PENDING_PAYMENT').length
      const approved = apps.filter((a: Application) => a.status === 'APPROVED' || a.status === 'PAID').length
      const total_spent = apps
        .filter((a: Application) => a.status === 'PAID')
        .reduce((sum: number, a: Application) => sum + a.price, 0)

      setStats({ pending, approved, total_spent })
      setReport(reportRes.data.report || '')
    } catch (error) {
      console.error('Failed to load dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleUpdateStatus = async (appId: string, newStatus: string) => {
    try {
      await applicationsAPI.updateStatus(appId, newStatus)
      alert('Status updated successfully!')
      loadData()
    } catch (error: any) {
      alert(`Failed to update: ${error.response?.data?.error?.message || 'Unknown error'}`)
    }
  }

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <p>Loading...</p>
      </div>
    )
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2rem' }}>
        <div>
          <h1>Company Admin Dashboard</h1>
          <p>Welcome, {user?.first_name} {user?.last_name}</p>
        </div>
        <button onClick={logout} style={{ height: 'fit-content' }}>
          Logout
        </button>
      </header>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
        <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '1.5rem', textAlign: 'center' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#666' }}>Pending Applications</h3>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0 }}>{stats.pending}</p>
        </div>
        <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '1.5rem', textAlign: 'center' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#666' }}>Approved</h3>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0 }}>{stats.approved}</p>
        </div>
        <div style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '1.5rem', textAlign: 'center' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#666' }}>Total Spent</h3>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0 }}>
            {stats.total_spent.toLocaleString()} UZS
          </p>
        </div>
      </section>

      {report && (
        <section style={{ marginBottom: '2rem', padding: '1rem', background: '#f8f9fa', borderRadius: '8px' }}>
          <h2>Company Report</h2>
          <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', margin: 0 }}>{report}</pre>
        </section>
      )}

      <section>
        <h2>Employee Applications</h2>
        {applications.length === 0 ? (
          <p>No applications</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #ddd' }}>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Status</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Price</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Date</th>
                <th style={{ textAlign: 'right', padding: '0.5rem' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {applications.map((app) => (
                <tr key={app.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '0.5rem' }}>
                    <span
                      style={{
                        padding: '0.25rem 0.5rem',
                        borderRadius: '4px',
                        background:
                          app.status === 'PAID'
                            ? '#d4edda'
                            : app.status === 'APPROVED'
                            ? '#d1ecf1'
                            : app.status === 'PENDING_PAYMENT'
                            ? '#fff3cd'
                            : '#f8d7da',
                        fontSize: '0.875rem',
                      }}
                    >
                      {app.status}
                    </span>
                  </td>
                  <td style={{ padding: '0.5rem' }}>
                    {app.price} {app.currency}
                  </td>
                  <td style={{ padding: '0.5rem' }}>
                    {new Date(app.created_at).toLocaleDateString()}
                  </td>
                  <td style={{ padding: '0.5rem', textAlign: 'right' }}>
                    {app.status === 'PENDING_PAYMENT' && (
                      <>
                        <button
                          onClick={() => handleUpdateStatus(app.id, 'APPROVED')}
                          style={{ marginRight: '0.5rem', background: '#28a745', color: 'white', border: 'none', padding: '0.25rem 0.5rem', borderRadius: '4px', cursor: 'pointer' }}
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => handleUpdateStatus(app.id, 'REJECTED')}
                          style={{ background: '#dc3545', color: 'white', border: 'none', padding: '0.25rem 0.5rem', borderRadius: '4px', cursor: 'pointer' }}
                        >
                          Reject
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
