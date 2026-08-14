# Финальный чеклист проверки

## Backend

### Core модули
- [x] `app/core/security.py` — поля конфига исправлены (`jwt_secret`, `jwt_access_expire_minutes`)
- [x] `app/core/deps.py` — `Unauthenticated` вместо `Unauthorized`, `require_roles()` поддерживает varargs и список
- [x] `app/core/config.py` — добавлены `project_name`, `debug`
- [x] `app/core/errors.py` — все ошибки на месте
- [x] `app/core/database.py` — `get_session` экспортируется
- [x] `app/main.py` — использует `settings.project_name`, `settings.debug`

### Роутеры
- [x] `app/users/routes.py` — `create_access_token(user_id=, role=, company_id=, merchant_id=)`
- [x] `app/benefits/routes.py` — импорты из `deps`, `user.user_id`, `merchant_id` в схеме
- [x] `app/applications/routes.py` — `user.user_id`, кастомные ошибки
- [x] `app/payments/routes.py` — `user.user_id`, `selectinload(Application.benefit)`
- [x] `app/companies/routes.py` — согласованные импорты и ошибки
- [x] `app/merchants/routes.py` — согласованные импорты и ошибки
- [x] `app/ai/routes.py` — `user.user_id`, импорты
- [x] `app/events/routes.py` — `user.user_id`, Redis из `request.app.state.redis`

### Инфраструктура
- [x] `backend/Dockerfile` — multi-stage, `postgresql-client` установлен
- [x] `backend/docker-entrypoint.sh` — разделены команды `migrate` и `seed`, добавлено ожидание БД
- [x] `backend/pyproject.toml` — зависимости, pytest, ruff, mypy
- [x] `backend/tests/conftest.py` — фикстуры `db_session`, `client`
- [x] `backend/tests/test_auth.py` — базовые тесты аутентификации

## Frontend

### Страницы (полностью функциональные)
- [x] `src/pages/Login.tsx` — логин с демо-кредами (совпадают с сидами)
- [x] `src/pages/EmployeeDashboard.tsx` — загрузка льгот, заявок, рекомендаций AI
- [x] `src/pages/CompanyAdminDashboard.tsx` — статистика, отчёт AI, управление заявками
- [x] `src/pages/MerchantDashboard.tsx` — CRUD льгот с формой создания
- [x] `src/pages/PlatformAdminDashboard.tsx` — табы Overview/Companies/Merchants, управление статусами

### API и контекст
- [x] `src/api/client.ts` — все методы (`companies`, `merchants`, `aiAPI`, `subscribeToEvents`)
- [x] `src/context/AuthContext.tsx` — декодирование JWT, хранение user
- [x] `src/App.tsx` — роутинг, `PrivateRoute`, редирект по роли

### Конфигурация
- [x] `frontend/Dockerfile` — multi-stage с nginx, history fallback для SPA
- [x] `frontend/vite.config.ts` — proxy `/api` на backend
- [x] `frontend/tsconfig.json` — strict mode
- [x] `frontend/tsconfig.node.json` — Vite config
- [x] `frontend/package.json` — зависимости (react-router-dom, axios, tanstack/react-query)

## Docker & CI/CD

- [x] `docker-compose.yml` — разделены сервисы `migrate` и `seeds`, `backend` зависит от обоих
- [x] `.env.example` — все переменные окружения с комментариями
- [x] `.gitignore` — Python, Node, Docker, IDE
- [x] `.github/workflows/ci.yml` — lint и тесты для backend/frontend, docker build

## Документация

- [x] `README.md` — полное описание архитектуры, команд запуска, демо-пользователей, API endpoints
- [x] Демо-креды в `README.md` и `Login.tsx` совпадают с `backend/app/seeds/demo.py`

## Что НЕ проверено (требует установки зависимостей)

- [ ] `npm install` и `npm run build` — классификатор был недоступен
- [ ] `docker compose up --build` — проверка сборки и запуска всех сервисов
- [ ] `pytest` — запуск тестов backend
- [ ] Фактическая работа SSE (EventSource) в браузере
- [ ] AI-интеграция с Ollama (заглушки возвращают fallback)

## Следующие шаги для верификации

1. **Установить зависимости фронтенда:**
   ```bash
   cd frontend && npm install
   ```

2. **Проверить TypeScript:**
   ```bash
   npm run build
   ```

3. **Установить зависимости бэкенда:**
   ```bash
   cd backend && pip install -e .[dev]
   ```

4. **Запустить линтер:**
   ```bash
   ruff check app
   mypy app
   ```

5. **Собрать и запустить через Docker:**
   ```bash
   docker compose up --build
   ```

6. **Проверить логи:**
   ```bash
   docker compose logs migrate
   docker compose logs seeds
   docker compose logs backend
   ```

7. **Открыть приложение:**
   - Backend API: http://localhost:8000/docs
   - Frontend: http://localhost:3000
   - Войти с: `alice@alphacorp.uz` / `Demo1234!`

8. **Запустить тесты:**
   ```bash
   cd backend && pytest -v
   ```

## Известные ограничения

- **AI функции** — возвращают fallback, если Ollama недоступен или не настроен
- **SSE события** — требуют Redis pub/sub, пока не тестировались
- **Click платежи** — webhook endpoints готовы, но интеграция требует реальных credentials
- **Invite tokens** — регистрация пока не валидирует токены (TODO в `users/routes.py`)
