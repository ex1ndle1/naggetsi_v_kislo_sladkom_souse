"""Конфигурация приложения. Единственный источник настроек — переменные окружения.

Ничего из перечисленного здесь не хардкодится в бизнес-логике: имя модели Ollama,
Click-credentials и параметры БД читаются только отсюда (ТЗ §29, §54).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Приложение ---
    project_name: str = "Corporate Benefits Platform"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"
    public_base_url: str = "http://localhost"
    cors_origins: str = "http://localhost"

    # --- PostgreSQL ---
    postgres_db: str = "benefits"
    postgres_user: str = "benefits"
    postgres_password: SecretStr = SecretStr("benefits")
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"

    # --- JWT ---
    jwt_secret: SecretStr = SecretStr("dev-only-change-me")
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    # --- Ollama / AI ---
    ai_enabled: bool = True
    ollama_host: str = "https://ollama.com"
    ollama_api_key: SecretStr = SecretStr("")
    ollama_model: str = "gemma4:31b-cloud"
    ollama_timeout_seconds: float = 60.0

    # --- Click ---
    click_sandbox: bool = True
    click_merchant_id: str = "demo_merchant"
    click_service_id: str = "demo_service"
    click_secret_key: SecretStr = SecretStr("demo_secret_key")
    click_merchant_user_id: str = "demo_merchant_user"

    # --- Демо-данные ---
    seed_demo_data: bool = True
    demo_password: SecretStr = SecretStr("Demo1234!")

    # --- Rate limiting (запросов за окно) ---
    rate_limit_max_requests: int = 100  # Глобальный лимит на IP
    rate_limit_window_seconds: int = 60
    rate_limit_login: int = 10
    rate_limit_register: int = 5
    rate_limit_payments: int = 20
    rate_limit_ai: int = 15
    rate_limit_applications: int = 30

    # --- Прочее ---
    default_currency: str = "UZS"

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Async DSN для SQLAlchemy/asyncpg."""
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ollama_is_cloud(self) -> bool:
        """True, если запросы идут напрямую в ollama.com, а не в локальный контейнер.

        В cloud-режиме нужен Bearer-токен, а имя модели передаётся без суффикса
        ``-cloud`` — нормализацией занимается OllamaProvider.
        """
        return "ollama.com" in self.ollama_host

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Настройки кэшируются: читаем окружение один раз за процесс."""
    return Settings()


settings: Settings = get_settings()


__all__ = ["Settings", "get_settings", "settings"]
