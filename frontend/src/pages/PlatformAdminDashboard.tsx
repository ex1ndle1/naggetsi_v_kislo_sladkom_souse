import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { companiesAPI, merchantsAPI, benefitsAPI, applicationsAPI } from '../api/client'

interface Company {
  id: string
  name: string
  status: string
  created_at: string
}

interface Merchant {
  id: string
  name: string
  email: string
  status: string
  created_at: string
}

type Tab = 'overview' | 'companies' | 'merchants'

export default function PlatformAdminDashboard() {
  const { user, logout } = useAuth()
  const [tab, setTab] = useState<Tab>('overview')
  const [companies, setCompanies] = useState<Company[]>([])
  const [merchants, setMerchants] = useState<Merchant[]>([])
  const [counts, setCounts] = useState({ companies: 0, merchants: 0, benefits: 0, applications: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [companiesRes, merchantsRes, benefitsRes, applicationsRes] = await Promise.all([
        companiesAPI.list({ page: 1, page_size: 50 }),
        merchantsAPI.list({ page: 1, page_size: 50 }),
        benefitsAPI.list({ page: 1, page_size: 1 }),
        applicationsAPI.list({ page: 1, page_size: 1 }),
      ])

      setCompanies(companiesRes.data.items || [])
      setMerchants(merchantsRes.data.items || [])
      setCounts({
        companies: companiesRes.data.total ?? 0,
        merchants: merchantsRes.data.total ?? 0,
        benefits: benefitsRes.data.total ?? 0,
        applications: applicationsRes.data.total ?? 0,
      })
      setError(null)
    } catch (err: any) {
      setError(err.response?.data?.error?.message || 'Не удалось загрузить данные')
    } finally {
      setLoading(false)
    }
  }

  const handleToggleMerchant = async (id: string, currentStatus: string) => {
    const nextStatus = currentStatus === 'BLOCKED' ? 'ACTIVE' : 'BLOCKED'
    try {
      await merchantsAPI.update(id, { status: nextStatus })
      loadData()
    } catch (err: any) {
      alert(`Не удалось обновить мерчанта: ${err.response?.data?.error?.message || 'ошибка'}`)
    }
  }

  const handleToggleCompany = async (id: string, currentStatus: string) => {
    const nextStatus = currentStatus === 'SUSPENDED' ? 'ACTIVE' : 'SUSPENDED'
    try {
      await companiesAPI.update(id, { status: nextStatus })
      loadData()
    } catch (err: any) {
      alert(`Не удалось обновить компанию: ${err.response?.data?.error?.message || 'ошибка'}`)
    }
  }

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <p>Loading...</p>
      </div>
    )
  }

  const tabStyle = (active: boolean) => ({
    padding: '0.5rem 1rem',
    border: 'none',
    borderBottom: active ? '2px solid #007bff' : '2px solid transparent',
    background: 'none',
    cursor: 'pointer',
    fontWeight: active ? ('bold' as const) : ('normal' as const),
  })

  const badge = (text: string, ok: boolean) => (
    <span
      style={{
        padding: '0.25rem 0.5rem',
        borderRadius: '4px',
        background: ok ? '#d4edda' : '#f8d7da',
        fontSize: '0.875rem',
      }}
    >
      {text}
    </span>
  )

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2rem' }}>
        <div>
          <h1>Platform Admin Dashboard</h1>
          <p>
            Welcome, {user?.first_name} {user?.last_name}
          </p>
        </div>
        <button onClick={logout} style={{ height: 'fit-content' }}>
          Logout
        </button>
      </header>

      {error && (
        <div style={{ padding: '0.75rem', marginBottom: '1rem', background: '#f8d7da', borderRadius: '4px' }}>
          {error}
        </div>
      )}

      <nav style={{ display: 'flex', gap: '0.5rem', borderBottom: '1px solid #ddd', marginBottom: '1.5rem' }}>
        <button style={tabStyle(tab === 'overview')} onClick={() => setTab('overview')}>
          Overview
        </button>
        <button style={tabStyle(tab === 'companies')} onClick={() => setTab('companies')}>
          Companies ({counts.companies})
        </button>
        <button style={tabStyle(tab === 'merchants')} onClick={() => setTab('merchants')}>
          Merchants ({counts.merchants})
        </button>
      </nav>

      {tab === 'overview' && (
        <section
          style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem' }}
        >
          {[
            { label: 'Companies', value: counts.companies },
            { label: 'Merchants', value: counts.merchants },
            { label: 'Benefits', value: counts.benefits },
            { label: 'Applications', value: counts.applications },
          ].map((card) => (
            <div
              key={card.label}
              style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '1.5rem', textAlign: 'center' }}
            >
              <h3 style={{ margin: '0 0 0.5rem 0', color: '#666' }}>{card.label}</h3>
              <p style={{ fontSize: '2rem', fontWeight: 'bold', margin: 0 }}>{card.value}</p>
            </div>
          ))}
        </section>
      )}

      {tab === 'companies' && (
        <section>
          {companies.length === 0 ? (
            <p>No companies</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #ddd' }}>
                  <th style={{ textAlign: 'left', padding: '0.5rem' }}>Name</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem' }}>Status</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem' }}>Created</th>
                  <th style={{ textAlign: 'right', padding: '0.5rem' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {companies.map((c) => (
                  <tr key={c.id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '0.5rem' }}>{c.name}</td>
                    <td style={{ padding: '0.5rem' }}>{badge(c.status, c.status === 'ACTIVE')}</td>
                    <td style={{ padding: '0.5rem' }}>{new Date(c.created_at).toLocaleDateString()}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right' }}>
                      <button
                        onClick={() => handleToggleCompany(c.id, c.status)}
                        style={{
                          background: c.status === 'ACTIVE' ? '#ffc107' : '#28a745',
                          color: 'white',
                          border: 'none',
                          padding: '0.25rem 0.5rem',
                          borderRadius: '4px',
                          cursor: 'pointer',
                        }}
                      >
                        {c.status === 'ACTIVE' ? 'Suspend' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {tab === 'merchants' && (
        <section>
          {merchants.length === 0 ? (
            <p>No merchants</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #ddd' }}>
                  <th style={{ textAlign: 'left', padding: '0.5rem' }}>Name</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem' }}>Email</th>
                  <th style={{ textAlign: 'left', padding: '0.5rem' }}>Status</th>
                  <th style={{ textAlign: 'right', padding: '0.5rem' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {merchants.map((m) => (
                  <tr key={m.id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '0.5rem' }}>{m.name}</td>
                    <td style={{ padding: '0.5rem' }}>{m.email}</td>
                    <td style={{ padding: '0.5rem' }}>{badge(m.status, m.status === 'ACTIVE')}</td>
                    <td style={{ padding: '0.5rem', textAlign: 'right' }}>
                      <button
                        onClick={() => handleToggleMerchant(m.id, m.status)}
                        style={{
                          background: m.status === 'BLOCKED' ? '#28a745' : '#ffc107',
                          color: 'white',
                          border: 'none',
                          padding: '0.25rem 0.5rem',
                          borderRadius: '4px',
                          cursor: 'pointer',
                        }}
                      >
                        {m.status === 'BLOCKED' ? 'Unblock' : 'Block'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  )
}
