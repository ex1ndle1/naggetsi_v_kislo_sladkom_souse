# Наггетсы30 — Corporate Benefits Platform

(ранее NEXUS30)

B2B2C SaaS-платформа корпоративных льгот на основе seat-based subscription и promo codes.

## Бизнес-модель

**Это не ecommerce. Сотрудники НЕ платят внутри приложения.**

```
Company (корпоративный клиент)
   ↓ покупает корпоративный доступ (B2B-контракт)
Platform
   ↓ предоставляет сотрудникам аккаунты с планами
Employees (STANDARD / PLUS / PRO)
   ↓ получают promo codes
   ↓ используют коды у мерчантов
Merchants
   ↓ предоставляют скидки
```

### Монетизация

**Seat-based B2B subscription**: компания покупает места (seats) разных тарифов.

Пример:
```
Company Alpha
300 × STANDARD seats
150 × PLUS seats
 50 × PRO seats
```

Компания платит платформе за предоставленные места. MVP не реализует оплату B2B-контракта — только моделирует seat allocation.

### User flow

1. **Company Admin** создаёт invite token с привязкой к плану (STANDARD/PLUS/PRO)
2. **Employee** регистрируется по токену → получает аккаунт с закреплённым планом
3. **Employee** видит каталог льгот, отфильтрованный по своему плану
4. **Employee** выбирает льготу → получает promo code
5. **Employee** идёт на сайт merchant и использует код
6. **Merchant** подтверждает использование кода в своём dashboard
7. **Company** видит аналитику: redemption rate, usage by plan, популярные категории

### Тарифные планы

Одна льгота может иметь разные условия для разных планов:

```
Fitness Club
STANDARD → 5%
PLUS     → 15%
PRO      → 45%
```

Employee видит ТОЛЬКО те льготы, для которых существует offer его плана. Backend фильтрует на уровне SQL.

## Технологии

**Backend:**
- FastAPI + SQLAlchemy 2.0 async + Alembic
- PostgreSQL 17 (native ENUMs, partial indexes)
- Redis (rate limiting, SSE pub/sub)
- Argon2id password hashing
- JWT (access 15 min + refresh 7 days)
- Ollama AI (recommendations, merchant assistant, company analytics)

**Frontend:**
- React 18 + TypeScript strict mode
- Vite + TanStack Query
- Tailwind CSS
- SSE для realtime events

**Infrastructure:**
- Docker Compose
- nginx reverse proxy
- Multi-stage builds

## Быстрый старт

### Требования

- Docker + Docker Compose
- Node.js 20+ (для локальной разработки frontend)
- Python 3.12+ (для локальной разработки backend)

### Запуск

```bash
# 1. Скопировать .env
cp .env.example .env

# 2. Поднять все сервисы
docker compose up -d

# 3. Проверить статус
docker compose ps
docker compose logs backend | tail -20

# Доступ:
# - Frontend: http://localhost
# - Backend API: http://localhost/api/v1
# - API docs: http://localhost/api/docs
```

Миграции и seeds выполняются автоматически через отдельные Docker-сервисы `migrate` и `seeds`.

### Demo credentials

Все пароли: `Demo1234!`

**Employees:**
- `alice@alphacorp.uz` — STANDARD plan (AlphaCorp)
- `bob@alphacorp.uz` — PLUS plan (AlphaCorp)
- `charlie@alphacorp.uz` — PRO plan (AlphaCorp)
- `eve@betaindustries.uz` — STANDARD plan (Beta Industries)

**Company Admins:**
- `admin@alphacorp.uz` — AlphaCorp admin

**Merchants:**
- `merchant.user@fitzone.uz` — FitZone Gym merchant

**Platform Admin:**
- `platform@admin.uz` — полный доступ ко всей платформе

## Архитектура

Платформа построена на основе **слоистой архитектуры** (layered architecture) с чётким разделением ответственности:

- **Presentation layer** — `routes.py` (FastAPI endpoints)
- **Business logic layer** — `service.py` (domain logic, orchestration)
- **Data access layer** — `models.py` (SQLAlchemy ORM)

