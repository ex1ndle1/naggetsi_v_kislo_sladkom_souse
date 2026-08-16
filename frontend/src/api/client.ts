import type { AxiosResponse } from 'axios'
import axios from 'axios'

export type Role = 'EMPLOYEE' | 'COMPANY_ADMIN' | 'MERCHANT' | 'PLATFORM_ADMIN'
export type Plan = 'STANDARD' | 'PLUS' | 'PRO'
export type BenefitCategory = 'SPORT' | 'EDUCATION' | 'HEALTH' | 'FOOD' | 'TRANSPORT' | 'ENTERTAINMENT' | 'TECH' | 'OTHER'
export type PromoStatus = 'ISSUED' | 'REDEEMED' | 'EXPIRED' | 'REVOKED'
export type RedemptionStatus = 'ISSUED' | 'REDEEMED' | 'EXPIRED' | 'CANCELLED'

export interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  role: Role
  plan: Plan | null
  is_active: boolean
  company_id: string | null
  merchant_id: string | null
  created_at: string
  updated_at: string
}

export interface Page<T> {
  items: T[]
  meta: { page: number; page_size: number; total: number; pages: number }
}

export interface PlanOffer { plan: Plan; discount_percent: number; is_available: boolean }
export interface Benefit {
  id: string; title: string; description: string; category: BenefitCategory
  merchant_id: string; merchant_name?: string; destination_url: string | null
  valid_until: string | null; your_discount_percent?: number
  plan_offers: PlanOffer[]; already_redeemed?: boolean
  max_redemptions_per_employee?: number; promo_valid_days?: number; redemptions_left?: number
  is_active?: boolean; valid_from?: string | null; usage_limit?: number | null
  created_at?: string; updated_at?: string
}
export interface PromoCode {
  id: string; code: string; status: PromoStatus; issued_at: string; expires_at: string
  redeemed_at: string | null; benefit_id: string; benefit_title: string; merchant_name: string
  destination_url: string | null; discount_percent: number | null
}
export interface Redemption { id: string; status: RedemptionStatus; created_at: string; redeemed_at: string | null; benefit_id: string; benefit_title: string; benefit_category: BenefitCategory; merchant_name: string; promo_code: string | null; promo_status: PromoStatus | null; promo_expires_at: string | null }
export interface Seat { plan: Plan; allocated: number; assigned: number; available: number; utilization_percent: number }
export interface CompanyOverview { id: string; name: string; status: string; seats: { plans: Seat[]; total_allocated: number; total_assigned: number; total_available: number }; active_employees: number; created_at: string }
export interface Employee { id: string; email: string; first_name: string; last_name: string; plan: Plan | null; is_active: boolean; redemptions: number; last_activity: string | null; created_at: string }
export interface Invite { id: string; plan: Plan; email: string | null; status: string; expires_at: string; used_at: string | null; created_at: string }
export interface Analytics { [key: string]: unknown }
export interface RankedRow { label: string; value: number }
export interface TrendPoint { day: string; count: number }

const api = axios.create({ baseURL: '/api/v1', headers: { 'Content-Type': 'application/json' } })
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
let refreshing: Promise<string> | null = null
api.interceptors.response.use((response) => response, async (error) => {
  const original = error.config
  if (error.response?.status !== 401 || original?._retry || original?.url?.includes('/auth/')) return Promise.reject(error)
  original._retry = true
  try {
    refreshing ??= api.post<{ access_token: string; refresh_token: string }>('/auth/refresh', { refresh_token: localStorage.getItem('refresh_token') }).then(({ data }) => {
      localStorage.setItem('access_token', data.access_token); localStorage.setItem('refresh_token', data.refresh_token); return data.access_token
    }).finally(() => { refreshing = null })
    const token = await refreshing
    original.headers.Authorization = `Bearer ${token}`
    return api(original)
  } catch (refreshError) {
    localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token'); localStorage.removeItem('user')
    window.dispatchEvent(new Event('auth:logout'))
    return Promise.reject(refreshError)
  }
})

