import { useEffect, useState, type FormEvent } from 'react'
import { aiAPI, merchantAPI, type Analytics, type Benefit, type BenefitCategory, type Plan } from '../api/client'
import { useAuth } from '../context/AuthContext'

const plans: Plan[] = ['STANDARD', 'PLUS', 'PRO']
const CATEGORIES: BenefitCategory[] = ['SPORT', 'EDUCATION', 'HEALTH', 'FOOD', 'TRANSPORT', 'ENTERTAINMENT', 'TECH', 'OTHER']

type Tab = 'benefits' | 'analytics' | 'promo'

export default function MerchantDashboard() {
  const { user, logout } = useAuth()
  const [tab, setTab] = useState<Tab>('benefits')
  const [benefits, setBenefits] = useState<Benefit[]>([])
  const [analytics, setAnalytics] = useState<Analytics>({})
  const [code, setCode] = useState('')
  const [result, setResult] = useState('')
  const [hint, setHint] = useState('')
  const [draft, setDraft] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ title: '', description: '', category: 'SPORT' as BenefitCategory, destination_url: '', standard: '5', plus: '15', pro: '45' })

  const load = async () => {
    const [b, a] = await Promise.all([merchantAPI.benefits(), merchantAPI.analytics()])
    setBenefits(b.data); setAnalytics(a.data)
  }
  useEffect(() => { void load() }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await merchantAPI.createBenefit({
        title: form.title, description: form.description, category: form.category,
        destination_url: form.destination_url || null,
        plan_offers: plans.map((plan) => ({ plan, discount_percent: Number(form[plan.toLowerCase() as 'standard' | 'plus' | 'pro']), is_available: true }))
      })
      setShowForm(false); setForm({ title: '', description: '', category: 'SPORT', destination_url: '', standard: '5', plus: '15', pro: '45' })
      await load()
    } catch (err: any) { alert(err.response?.data?.error?.message || 'Не удалось сохранить предложение') }
  }

  const checkCode = async (redeem = false) => {
    try {
      const response = redeem ? await merchantAPI.redeemPromo(code) : await merchantAPI.lookupPromo(code)
      setResult(redeem ? response.data.message : `${response.data.benefit_title}: ${response.data.status}`)
      if (redeem) await load()
    } catch (err: any) { setResult(err.response?.data?.error?.message || 'Код не найден') }
  }

  const generateDraft = async () => {
    const { data } = await aiAPI.merchantDraft(hint)
    setDraft(data.draft ? `${data.draft.title}\n\n${data.draft.description}` : (data.message || 'Черновик недоступен'))
  }

  const issued = (analytics.promo_codes_issued as number) ?? 0
  const redeemed = (analytics.promo_codes_redeemed as number) ?? 0
  const expired = (analytics.promo_codes_expired as number) ?? 0
  const revoked = (analytics.promo_codes_revoked as number) ?? 0
  const rate = (analytics.redemption_rate_percent as number) ?? 0
  const active = (analytics.benefits_active as number) ?? 0
  const benefitsTotal = (analytics.benefits_total as number) ?? 0
  const benefitsInactive = (analytics.benefits_inactive as number) ?? Math.max(0, benefitsTotal - active)
  const topBenefits = (analytics.top_benefits as any[]) ?? []
  const trend = (analytics.redemption_trend as { day: string; count: number }[]) ?? []
  const conversionColor = rate >= 60 ? '#28734a' : rate >= 30 ? '#966b19' : '#a34444'
  // Промокоды, что ещё в игре: не погашены, не истекли, не отозваны.
  const pending = Math.max(0, issued - redeemed - expired - revoked)

  const TabBtn = ({ id, label }: { id: Tab; label: string }) => (
    <button className={`tab ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>{label}</button>
  )

  return (
    <main className="page">
      <header className="topbar">
        <div><p className="eyebrow">Кабинет партнёра</p><h1>{user?.first_name} {user?.last_name}</h1></div>
        <button className="button secondary" onClick={logout}>Выйти</button>
      </header>

      <section className="metrics">
        {[
          ['Активных предложений', active, ''],
          ['Выдано промокодов', issued, ''],
          ['Погашено', redeemed, ''],
          ['Истекло', expired, ''],
          ['Конверсия', rate, '%'],
        ].map(([label, value, suffix]) => (
          <div className="metric" key={String(label)}>
            <span>{String(label)}</span>
            <strong style={label === 'Конверсия' ? { color: conversionColor } : {}}>
              {String(value)}{String(suffix)}
            </strong>
          </div>
        ))}
      </section>

      <nav className="tabs">
        <TabBtn id="benefits" label={`Предложения (${benefits.length})`} />
        <TabBtn id="analytics" label="Аналитика" />
        <TabBtn id="promo" label="Касса · AI" />
      </nav>

      {tab === 'benefits' && (
        <section>
          <div className="section-heading">
            <div><p className="eyebrow">Каталог партнёра</p><h2>Мои предложения</h2></div>
            <button className="button" onClick={() => setShowForm(!showForm)}>{showForm ? 'Закрыть' : 'Новое предложение'}</button>
          </div>
          {showForm && (
            <form className="panel offer-form" style={{ marginBottom: '1.5rem' }} onSubmit={submit}>
              <h3>Новое предложение</h3>
              <input required placeholder="Название" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              <textarea required placeholder="Описание" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <input placeholder="Ссылка назначения (https://…)" value={form.destination_url} onChange={(e) => setForm({ ...form, destination_url: e.target.value })} />
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as BenefitCategory })}>
                {CATEGORIES.map((x) => <option key={x}>{x}</option>)}
              </select>
              <div className="offer-grid">
                {plans.map((plan) => (
                  <label key={plan}>{plan} скидка %
                    <input type="number" min="0" max="100" value={form[plan.toLowerCase() as 'standard' | 'plus' | 'pro']} onChange={(e) => setForm({ ...form, [plan.toLowerCase()]: e.target.value })} />
                  </label>
                ))}
              </div>
              <button className="button">Сохранить предложение</button>
            </form>
          )}
          <div className="cards">
            {benefits.map((b) => (
              <article className="card" key={b.id}>
                <div className="card-head">
                  <span className="tag">{b.category}</span>
                  <span className={`status ${b.is_active ? 'issued' : 'expired'}`}>{b.is_active ? 'ACTIVE' : 'INACTIVE'}</span>
                </div>
                <h3>{b.title}</h3>
                <p>{b.description}</p>
                <div className="chips">
                  {b.plan_offers.map((o) => <span className="chip" key={o.plan}>{o.plan}: −{o.discount_percent}%</span>)}
                </div>
                {b.valid_until && <p style={{ fontSize: '.78rem', color: 'var(--muted)' }}>До {new Date(b.valid_until).toLocaleDateString()}</p>}
                <button className="button secondary" onClick={() => void merchantAPI.updateBenefit(b.id, { is_active: !b.is_active }).then(load)}>
                  {b.is_active ? 'Деактивировать' : 'Активировать'}
                </button>
              </article>
            ))}
          </div>
        </section>
      )}

      {tab === 'analytics' && (
        <section>
          <div className="two-columns" style={{ marginBottom: '1.5rem' }}>
            <div className="panel">
              <p className="eyebrow">Промокоды</p>
              <h3 style={{ marginBottom: '1rem' }}>Статус использования</h3>
              {issued > 0 ? (
                <>
                  <div style={{ display: 'grid', gap: '.8rem', marginBottom: '1.2rem' }}>
                    {([
                      ['Выдано', issued, '#145c63'],
                      ['Погашено', redeemed, '#28734a'],
                      ['Ожидают', pending, '#657284'],
                      ['Истекло', expired, '#966b19'],
                      ['Отозвано', revoked, '#a34444'],
                    ] as [string, number, string][]).map(([label, val, color]) => (
                      <div key={String(label)}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '.3rem', fontSize: '.85rem' }}>
                          <span>{String(label)}</span><span style={{ fontWeight: 700, color: String(color) }}>{String(val)}</span>
                        </div>
                        <div style={{ height: 8, background: '#edf0f2', borderRadius: 99, overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${issued > 0 ? (Number(val) / issued) * 100 : 0}%`, background: String(color) }} />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div style={{ textAlign: 'center', padding: '1rem', background: 'var(--accent-soft)', borderRadius: 6 }}>
                    <div style={{ fontSize: '2rem', fontWeight: 800, color: conversionColor }}>{rate}%</div>
                    <div style={{ fontSize: '.8rem', color: 'var(--muted)' }}>конверсия</div>
                  </div>
                </>
              ) : <p className="muted">Нет данных о промокодах</p>}
            </div>

            <div className="panel">
              <p className="eyebrow">Предложения</p>
              <h3 style={{ marginBottom: '1rem' }}>Топ по погашениям</h3>
              {topBenefits.length > 0 ? (
                <div style={{ display: 'grid', gap: '.75rem' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 60px 60px 60px', gap: '.5rem', fontSize: '.75rem', color: 'var(--muted)', fontWeight: 700, paddingBottom: '.4rem', borderBottom: '1px solid var(--line)' }}>
                    <span>Льгота</span><span style={{ textAlign: 'right' }}>Выдано</span><span style={{ textAlign: 'right' }}>Погашено</span><span style={{ textAlign: 'right' }}>%</span>
                  </div>
                  {topBenefits.slice(0, 8).map((b: any, i: number) => {
                    const bIssued: number = b.issued ?? b.redemptions ?? 0
                    const bRedeemed: number = b.redeemed ?? 0
                    const bRate = bIssued > 0 ? Math.round((bRedeemed / bIssued) * 100) : 0
                    const bColor = bRate >= 60 ? '#28734a' : bRate >= 30 ? '#966b19' : '#a34444'
                    return (
                      <div key={b.benefit ?? b.benefit_title ?? i}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 60px 60px 60px', gap: '.5rem', alignItems: 'center', marginBottom: '.25rem' }}>
                          <span style={{ fontSize: '.82rem', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={b.benefit ?? b.benefit_title}>{b.benefit ?? b.benefit_title ?? `Льгота ${i + 1}`}</span>
                          <span style={{ textAlign: 'right', fontSize: '.82rem' }}>{bIssued}</span>
                          <span style={{ textAlign: 'right', fontSize: '.82rem' }}>{bRedeemed}</span>
                          <span style={{ textAlign: 'right', fontSize: '.82rem', fontWeight: 700, color: bColor }}>{bRate}%</span>
                        </div>
                        <div style={{ height: 4, background: '#edf0f2', borderRadius: 99, overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${bIssued > 0 ? (bRedeemed / bIssued) * 100 : 0}%`, background: bColor }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div style={{ display: 'grid', gap: '.5rem' }}>
                  {benefits.map((b) => (
                    <div key={b.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '.4rem 0', borderBottom: '1px solid var(--line)' }}>
                      <span style={{ fontSize: '.85rem' }}>{b.title}</span>
                      <span className={`status ${b.is_active ? 'issued' : 'expired'}`}>{b.is_active ? 'ACTIVE' : 'OFF'}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="two-columns" style={{ marginBottom: '1.5rem' }}>
            <div className="panel">
              <p className="eyebrow">Каталог</p>
              <h3 style={{ marginBottom: '1rem' }}>Активные и выключенные</h3>
              {benefitsTotal > 0 ? (
                <>
                  <div style={{ display: 'flex', height: 26, borderRadius: 6, overflow: 'hidden', marginBottom: '.9rem' }}>
                    <div style={{ width: `${(active / benefitsTotal) * 100}%`, background: '#28734a' }} />
                    <div style={{ width: `${(benefitsInactive / benefitsTotal) * 100}%`, background: '#c9d0d8' }} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.82rem' }}>
                    <span><span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 2, background: '#28734a', marginRight: '.4rem' }} />Активные · <strong>{active}</strong></span>
                    <span><span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 2, background: '#c9d0d8', marginRight: '.4rem' }} />Выключены · <strong>{benefitsInactive}</strong></span>
                  </div>
                  <p style={{ marginTop: '.9rem', fontSize: '.8rem', color: 'var(--muted)' }}>
                    Всего в каталоге {benefitsTotal} · доля активных {Math.round((active / benefitsTotal) * 100)}%
                  </p>
                </>
              ) : <p className="muted">Предложений пока нет</p>}
            </div>

            <div className="panel">
              <p className="eyebrow">Динамика</p>
              <h3 style={{ marginBottom: '1rem' }}>Погашения за 30 дней</h3>
              {trend.length > 0 ? (
                <>
                  {/* Столбики по дням. Высота от максимума в выборке: важна форма
                      кривой, а не абсолютный масштаб. */}
                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 120, marginBottom: '.6rem' }}>
                    {trend.map((p) => {
                      const max = trend.reduce((m, t) => Math.max(m, t.count), 0) || 1
                      return (
                        <div
                          key={p.day}
                          title={`${new Date(p.day).toLocaleDateString()}: ${p.count}`}
                          style={{ flex: 1, height: `${Math.max(4, (p.count / max) * 100)}%`, background: 'var(--accent)', borderRadius: '2px 2px 0 0', minWidth: 3 }}
                        />
                      )
                    })}
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.75rem', color: 'var(--muted)' }}>
                    <span>{new Date(trend[0].day).toLocaleDateString()}</span>
                    <span>всего {trend.reduce((s, t) => s + t.count, 0)}</span>
                    <span>{new Date(trend[trend.length - 1].day).toLocaleDateString()}</span>
                  </div>
                </>
              ) : <p className="muted">За последние 30 дней погашений не было</p>}
            </div>
          </div>

          <div className="panel">
            <p className="eyebrow">Сводка</p>
            <h3 style={{ marginBottom: '1rem' }}>Эффективность по тарифам</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: '1rem' }}>
              {plans.map((plan) => {
                const planOffers = benefits.flatMap((b) => b.plan_offers.filter((o) => o.plan === plan))
                const avgDiscount = planOffers.length > 0 ? Math.round(planOffers.reduce((s, o) => s + o.discount_percent, 0) / planOffers.length) : 0
                return (
                  <div key={plan} style={{ background: '#f4f6f8', borderRadius: 6, padding: '1rem' }}>
                    <span className="eyebrow">{plan}</span>
                    <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--accent)', margin: '.4rem 0 .1rem' }}>{avgDiscount}%</div>
                    <div style={{ fontSize: '.78rem', color: 'var(--muted)' }}>средняя скидка · {planOffers.length} предложений</div>
                  </div>
                )
              })}
            </div>
          </div>
        </section>
      )}

      {tab === 'promo' && (
        <section className="two-columns">
          <div className="panel">
            <p className="eyebrow">Проверка на кассе</p>
            <h2 style={{ marginBottom: '1rem' }}>Подтвердить промокод</h2>
            <div className="inline-form">
              <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="Код клиента" style={{ fontFamily: 'monospace', letterSpacing: '.08em' }} />
              <button className="button secondary" onClick={() => void checkCode()}>Проверить</button>
              <button className="button" onClick={() => void checkCode(true)}>Погасить</button>
            </div>
            {result && <p className="notice" style={{ marginTop: '.8rem' }}>{result}</p>}
            <div style={{ marginTop: '1.5rem', padding: '1rem', background: '#f4f6f8', borderRadius: 6 }}>
              <p className="eyebrow" style={{ marginBottom: '.4rem' }}>Как это работает</p>
              <ol style={{ paddingLeft: '1.2rem', display: 'grid', gap: '.4rem', fontSize: '.85rem', color: 'var(--muted)', lineHeight: 1.5 }}>
                <li>Сотрудник показывает промокод</li>
                <li>Нажмите «Проверить» чтобы убедиться что код действителен</li>
                <li>Нажмите «Погасить» после предоставления скидки</li>
              </ol>
            </div>
          </div>
          <div className="panel">
            <p className="eyebrow">AI-помощник</p>
            <h2 style={{ marginBottom: '1rem' }}>Черновик предложения</h2>
            <div className="inline-form">
              <input value={hint} onChange={(e) => setHint(e.target.value)} placeholder="Опишите идею (напр: фитнес-абонемент для IT-специалистов)" />
              <button className="button" onClick={() => void generateDraft()} disabled={!hint.trim()}>Создать</button>
            </div>
            {draft && (
              <div style={{ marginTop: '1rem', padding: '1rem', background: 'var(--accent-soft)', borderRadius: 6, borderLeft: '3px solid var(--accent)' }}>
                <p className="eyebrow" style={{ marginBottom: '.5rem' }}>Готовый черновик</p>
                <pre className="draft" style={{ marginTop: 0 }}>{draft}</pre>
              </div>
            )}
          </div>
        </section>
      )}
    </main>
  )
}