Все модули используют **dependency injection** через `Depends()` для управления зависимостями (DB session, auth user, config).

**Подробнее:** [ARCHITECTURE.md](./ARCHITECTURE.md)

### Ключевые домены

```
app/
├── users/          — authentication, users, roles
├── companies/      — корпоративные клиенты
├── plans/          — seat allocation (STANDARD/PLUS/PRO)
├── invites/        — invite tokens (one-time, SHA-256 hash)
├── merchants/      — поставщики льгот
├── benefits/       — каталог льгот + plan-specific offers
├── promo_codes/    — промокоды (crypto-secure generation)
├── redemptions/    — активация льгот сотрудниками
├── ai/             — Ollama integration (3 use cases)
├── analytics/      — аналитика для компаний
├── events/         — SSE realtime events
├── bot/            — Telegram bot API
├── bitrix/         — Bitrix24 integration
└── audit/          — audit logs
```

### База данных

**User** → `plan: STANDARD|PLUS|PRO` (NULL для MERCHANT/PLATFORM_ADMIN)

**PlanAllocation** → (company_id, plan) UNIQUE, allocated/assigned seats

**InviteToken** → одноразовый токен для регистрации, привязан к company + plan

**Benefit** → title, description, category, merchant_id, validity period

**BenefitPlanOffer** → (benefit_id, plan) UNIQUE, discount_percent

**BenefitRedemption** → факт получения promo code (заменяет legacy Application)

**PromoCode** → FIT-8XK29-QJ4M7 (prefix + crypto-random), ISSUED/REDEEMED/EXPIRED

### Безопасность

- **Tenant isolation**: `company_id` берётся из JWT, не из request body
- **Plan isolation**: backend фильтрует benefits по `user.plan` на уровне SQL
- **Seat allocation**: система запрещает назначение плана, если свободных seats нет
- **Invite token**: SHA-256 hash в БД, plaintext отдаётся создателю один раз
- **Promo code**: cryptographically secure, unique constraint
- **Rate limiting**: Redis-based, per-endpoint limits
- **Audit log**: все критические действия (invite, plan assignment, redemption)

## AI Features

Три сценария через Ollama:

### 1. Employee AI Concierge

Персонализированные рекомендации льгот на основе:
- План сотрудника (STANDARD/PLUS/PRO)
- История активаций (приоритет новым категориям)
- Поисковый запрос

```
User: "Хочу спорт и минимум 20% скидки"
→ Backend фильтрует по company/plan/category/discount
→ Собирает историю использованных категорий
→ LLM ранжирует по релевантности, приоритизируя новые категории
```

**Эндпоинт:** `GET /api/v1/ai/concierge`

**Fallback:** если Ollama недоступна, возвращаются топ-5 льгот по скидке с приоритетом неиспользованных категорий.

### 2. Merchant AI Assistant (§18)

Генерация описаний и категоризация при создании льготы:
```
Merchant: "Скидка 20% на годовой абонемент"
→ AI предлагает title, description, category, tags
→ Merchant корректирует и публикует
```

**Эндпоинт:** `POST /api/v1/ai/merchant/generate-offer`

### 3. Company AI Analytics (§19)

Аналитика использования льгот:
```
Data: seats (allocated/assigned), redemptions by plan, popular categories
→ AI генерирует insights:
  "PRO-пользователи активны (92% usage).
   Standard имеет низкую вовлечённость (48%).
   Рекомендуется расширить Standard benefits в Sport и Food."
```

**Эндпоинт:** `GET /api/v1/ai/company-report`

### Конфигурация Ollama

```env
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=gemma2:9b-instruct-q8_0
OLLAMA_API_KEY=  # для cloud-моделей
OLLAMA_IS_CLOUD=false
```

Graceful fallback: при недоступности AI основная функциональность (auth, benefits, promo codes, redemptions) продолжает работать.

## Telegram Bot

Платформа включает Telegram-бота для проверки и активации промокодов сотрудниками.

**Команды:**
- `/start` — приветствие и список команд
- `/check CODE` — проверить статус промокода
- `/activate CODE` — погасить промокод