const unwrap = <T>(request: Promise<AxiosResponse<T>>) => request
export const authAPI = {
  login: (email: string, password: string) => api.post<{ access_token: string; refresh_token: string }>('/auth/login', { email, password }),
  me: () => api.get<User>('/me'),
}
export const benefitsAPI = {
  list: (params?: { page?: number; page_size?: number; category?: BenefitCategory }) => unwrap(api.get<Page<Benefit>>('/benefits', { params })),
  detail: (id: string) => api.get<Benefit>(`/benefits/${id}`),
  redeem: (id: string) => api.post<{ redemption_id: string; promo_code: string; expires_at: string; status: RedemptionStatus; message: string }>(`/benefits/${id}/redeem`),
}
export const meAPI = {
  promoCodes: (params?: { page?: number; page_size?: number; status?: PromoStatus }) => api.get<Page<PromoCode>>('/me/promo-codes', { params }),
  redemptions: (params?: { page?: number; page_size?: number }) => api.get<Page<Redemption>>('/me/redemptions', { params }),
}
export const companyAPI = {
  overview: () => api.get<CompanyOverview>('/company'),
  employees: (params?: { page?: number; page_size?: number; plan?: Plan; is_active?: boolean }) => api.get<Page<Employee>>('/company/employees', { params }),
  invites: (params?: { page?: number; page_size?: number; status?: string }) => api.get<Page<Invite>>('/company/invites', { params }),
  createInvite: (data: { plan: Plan; email?: string; expires_in_days?: number }) => api.post<{ token: string; plan: Plan; email: string | null; expires_at: string }>('/company/invites', data),
  changePlan: (id: string, plan: Plan) => api.post<Employee>(`/company/employees/${id}/plan`, { plan }),
  toggleEmployee: (id: string, active: boolean) => api.post<Employee>(`/company/employees/${id}/${active ? 'activate' : 'deactivate'}`),
  analytics: () => api.get<Analytics>('/company/analytics'),
  syncBitrix: (webhookUrl: string) => api.post<{
    company_id: string
    webhook_url: string
    total_fetched: number
    created: number
    updated: number
  }>('/companies/bitrix/sync', { webhook_url: webhookUrl }),
}
export const merchantAPI = {
  benefits: (params?: { merchant_id?: string }) => api.get<Benefit[]>('/merchant/benefits', { params }),
  createBenefit: (data: Record<string, unknown>) => api.post<Benefit>('/merchant/benefits', data),
  updateBenefit: (id: string, data: Record<string, unknown>) => api.patch<Benefit>(`/merchant/benefits/${id}`, data),
  analytics: () => api.get<Analytics>('/merchant/analytics'),
  lookupPromo: (code: string) => api.get(`/merchant/promo-codes/${encodeURIComponent(code)}`),
  redeemPromo: (code: string) => api.post(`/merchant/promo-codes/${encodeURIComponent(code)}/redeem`),
}
export const adminAPI = {
  users: (params?: { page?: number; page_size?: number }) => api.get<Page<User>>('/admin/users', { params }),
  benefits: (params?: { page?: number; page_size?: number }) => api.get<Page<Benefit>>('/admin/benefits', { params }),
  redemptions: (params?: { page?: number; page_size?: number }) => api.get('/admin/redemptions', { params }),
  auditLogs: (params?: { page?: number; page_size?: number }) => api.get('/admin/audit-logs', { params }),
  setUserActive: (id: string, active: boolean) => api.patch<User>(`/admin/users/${id}/${active ? 'unblock' : 'block'}`),
}
export const aiAPI = {
  concierge: (query: string) => api.post<{ benefits: Benefit[]; reasoning: string | null; ai_used: boolean }>('/ai/concierge', { query }),
  merchantDraft: (hint: string) => api.post('/ai/merchant/generate-offer', { hint }),
  companyReport: (companyId?: string) => api.get<{ metrics: Analytics; insights: string | null; ai_used: boolean }>('/ai/company-report', { params: companyId ? { company_id: companyId } : undefined }),
}
export async function issueEventTicket() { return (await api.post<{ ticket: string; expires_in_seconds: number }>('/events/ticket')).data }
export async function subscribeToEvents(onEvent: (event: MessageEvent) => void, onError?: () => void) {
  const { ticket } = await issueEventTicket()
  const source = new EventSource(`/api/v1/events/stream?ticket=${encodeURIComponent(ticket)}`)
  source.onmessage = onEvent; source.onerror = () => onError?.()
  return source
}
export default api
