import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const FEATURES = [
  { icon: '🎁', title: 'Каталог льгот', desc: 'Персональный список бенефитов по тарифу: скидки 5–60% у партнёров — фитнес, питание, образование, развлечения.' },
  { icon: '🏢', title: 'Управление компанией', desc: 'HR-администраторы распределяют места, выдают инвайты и видят аналитику использования в реальном времени.' },
  { icon: '🏪', title: 'Кабинет мерчанта', desc: 'Партнёры публикуют льготы, принимают промокоды через QR или вручную и получают отчёты по погашениям.' },
  { icon: '🤖', title: 'AI-ассистент', desc: 'Gemma 4 31B ранжирует каталог под ваш запрос и генерирует черновики описаний льгот для мерчантов.' },
]

const PLANS = [
  { name: 'STANDARD', discount: '5–10 %', features: ['Базовый каталог льгот', 'AI-консьерж', 'История погашений'] },
  { name: 'PLUS',     discount: '15–25 %', features: ['Расширенный каталог', 'AI-консьерж', 'Приоритетная поддержка'] },
  { name: 'PRO',      discount: '40–60 %', features: ['Полный каталог + эксклюзив', 'AI-консьерж', 'Персональный менеджер'] },
]

const STATS = [
  { value: '5', label: 'партнёров' },
  { value: '5+', label: 'категорий льгот' },
  { value: '3', label: 'тарифных плана' },
  { value: 'AI', label: 'рекомендации' },
]

