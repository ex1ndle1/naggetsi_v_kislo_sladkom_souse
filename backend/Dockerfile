FROM python:3.13-slim AS builder

WORKDIR /build

# Зависимости ставятся из одного pyproject.toml, без исходников: слой
# переиспользуется, пока не менялись сами зависимости. Editable-режим здесь
# неприменим — пакета в этом слое ещё нет.
COPY pyproject.toml ./
# INSTALL_DEV=true добавляет pytest/ruff/mypy — нужны для проверок §52 внутри
# контейнера. По умолчанию выключено: в образ, открытый в сеть, тестовый
# инструментарий не попадает.
ARG INSTALL_DEV=false
RUN pip install --no-cache-dir --upgrade pip \
    && if [ "$INSTALL_DEV" = "true" ]; then \
         pip install --no-cache-dir ".[dev]"; \
       else \
         pip install --no-cache-dir .; \
       fi

# ---------------------------------------------------------------------------
FROM python:3.13-slim

WORKDIR /app

# postgresql-client — для ожидания БД в entrypoint, curl — для healthcheck
# из docker-compose.yml.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY pyproject.toml ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY tests ./tests
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Приложение не пишет в файловую систему и не нуждается в root: процесс, открытый
# в сеть, не должен иметь права менять собственный код.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["serve"]
