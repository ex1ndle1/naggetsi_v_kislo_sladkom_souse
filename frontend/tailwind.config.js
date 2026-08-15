/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Тарифы сотрудников: один и тот же цвет обозначает один и тот же план
        // во всех четырёх дашбордах.
        plan: {
          standard: '#64748b',
          plus: '#0ea5e9',
          pro: '#7c3aed',
        },
        // Статусы промокодов и погашений.
        state: {
          issued: '#0284c7',
          redeemed: '#059669',
          expired: '#a1a1aa',
          revoked: '#dc2626',
        },
      },
    },
  },
  plugins: [],
}
