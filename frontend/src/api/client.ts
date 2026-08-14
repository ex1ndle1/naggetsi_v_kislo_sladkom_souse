import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Interceptor для добавления JWT токена
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Interceptor для обработки 401 и refresh токена
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      try {
        const refreshToken = localStorage.getItem('refresh_token')
        const response = await axios.post('/api/v1/auth/refresh', {
          refresh_token: refreshToken,
        })

        const { access_token, refresh_token } = response.data
        localStorage.setItem('access_token', access_token)
        localStorage.setItem('refresh_token', refresh_token)

        originalRequest.headers.Authorization = `Bearer ${access_token}`
        return api(originalRequest)
      } catch (refreshError) {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        window.location.href = '/login'
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default api

// API methods
export const authAPI = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }),

  register: (data: any) =>
    api.post('/auth/register', data),

  refresh: (refresh_token: string) =>
    api.post('/auth/refresh', { refresh_token }),
}

export const benefitsAPI = {
  list: (params?: any) =>
    api.get('/benefits', { params }),

  getById: (id: string) =>
    api.get(`/benefits/${id}`),

  create: (data: any) =>
    api.post('/benefits', data),

  update: (id: string, data: any) =>
    api.patch(`/benefits/${id}`, data),
}

export const applicationsAPI = {
  list: (params?: any) =>
    api.get('/applications', { params }),

  getById: (id: string) =>
    api.get(`/applications/${id}`),

  create: (benefit_id: string) =>
    api.post('/applications', { benefit_id }),

  updateStatus: (id: string, status: string, reason?: string) =>
    api.patch(`/applications/${id}/status`, { status, reason }),
}

export const paymentsAPI = {
  initiate: (application_id: string, provider: string = 'CLICK') =>
    api.post('/payments/initiate', { application_id, provider }),
}

export const aiAPI = {
  getRecommendations: () =>
    api.get('/ai/recommendations'),

  checkFraud: (application_id: string) =>
    api.post('/ai/fraud-check', { application_id }),

  getCompanyReport: () =>
    api.get('/ai/company-report'),
}

export const companiesAPI = {
  list: (params?: any) =>
    api.get('/companies', { params }),

  getById: (id: string) =>
    api.get(`/companies/${id}`),

  create: (data: any) =>
    api.post('/companies', data),

  update: (id: string, data: any) =>
    api.patch(`/companies/${id}`, data),

  delete: (id: string) =>
    api.delete(`/companies/${id}`),
}

export const merchantsAPI = {
  list: (params?: any) =>
    api.get('/merchants', { params }),

  getById: (id: string) =>
    api.get(`/merchants/${id}`),

  create: (data: any) =>
    api.post('/merchants', data),

  update: (id: string, data: any) =>
    api.patch(`/merchants/${id}`, data),

  delete: (id: string) =>
    api.delete(`/merchants/${id}`),
}

// SSE для real-time событий
export function subscribeToEvents(onMessage: (event: MessageEvent) => void) {
  const token = localStorage.getItem('access_token')
  if (!token) return null

  const eventSource = new EventSource(`/api/v1/events/stream`, {
    withCredentials: true,
  })

  eventSource.onmessage = onMessage
  eventSource.onerror = (error) => {
    console.error('SSE error:', error)
  }

  return eventSource
}
