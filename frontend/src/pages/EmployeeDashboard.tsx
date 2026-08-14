import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { benefitsAPI, applicationsAPI, aiAPI } from '../api/client'

interface Benefit {
  id: string
  title: string
  description: string
  category: string
  price: number
  discount_price: number | null
  currency: string
}

interface Application {
  id: string
  status: string
  price: number
  currency: string
  created_at: string
  benefit_id: string
}

export default function EmployeeDashboard() {
  const { user, logout } = useAuth()
  const [benefits, setBenefits] = useState<Benefit[]>([])
  const [applications, setApplications] = useState<Application[]>([])
  const [recommendations, setRecommendations] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const [benefitsRes, applicationsRes, recommendationsRes] = await Promise.all([
        benefitsAPI.list({ page: 1, page_size: 20 }),
        applicationsAPI.list({ page: 1, page_size: 10 }),
        aiAPI.getRecommendations().catch(() => ({ data: { recommended: [] } })),
      ])

      setBenefits(benefitsRes.data.items || [])
      setApplications(applicationsRes.data.items || [])
      setRecommendations(recommendationsRes.data.recommended || [])
    } catch (error) {
      console.error('Failed to load dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleApply = async (benefitId: string) => {
    try {
      await applicationsAPI.create(benefitId)
      alert('Application submitted successfully!')
      loadData()
    } catch (error: any) {
      alert(`Failed to apply: ${error.response?.data?.error?.message || 'Unknown error'}`)
    }
  }

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <p>Loading...</p>
      </div>
    )
  }

  const recommendedBenefits = benefits.filter((b) => recommendations.includes(b.id))

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2rem' }}>
        <div>
          <h1>Employee Dashboard</h1>
          <p>Welcome, {user?.first_name} {user?.last_name}</p>
        </div>
        <button onClick={logout} style={{ height: 'fit-content' }}>
          Logout
        </button>
      </header>

      <section style={{ marginBottom: '3rem' }}>
        <h2>My Applications</h2>
        {applications.length === 0 ? (
          <p>No applications yet</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #ddd' }}>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Status</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Price</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Date</th>
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
                        background: app.status === 'PAID' ? '#d4edda' : '#f8d7da',
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
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {recommendedBenefits.length > 0 && (
        <section style={{ marginBottom: '3rem' }}>
          <h2>Recommended for You</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
            {recommendedBenefits.map((benefit) => (
              <div
                key={benefit.id}
                style={{
                  border: '1px solid #ddd',
                  borderRadius: '8px',
                  padding: '1rem',
                  background: '#fffbea',
                }}
              >
                <h3 style={{ margin: '0 0 0.5rem 0' }}>{benefit.title}</h3>
                <p style={{ fontSize: '0.875rem', color: '#666', margin: '0 0 1rem 0' }}>
                  {benefit.description.slice(0, 100)}...
                </p>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: 'bold' }}>
                    {benefit.discount_price || benefit.price} {benefit.currency}
                  </span>
                  <button onClick={() => handleApply(benefit.id)}>Apply</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2>All Benefits</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
          {benefits.map((benefit) => (
            <div
              key={benefit.id}
              style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '1rem' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '0.5rem' }}>
                <h3 style={{ margin: 0 }}>{benefit.title}</h3>
                <span
                  style={{
                    padding: '0.25rem 0.5rem',
                    borderRadius: '4px',
                    background: '#e3f2fd',
                    fontSize: '0.75rem',
                  }}
                >
                  {benefit.category}
                </span>
              </div>
              <p style={{ fontSize: '0.875rem', color: '#666', margin: '0 0 1rem 0' }}>
                {benefit.description.slice(0, 120)}...
              </p>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  {benefit.discount_price && (
                    <span style={{ textDecoration: 'line-through', color: '#999', marginRight: '0.5rem' }}>
                      {benefit.price}
                    </span>
                  )}
                  <span style={{ fontWeight: 'bold' }}>
                    {benefit.discount_price || benefit.price} {benefit.currency}
                  </span>
                </div>
                <button onClick={() => handleApply(benefit.id)}>Apply</button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
