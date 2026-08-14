import { useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { benefitsAPI } from '../api/client'

interface Benefit {
  id: string
  title: string
  description: string
  category: string
  price: number
  discount_price: number | null
  currency: string
  is_active: boolean
  created_at: string
}

export default function MerchantDashboard() {
  const { user, logout } = useAuth()
  const [benefits, setBenefits] = useState<Benefit[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    category: 'SPORT',
    price: '',
    discount_price: '',
  })

  useEffect(() => {
    loadBenefits()
  }, [])

  const loadBenefits = async () => {
    try {
      const response = await benefitsAPI.list({ page: 1, page_size: 50 })
      setBenefits(response.data.items || [])
    } catch (error) {
      console.error('Failed to load benefits:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await benefitsAPI.create({
        title: formData.title,
        description: formData.description,
        category: formData.category,
        price: parseFloat(formData.price),
        discount_price: formData.discount_price ? parseFloat(formData.discount_price) : null,
        currency: 'UZS',
        allow_repeat: true,
      })
      alert('Benefit created successfully!')
      setShowCreateForm(false)
      setFormData({ title: '', description: '', category: 'SPORT', price: '', discount_price: '' })
      loadBenefits()
    } catch (error: any) {
      alert(`Failed to create: ${error.response?.data?.error?.message || 'Unknown error'}`)
    }
  }

  const handleToggleActive = async (benefitId: string, currentActive: boolean) => {
    try {
      await benefitsAPI.update(benefitId, { is_active: !currentActive })
      loadBenefits()
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
          <h1>Merchant Dashboard</h1>
          <p>Welcome, {user?.first_name} {user?.last_name}</p>
        </div>
        <button onClick={logout} style={{ height: 'fit-content' }}>
          Logout
        </button>
      </header>

      <section style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2>My Benefits</h2>
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            style={{ background: '#007bff', color: 'white', border: 'none', padding: '0.5rem 1rem', borderRadius: '4px', cursor: 'pointer' }}
          >
            {showCreateForm ? 'Cancel' : 'Create New Benefit'}
          </button>
        </div>

        {showCreateForm && (
          <form
            onSubmit={handleCreate}
            style={{ border: '1px solid #ddd', borderRadius: '8px', padding: '1.5rem', marginBottom: '2rem', background: '#f8f9fa' }}
          >
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>Title</label>
              <input
                type="text"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                required
                style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
              />
            </div>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>Description</label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                required
                rows={3}
                style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>Category</label>
                <select
                  value={formData.category}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                >
                  <option value="SPORT">Sport</option>
                  <option value="EDUCATION">Education</option>
                  <option value="HEALTH">Health</option>
                  <option value="FOOD">Food</option>
                  <option value="TRANSPORT">Transport</option>
                  <option value="ENTERTAINMENT">Entertainment</option>
                  <option value="TECH">Tech</option>
                  <option value="OTHER">Other</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>Price (UZS)</label>
                <input
                  type="number"
                  value={formData.price}
                  onChange={(e) => setFormData({ ...formData, price: e.target.value })}
                  required
                  min="0"
                  step="0.01"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 'bold' }}>Discount Price</label>
                <input
                  type="number"
                  value={formData.discount_price}
                  onChange={(e) => setFormData({ ...formData, discount_price: e.target.value })}
                  min="0"
                  step="0.01"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid #ddd', borderRadius: '4px' }}
                />
              </div>
            </div>
            <button
              type="submit"
              style={{ background: '#28a745', color: 'white', border: 'none', padding: '0.5rem 1rem', borderRadius: '4px', cursor: 'pointer' }}
            >
              Create Benefit
            </button>
          </form>
        )}

        {benefits.length === 0 ? (
          <p>No benefits created yet</p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
            {benefits.map((benefit) => (
              <div
                key={benefit.id}
                style={{
                  border: '1px solid #ddd',
                  borderRadius: '8px',
                  padding: '1rem',
                  background: benefit.is_active ? 'white' : '#f8f9fa',
                  opacity: benefit.is_active ? 1 : 0.7,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '0.5rem' }}>
                  <h3 style={{ margin: 0 }}>{benefit.title}</h3>
                  <span
                    style={{
                      padding: '0.25rem 0.5rem',
                      borderRadius: '4px',
                      background: benefit.is_active ? '#d4edda' : '#f8d7da',
                      fontSize: '0.75rem',
                    }}
                  >
                    {benefit.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
                <p style={{ fontSize: '0.875rem', color: '#666', margin: '0 0 0.5rem 0' }}>
                  {benefit.description.slice(0, 100)}...
                </p>
                <p style={{ fontSize: '0.75rem', color: '#999', margin: '0 0 1rem 0' }}>
                  Category: {benefit.category}
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
                  <button
                    onClick={() => handleToggleActive(benefit.id, benefit.is_active)}
                    style={{
                      background: benefit.is_active ? '#ffc107' : '#28a745',
                      color: 'white',
                      border: 'none',
                      padding: '0.25rem 0.5rem',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                    }}
                  >
                    {benefit.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