export default function Landing() {
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (!authLoading && user) navigate('/dashboard', { replace: true })
  }, [user, authLoading, navigate])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--paper)', color: 'var(--ink)' }}>

      {/* NAV */}
      <nav style={{ borderBottom: '1px solid var(--line)', padding: '.9rem 0', position: 'sticky', top: 0, background: 'rgba(255,255,255,.92)', backdropFilter: 'blur(8px)', zIndex: 10 }}>
        <div style={{ width: 'min(1180px, calc(100% - 2rem))', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 800, fontSize: '1.15rem', color: 'var(--accent)', letterSpacing: '-.02em' }}>
            NEXUS<span style={{ color: 'var(--ink)' }}>30</span>
          </span>
          <div style={{ display: 'flex', gap: '.6rem' }}>
            <button className="button secondary small" onClick={() => navigate('/login')}>Войти</button>
            <button className="button small" onClick={() => navigate('/login')}>Начать →</button>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <section style={{ background: 'linear-gradient(160deg,#e2f0f0 0%,#f4f6f8 55%)', padding: '5.5rem 0 5rem', textAlign: 'center' }}>
        <div style={{ width: 'min(760px, calc(100% - 2rem))', margin: '0 auto' }}>
          <span className="eyebrow">Платформа корпоративных льгот</span>
          <h1 style={{ fontSize: 'clamp(2.2rem,6vw,3.8rem)', lineHeight: 1.08, margin: '1rem auto .9rem' }}>
            Умные бенефиты<br />для вашей команды
          </h1>
          <p style={{ color: 'var(--muted)', fontSize: '1.1rem', maxWidth: 500, margin: '0 auto 2.4rem', lineHeight: 1.65 }}>
            Единая платформа для сотрудников, HR-отделов и партнёров. Гибкие тарифы, промокоды и AI-рекомендации.
          </p>
          <div style={{ display: 'flex', gap: '.8rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <button className="button" style={{ padding: '.85rem 2.2rem', fontSize: '1rem' }} onClick={() => navigate('/login')}>
              Начать работу →
            </button>
            <button className="button secondary" style={{ padding: '.85rem 2.2rem', fontSize: '1rem' }} onClick={() => navigate('/login')}>
              Демо-вход
            </button>
          </div>
        </div>
      </section>

      {/* STATS */}
      <section style={{ borderBottom: '1px solid var(--line)', padding: '2.5rem 0' }}>
        <div style={{ width: 'min(1180px, calc(100% - 2rem))', margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: '1rem', textAlign: 'center' }}>
          {STATS.map(s => (
            <div key={s.label}>
              <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--accent)' }}>{s.value}</div>
              <div style={{ color: 'var(--muted)', fontSize: '.85rem', marginTop: '.2rem' }}>{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* FEATURES */}
      <section style={{ padding: '4.5rem 0' }}>
        <div style={{ width: 'min(1180px, calc(100% - 2rem))', margin: '0 auto' }}>
          <p className="eyebrow" style={{ textAlign: 'center', marginBottom: '.5rem' }}>Возможности</p>
          <h2 style={{ textAlign: 'center', fontSize: 'clamp(1.5rem,3vw,2rem)', marginBottom: '2.5rem' }}>Всё необходимое в одном месте</h2>
          <div className="cards">
            {FEATURES.map(f => (
              <div key={f.title} className="card" style={{ padding: '1.6rem' }}>
                <div style={{ fontSize: '2.2rem', marginBottom: '.6rem' }}>{f.icon}</div>
                <h3 style={{ marginBottom: '.4rem' }}>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* PLANS */}
      <section style={{ background: '#f4f6f8', padding: '4.5rem 0' }}>
        <div style={{ width: 'min(1180px, calc(100% - 2rem))', margin: '0 auto' }}>
          <p className="eyebrow" style={{ textAlign: 'center', marginBottom: '.5rem' }}>Тарифы</p>
          <h2 style={{ textAlign: 'center', fontSize: 'clamp(1.5rem,3vw,2rem)', marginBottom: '2.5rem' }}>Три уровня льгот</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: '1rem' }}>
            {PLANS.map((p, i) => (
              <div key={p.name} className="card" style={{ padding: '2rem 1.6rem', border: i === 2 ? '2px solid var(--accent)' : undefined, position: 'relative' }}>
                {i === 2 && <span className="chip" style={{ position: 'absolute', top: '1rem', right: '1rem' }}>Лучший выбор</span>}
                <span className="eyebrow">{p.name}</span>
                <p style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--accent)', margin: '.5rem 0 .2rem' }}>{p.discount}</p>
                <p style={{ color: 'var(--muted)', fontSize: '.82rem', marginBottom: '1.4rem' }}>скидка у партнёров</p>
                <ul style={{ listStyle: 'none', display: 'grid', gap: '.6rem' }}>
                  {p.features.map(feat => (
                    <li key={feat} style={{ fontSize: '.88rem', display: 'flex', gap: '.45rem' }}>
                      <span style={{ color: 'var(--accent)', flexShrink: 0 }}>✓</span>{feat}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section style={{ padding: '5rem 0', textAlign: 'center', background: 'var(--accent)' }}>
        <div style={{ width: 'min(600px, calc(100% - 2rem))', margin: '0 auto' }}>
          <h2 style={{ color: '#fff', fontSize: 'clamp(1.5rem,3vw,2rem)', marginBottom: '1rem' }}>Готовы попробовать?</h2>
          <p style={{ color: 'rgba(255,255,255,.75)', marginBottom: '2rem', lineHeight: 1.6 }}>
            Войдите под одной из демо-ролей и оцените платформу в действии.
          </p>
          <button style={{ border: '2px solid #fff', borderRadius: 4, padding: '.85rem 2.4rem', background: 'transparent', color: '#fff', fontWeight: 700, fontSize: '1rem', cursor: 'pointer' }}
            onClick={() => navigate('/login')}>
            Открыть демо →
          </button>
        </div>
      </section>

      {/* FOOTER */}
      <footer style={{ borderTop: '1px solid var(--line)', padding: '2rem 0', textAlign: 'center', color: 'var(--muted)', fontSize: '.82rem' }}>
        <p>© 2026 Наггетсы30 · Корпоративная платформа льгот</p>
      </footer>
    </div>
  )
}