**Настройка:**

1. Создайте бота через [@BotFather](https://t.me/BotFather)
2. Добавьте токен в `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
   BOT_API_KEY=<openssl rand -hex 32>
   ```
3. Перезапустите: `docker compose restart tg_bot`

## Bitrix24 Integration

Автоматический импорт сотрудников из Bitrix24 через REST API.

**Настройка:**

1. Получите входящий webhook:
   - Зайдите в «Приложения» → «Webhook» → «Входящий webhook»
   - Выберите права: `user` (чтение)
   - Скопируйте URL вида `https://your-portal.bitrix24.ru/rest/1/xxxxx/`

2. Импортируйте через UI (для COMPANY_ADMIN):
   - Войдите как COMPANY_ADMIN
   - Перейдите на вкладку «Сотрудники»
   - Нажмите «Синхронизация с Bitrix24»
   - Вставьте webhook URL и нажмите «Импортировать»

3. Сотрудники будут созданы с временным паролем `changeme` — попросите их сменить при первом входе.

**API:**
```http
POST /api/v1/companies/bitrix/sync
{
  "webhook_url": "https://your-portal.bitrix24.ru/rest/1/xxxxx/"
}
```

## Production Deployment

Для production используйте отдельный compose-файл:

```bash
# 1. Скопировать .env.prod.example в .env.prod и заполнить переменные
cp .env.prod.example .env.prod
nano .env.prod  # Заполнить POSTGRES_PASSWORD, JWT_SECRET, BOT_API_KEY

# 2. Запустить production-стек
docker compose -f docker-compose.prod.yml up -d

# 3. Проверить healthcheck
docker compose -f docker-compose.prod.yml ps
curl https://yourdomain.com/api/v1/health
```

**Отличия production от development:**
- `INSTALL_DEV=false` — без ruff/mypy/pytest
- `APP_ENV=production`, `DEBUG=false`
- Nginx с SSL, rate limiting, security headers
- Порты backend/frontend не пробрасываются наружу (только через nginx)
- Seed-сервис не запускается (нет демо-данных)

### SSL-сертификаты

**Вариант 1: Let's Encrypt (рекомендуется)**

```bash
sudo certbot certonly --standalone -d yourdomain.com
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/ssl/
sudo chown $USER:$USER nginx/ssl/*.pem
```

**Вариант 2: Self-signed (только для тестирования)**

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/privkey.pem \
  -out nginx/ssl/fullchain.pem \
  -subj "/C=UZ/ST=Tashkent/L=Tashkent/O=DevOrg/CN=localhost"
```

**Важно:** не коммитьте приватные ключи в git!

## API

### Employee

```http
GET  /api/v1/benefits                 # Каталог, отфильтрованный по плану
GET  /api/v1/benefits/{id}            # Детали льготы
POST /api/v1/benefits/{id}/redeem     # Получить promo code
GET  /api/v1/me/promo-codes           # Мои промокоды
GET  /api/v1/me/redemptions           # История активаций
GET  /api/v1/ai/recommendations       # AI-рекомендации
```

### Company Admin

```http
GET  /api/v1/company/seats            # Seat allocation (allocated/assigned/available)
POST /api/v1/company/invites          # Создать invite token
GET  /api/v1/company/employees        # Список сотрудников
POST /api/v1/company/employees/{id}/plan  # Назначить план
GET  /api/v1/company/analytics        # Использование по планам
POST /api/v1/ai/company-report        # AI insights
```

### Merchant

```http
GET    /api/v1/merchant/benefits          # Мои льготы
POST   /api/v1/merchant/benefits          # Создать льготу (с plan offers)
PATCH  /api/v1/merchant/benefits/{id}     # Обновить
DELETE /api/v1/merchant/benefits/{id}     # Деактивировать
POST   /api/v1/merchant/promo-codes/{code}/redeem  # Подтвердить использование
GET    /api/v1/merchant/analytics         # Статистика: issued/redeemed/rate
POST   /api/v1/ai/merchant/generate-offer # AI Assistant
```

### Platform Admin

```http
GET  /api/v1/admin/companies              # Все компании
POST /api/v1/admin/companies/{id}/seats   # Изменить seat allocation
GET  /api/v1/admin/merchants              # Все мерчанты
GET  /api/v1/admin/audit-logs             # Audit trail
```

## Разработка

### Backend

```bash
cd backend

# Установить зависимости
pip install -e .[dev]

# Линтер
ruff check app
ruff format app

# Type checking
mypy app

# Тесты
pytest -v --cov=app

# Миграции
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Frontend

```bash
cd frontend

npm install
npm run dev        # http://localhost:5173
npm run build
npm run lint
npm run typecheck
```

## Тестирование

### Unit + Integration

```bash
cd backend
pytest -v --cov=app --cov-report=html
```

Ключевые тесты (§40-§41):
- **Auth & RBAC**: роли, JWT claims
- **Tenant isolation**: IDOR protection
- **Invite token lifecycle**: valid → used → reject reuse/expired
- **Seat allocation**: назначение при отсутствии seats → Conflict
- **Plan visibility**: STANDARD не видит PRO-only benefit через API
- **Discount selection**: PRO user получает 45%, а не 5%
- **Promo code**: уникальность, одноразовость, expiration
- **Rate limiting**: Redis-based limits
- **AI mocking**: LLMProvider stub, timeout/unavailable handling

### E2E (Browser)

1. Логин (`alice@alphacorp.uz` / `Demo1234!`)
2. Каталог льгот — видны STANDARD-доступные
3. Get promo code → проверить формат FIT-XXXXX-XXXXX
4. Merchant dashboard → redeem code → статус REDEEMED
5. Company dashboard → seat allocation, analytics

## Deployment

### Production checklist

- [ ] Поменять `JWT_SECRET` на криптостойкий ключ (32+ байта)
- [ ] Установить `DEBUG=false`
- [ ] Настроить CORS_ORIGINS на реальный домен
- [ ] Использовать managed PostgreSQL (не локальный volume)
- [ ] Настроить Redis persistence (AOF)
- [ ] Добавить healthchecks в docker-compose
- [ ] Настроить log aggregation (Loki/ELK)
- [ ] Включить HTTPS (Let's Encrypt + nginx)
- [ ] Отключить `SEED_DEMO_DATA=false`
- [ ] Настроить backup PostgreSQL
- [ ] Rate limiting: уменьшить RATE_LIMIT_MAX_REQUESTS для production
- [ ] AI: добавить OLLAMA_API_KEY для cloud-модели или настроить локальный Ollama с GPU

### Environment variables (production)

```env
DEBUG=false
CORS_ORIGINS=https://benefits.example.com
JWT_SECRET=<generate-with-openssl-rand-base64-32>
POSTGRES_HOST=<managed-db-host>
REDIS_URL=redis://<managed-redis-host>:6379/0
OLLAMA_HOST=<ollama-service-url>
SEED_DEMO_DATA=false
```

## Roadmap

### Текущий статус (MVP)

- ✅ Seat-based subscription model
- ✅ Invite tokens + plan assignment
- ✅ Plan-specific benefit visibility
- ✅ Promo code generation & redemption
- ✅ Merchant dashboard (код validation)
- ✅ AI recommendations (3 use cases)
- ✅ Audit logs
- ⚠️ SSE realtime (auth сломана — EventSource не передаёт headers)

### Следующие этапы

1. **SSE authentication** (§5): короткоживущие SSE-тикеты через Redis
2. **Merchant CRUD** полностью (пока stub)
3. **Company admin UI**: seat management, invite generation
4. **Platform admin UI**: company/merchant management
5. **Analytics dashboard**: charts (Chart.js/Recharts)
6. **Email notifications**: welcome, promo code issued, expiration warnings
7. **Webhook от merchant** для автоматической пометки REDEEMED
8. **Multi-language**: i18n (uz/ru/en)

## Лицензия

Proprietary. Все права защищены.

## Контакты

- Backend: FastAPI + SQLAlchemy 2.0
- Frontend: React 18 + TypeScript
- AI: Ollama (gemma2/llama3)
- Deployment: Docker Compose
