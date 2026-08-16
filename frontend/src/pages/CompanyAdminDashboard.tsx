import { useEffect, useState, type FormEvent } from 'react'
import { aiAPI, companyAPI, type Analytics, type CompanyOverview, type Employee, type Invite, type Plan } from '../api/client'
import { useAuth } from '../context/AuthContext'

type Tab = 'overview' | 'employees' | 'invites' | 'report'
const plans: Plan[] = ['STANDARD', 'PLUS', 'PRO']

export default function CompanyAdminDashboard() {
  const { user, logout } = useAuth()
  const [tab, setTab] = useState<Tab>('overview')
  const [overview, setOverview] = useState<CompanyOverview | null>(null)
  const [employees, setEmployees] = useState<Employee[]>([])
  const [invites, setInvites] = useState<Invite[]>([])
  const [analytics, setAnalytics] = useState<Analytics>({})
  const [report, setReport] = useState<{ metrics: Analytics; insights: string | null; ai_used: boolean } | null>(null)
  const [loading, setLoading] = useState(true)
  const [inviteForm, setInviteForm] = useState({ plan: 'STANDARD' as Plan, email: '', expires_in_days: 7 })
  const [newToken, setNewToken] = useState('')

  // Bitrix24 sync state
  const [showBitrixForm, setShowBitrixForm] = useState(false)
  const [bitrixWebhook, setBitrixWebhook] = useState('')
  const [bitrixResult, setBitrixResult] = useState<string | null>(null)
  const [bitrixLoading, setBitrixLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [ov, emp, inv, an] = await Promise.all([
        companyAPI.overview(),
        companyAPI.employees({ page: 1, page_size: 100 }),
        companyAPI.invites({ page: 1, page_size: 50 }),
        companyAPI.analytics()
      ])
      setOverview(ov.data); setEmployees(emp.data.items); setInvites(inv.data.items); setAnalytics(an.data)
    } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])

  const createInvite = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const { data } = await companyAPI.createInvite({ plan: inviteForm.plan, email: inviteForm.email || undefined, expires_in_days: inviteForm.expires_in_days })
      setNewToken(data.token); await load()
    } catch (err: any) { alert(err.response?.data?.error?.message || 'Не удалось создать приглашение') }
  }

  const loadReport = async () => {
    if (report) return setTab('report')
    const { data } = await aiAPI.companyReport()
    setReport(data); setTab('report')
  }

  const syncBitrix = async (e: FormEvent) => {
    e.preventDefault()
    if (!bitrixWebhook.trim()) return

    setBitrixLoading(true)
    setBitrixResult(null)

    try {
      const { data } = await companyAPI.syncBitrix(bitrixWebhook.trim())
      setBitrixResult(
        `✅ Импорт завершён:\n• Получено из Bitrix24: ${data.total_fetched}\n• Создано новых: ${data.created}\n• Обновлено: ${data.updated}`
      )
      await load()
      setBitrixWebhook('')
    } catch (err: any) {
      setBitrixResult(`❌ Ошибка: ${err.response?.data?.error?.message || 'Не удалось выполнить синхронизацию'}`)
    } finally {
      setBitrixLoading(false)
    }
  }

  const ov = overview
  const seats = ov?.seats?.plans ?? []
  const topCategories = (analytics.top_categories as any[]) ?? []
  const topMerchants = (analytics.top_merchants as any[]) ?? []
  const topBenefits = (analytics.top_benefits as any[]) ?? []
  const promoIssued = (analytics.promo_codes_issued as number) ?? 0
  const promoRedeemed = (analytics.promo_codes_redeemed as number) ?? 0
  const promoRate = (analytics.redemption_rate_percent as number) ?? 0
  const redemptionsTotal = (analytics.redemptions_total as number) ?? 0
  const rateColor = promoRate >= 60 ? '#28734a' : promoRate >= 30 ? '#966b19' : '#a34444'
  const topEmployees = employees.slice().sort((a, b) => b.redemptions - a.redemptions).slice(0, 5)
  const planBreakdown = employees.reduce((acc, e) => {
    if (e.plan) acc[e.plan] = (acc[e.plan] || 0) + 1
    return acc
  }, {} as Record<Plan, number>)

  /** Горизонтальный бар-чарт. Ширина считается от максимума в наборе, а не от
   *  суммы: так виден относительный лидер, даже когда значения близки. */
  const RankedBars = ({ rows }: { rows: { label: string; value: number }[] }) => {
    const max = rows.reduce((m, r) => Math.max(m, r.value), 0) || 1
    return (
      <div style={{ display: 'grid', gap: '.75rem' }}>
        {rows.map((r) => (
          <div key={r.label} style={{ display: 'grid', gridTemplateColumns: '130px 1fr auto', alignItems: 'center', gap: '.75rem' }}>
            <span style={{ fontWeight: 650, fontSize: '.85rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.label}>{r.label}</span>
            <div style={{ height: 8, background: '#edf0f2', borderRadius: 99, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${(r.value / max) * 100}%`, background: 'var(--accent)' }} />
            </div>
            <span style={{ color: 'var(--muted)', fontSize: '.8rem', minWidth: 30, textAlign: 'right' }}>{r.value}</span>
          </div>
        ))}
      </div>
    )
  }

  const TabBtn = ({ id, label }: { id: Tab; label: string }) => (
    <button className={`tab ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
  )

  if (loading) return <main className="page"><p>Загрузка…</p></main>

  return (
    <main className="page">
      <header className="topbar">
        <div><p className="eyebrow">Кабинет администратора</p><h1>{ov?.name ?? 'Компания'}</h1><p>{user?.first_name} {user?.last_name}</p></div>
        <button className="button secondary" onClick={logout}>Выйти</button>
      </header>

      <section className="metrics">
        {[
          ['Всего мест', ov?.seats?.total_allocated ?? 0, ''],
          ['Занято', ov?.seats?.total_assigned ?? 0, ''],
          ['Сотрудников', ov?.active_employees ?? 0, ''],
          ['Погашений', redemptionsTotal, ''],
          ['Конверсия', promoRate, '%'],
        ].map(([l, v, s]) => (
          <div className="metric" key={String(l)}>
            <span>{String(l)}</span>
            <strong style={l === 'Конверсия' ? { color: rateColor } : {}}>{String(v)}{String(s)}</strong>
          </div>
        ))}
      </section>

      <nav className="tabs">
        <TabBtn id="overview" label="Обзор" /><TabBtn id="employees" label={`Сотрудники (${employees.length})`} /><TabBtn id="invites" label={`Приглашения (${invites.length})`} />
        <button className="tab" onClick={() => void loadReport()}>AI-отчёт</button>
      </nav>

      {tab === 'overview' && (
        <>
          <section className="panel" style={{ marginBottom: '1.5rem' }}>
            <h2 style={{ marginBottom: '1rem' }}>Распределение мест по тарифам</h2>
            {seats.map((s: any) => (
              <div className="seat-row" key={s.plan}>
                <span className="plan-label">{s.plan}</span>
                <div className="seat-bar"><div className="seat-fill" style={{ width: `${s.utilization_percent}%` }} /></div>
                <span className="seat-nums">{s.assigned}/{s.allocated} — {s.utilization_percent}%</span>
              </div>
            ))}
          </section>

          <div className="two-columns" style={{ marginBottom: '1.5rem' }}>
            <div className="panel">
              <p className="eyebrow">Активность по категориям</p>
              <h3 style={{ marginBottom: '1rem' }}>Топ погашений</h3>
              {topCategories.length > 0 ? (
                <RankedBars rows={topCategories.map((c: any) => ({ label: c.category, value: c.redemptions }))} />
              ) : <p className="muted">Нет данных</p>}
            </div>

            <div className="panel">
              <p className="eyebrow">Распределение сотрудников</p>
              <h3 style={{ marginBottom: '1rem' }}>По тарифам</h3>
              <div style={{ display: 'grid', gap: '.6rem' }}>
                {plans.map((plan) => {
                  const count = planBreakdown[plan] || 0
                  const pct = employees.length > 0 ? Math.round((count / employees.length) * 100) : 0
                  return (
                    <div key={plan} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '.5rem 0', borderBottom: '1px solid var(--line)' }}>
                      <span className="chip">{plan}</span>
                      <span style={{ fontSize: '.9rem' }}><strong>{count}</strong> <span className="muted">({pct}%)</span></span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          <div className="two-columns" style={{ marginBottom: '1.5rem' }}>
            <div className="panel">
              <p className="eyebrow">Партнёры</p>
              <h3 style={{ marginBottom: '1rem' }}>Топ мерчантов</h3>
              {topMerchants.length > 0 ? (
                <RankedBars rows={topMerchants.map((m: any) => ({ label: m.merchant, value: m.redemptions }))} />
              ) : <p className="muted">Нет данных</p>}
            </div>

            <div className="panel">
              <p className="eyebrow">Каталог</p>
              <h3 style={{ marginBottom: '1rem' }}>Самые популярные льготы</h3>
              {topBenefits.length > 0 ? (
                <RankedBars rows={topBenefits.map((b: any) => ({ label: b.benefit, value: b.redemptions }))} />
              ) : <p className="muted">Нет данных</p>}
            </div>
          </div>

          <div className="panel" style={{ marginBottom: '1.5rem' }}>
            <p className="eyebrow">Промокоды</p>
            <h3 style={{ marginBottom: '1rem' }}>Воронка использования</h3>
            {promoIssued > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 220px', gap: '1.5rem', alignItems: 'center' }}>
                <div style={{ display: 'grid', gap: '.8rem' }}>
                  {([
                    ['Выдано', promoIssued, '#145c63'],
                    ['Погашено', promoRedeemed, '#28734a'],
                    ['Не использовано', promoIssued - promoRedeemed, '#966b19'],
                  ] as [string, number, string][]).map(([label, val, color]) => (
                    <div key={label}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '.3rem', fontSize: '.85rem' }}>
                        <span>{label}</span>
                        <span style={{ fontWeight: 700, color }}>{val} <span className="muted">({Math.round((val / promoIssued) * 100)}%)</span></span>
                      </div>
                      <div style={{ height: 8, background: '#edf0f2', borderRadius: 99, overflow: 'hidden' }}>
                        <div style={{ height: '100%', width: `${(val / promoIssued) * 100}%`, background: color }} />
                      </div>
                    </div>
                  ))}
                </div>
                <div style={{ textAlign: 'center', padding: '1.2rem', background: 'var(--accent-soft)', borderRadius: 6 }}>
                  <div style={{ fontSize: '2.2rem', fontWeight: 800, color: rateColor }}>{promoRate}%</div>
                  <div style={{ fontSize: '.8rem', color: 'var(--muted)' }}>доходят до мерчанта</div>
                </div>
              </div>
            ) : <p className="muted">Промокоды ещё не выдавались</p>}
          </div>

          <div className="panel">
            <p className="eyebrow">Лидеры активности</p>
            <h3 style={{ marginBottom: '.75rem' }}>Топ-5 сотрудников по использованию</h3>
            {topEmployees.length > 0 ? (
              <div>
                {topEmployees.map((e, i) => (
                  <div key={e.id} className="list-row">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '.75rem' }}>
                      <span style={{ fontSize: '1.2rem', fontWeight: 800, color: i === 0 ? 'var(--accent)' : 'var(--muted)', minWidth: 24 }}>{i + 1}</span>
                      <div>
                        <strong>{e.first_name} {e.last_name}</strong>
                        <p className="muted">{e.email} · {e.plan ?? '—'}</p>
                      </div>
                    </div>
                    <span className="chip">{e.redemptions} погашений</span>
                  </div>
                ))}
              </div>
            ) : <p className="muted">Нет данных</p>}
          </div>
        </>
      )}

      {tab === 'employees' && (
        <section>
          {/* Панель синхронизации Bitrix24 */}
          <div className="panel" style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div>
                <p className="eyebrow">Bitrix24</p>
                <h2>Импорт сотрудников</h2>
              </div>
              <button
                className="button secondary"
                onClick={() => setShowBitrixForm(!showBitrixForm)}
              >
                {showBitrixForm ? 'Скрыть' : 'Синхронизация с Bitrix24'}
              </button>
            </div>

            {showBitrixForm && (
              <>
                <p className="muted" style={{ marginBottom: '1rem' }}>
                  Введите входящий webhook URL из вашего Bitrix24 портала.
                  Формат: <code>https://your-portal.bitrix24.ru/rest/1/xxxxx/</code>
                </p>

                <form onSubmit={syncBitrix} style={{ marginBottom: '1rem' }}>
                  <div className="inline-form">
                    <input
                      type="url"
                      placeholder="https://your-portal.bitrix24.ru/rest/1/xxxxx/"
                      value={bitrixWebhook}
                      onChange={(e) => setBitrixWebhook(e.target.value)}
                      required
                      disabled={bitrixLoading}
                      style={{ flex: 1 }}
                    />
                    <button
                      type="submit"
                      className="button"
                      disabled={bitrixLoading || !bitrixWebhook.trim()}
                    >
                      {bitrixLoading ? 'Импорт...' : 'Импортировать'}
                    </button>
                  </div>
                </form>

                {bitrixResult && (
                  <div
                    className="notice"
                    style={{
                      whiteSpace: 'pre-line',
                      background: bitrixResult.startsWith('✅') ? 'var(--accent-soft)' : '#fef2f2',
                      borderLeft: bitrixResult.startsWith('✅') ? '3px solid var(--accent)' : '3px solid #ef4444'
                    }}
                  >
                    {bitrixResult}
                  </div>
                )}

                <details style={{ marginTop: '1rem', fontSize: '.85rem', color: 'var(--muted)' }}>
                  <summary style={{ cursor: 'pointer', fontWeight: 600 }}>Как получить webhook?</summary>
                  <ol style={{ paddingLeft: '1.5rem', marginTop: '.5rem', lineHeight: 1.6 }}>
                    <li>Зайдите в Bitrix24: <strong>Приложения</strong> → <strong>Webhook</strong> → <strong>Входящий webhook</strong></li>
                    <li>Выберите права: <strong>user</strong> (чтение пользователей)</li>
                    <li>Скопируйте URL вида <code>https://ваш-портал.bitrix24.ru/rest/1/код/</code></li>
                    <li>Вставьте его выше и нажмите «Импортировать»</li>
                  </ol>
                </details>
              </>
            )}
          </div>

          {/* Существующий список сотрудников */}
          <div className="panel">
            <h2 style={{ marginBottom: '1rem' }}>Список сотрудников ({employees.length})</h2>
            {employees.length === 0 ? (
              <p className="muted">Пока нет сотрудников. Создайте приглашения или импортируйте из Bitrix24.</p>
            ) : (
              employees.map((emp) => (
                <div className="list-row" key={emp.id}>
                  <div>
                    <strong>{emp.first_name} {emp.last_name}</strong>
                    <p className="muted">{emp.email} · {emp.plan ?? '—'} · {emp.redemptions} использований</p>
                  </div>
                  <div className="row-actions">
                    <span className={`status ${emp.is_active ? 'issued' : 'expired'}`}>{emp.is_active ? 'ACTIVE' : 'INACTIVE'}</span>
                    <button className="button secondary small" onClick={() => void companyAPI.toggleEmployee(emp.id, !emp.is_active).then(load)}>
                      {emp.is_active ? 'Откл.' : 'Вкл.'}
                    </button>
                    {emp.plan && plans.filter((p) => p !== emp.plan).map((p) => (
                      <button className="button secondary small" key={p} onClick={() => void companyAPI.changePlan(emp.id, p).then(load)}>{p}</button>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      )}

      {tab === 'invites' && (
        <section>
          <div className="panel" style={{ marginBottom: '1.5rem' }}>
            <h2>Новое приглашение</h2>
            {newToken && <div className="notice"><strong>Токен (сохраните сейчас):</strong> <code>{newToken}</code></div>}
            <form className="offer-form" onSubmit={createInvite}>
              <div className="offer-grid">
                <label>Тариф<select value={inviteForm.plan} onChange={(e) => setInviteForm({ ...inviteForm, plan: e.target.value as Plan })}>{plans.map((p) => <option key={p}>{p}</option>)}</select></label>
                <label>Email (необязательно)<input type="email" value={inviteForm.email} onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}/></label>
                <label>Дней<input type="number" min="1" max="90" value={inviteForm.expires_in_days} onChange={(e) => setInviteForm({ ...inviteForm, expires_in_days: Number(e.target.value) })}/></label>
              </div>
              <button className="button">Создать приглашение</button>
            </form>
          </div>
          {invites.map((inv) => (
            <div className="list-row" key={inv.id}>
              <div><strong>{inv.plan}</strong><p className="muted">{inv.email ?? 'Любой'} · до {new Date(inv.expires_at).toLocaleDateString()}</p></div>
              <span className={`status ${inv.status.toLowerCase()}`}>{inv.status}</span>
            </div>
          ))}
        </section>
      )}

      {tab === 'report' && report && (
        <section className="two-columns">
          <div className="panel">
            <h2>Метрики</h2>
            {Object.entries(report.metrics).filter(([, v]) => typeof v !== 'object').map(([k, v]) => (
              <div className="list-row" key={k}><span>{k}</span><strong>{String(v)}</strong></div>
            ))}
          </div>
          <div className="panel">
            <p className="eyebrow">{report.ai_used ? 'AI-инсайты' : 'AI недоступен'}</p>
            <h2>Рекомендации</h2>
            <pre className="draft">{report.insights ?? 'AI в данный момент недоступен — метрики в левой колонке.'}</pre>
          </div>
        </section>
      )}
    </main>
  )
}
