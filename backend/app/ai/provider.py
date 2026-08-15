"""Провайдер LLM: единственное место, где приложение говорит с Ollama.

Зачем протокол, а не прямой httpx-вызов в сервисе: тесты §42 обязаны проверять
поведение при таймауте, невалидном JSON и недоступности модели, не поднимая сеть.
Подменяется реализация, а не monkeypatch'ится httpx.

Cloud и локальный контейнер различаются двумя вещами: Bearer-токеном и суффиксом
``-cloud`` в имени модели, который локальный сервер не понимает. Обе особенности
живут здесь, чтобы бизнес-логика ничего не знала о транспорте.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import settings
from app.core.logging import get_logger

__all__ = [
    "LLMProvider",
    "LLMUnavailableError",
    "OllamaProvider",
    "get_llm_provider",
    "set_llm_provider",
]

logger = get_logger(__name__)


class LLMUnavailableError(RuntimeError):
    """Провайдер не смог получить ответ: сеть, таймаут, HTTP-ошибка, пустой ответ.

    Не наследуется от AppError: это внутренний сигнал для сервисного слоя, который
    сам решает, чем деградировать. Наружу как 5xx не выходит.
    """


@runtime_checkable
class LLMProvider(Protocol):
    """Минимальный контракт: строка на вход, строка на выход."""

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        """Вернуть текст ответа модели.

        Raises:
            LLMUnavailableError: при любой недоступности провайдера.
        """
        ...


class OllamaProvider:
    """Реализация над Ollama HTTP API (`/api/generate`)."""

    def __init__(
        self,
        *,
        host: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._host = (host if host is not None else settings.ollama_host).rstrip("/")
        self._raw_model = model if model is not None else settings.ollama_model
        self._api_key = api_key if api_key is not None else settings.ollama_api_key.get_secret_value()
        self._timeout = timeout if timeout is not None else settings.ollama_timeout_seconds
        self._is_cloud = "ollama.com" in self._host

    @property
    def model(self) -> str:
        """Имя модели, нормализованное под целевой хост.

        Cloud-каталог маркирует модели суффиксом ``-cloud``; локальный демон такого
        тега не знает и ответит 404, поэтому для него суффикс снимается.
        """
        if not self._is_cloud and self._raw_model.endswith("-cloud"):
            return self._raw_model[: -len("-cloud")]
        return self._raw_model

    def _headers(self) -> dict[str, str]:
        if self._is_cloud and self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._host}/api/generate",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            logger.warning("llm_timeout", model=self.model, timeout=self._timeout)
            raise LLMUnavailableError(f"Ollama timed out after {self._timeout}s") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("llm_http_error", model=self.model, status_code=exc.response.status_code)
            raise LLMUnavailableError(f"Ollama returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("llm_transport_error", model=self.model, error=str(exc))
            raise LLMUnavailableError(f"Ollama request failed: {exc}") from exc

        text = str(data.get("response", "")).strip()
        if not text:
            logger.warning("llm_empty_response", model=self.model)
            raise LLMUnavailableError("Ollama returned an empty response")
        return text


_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """Ленивый синглтон провайдера.

    Ленивый, потому что на импорте модуля настройки Ollama могут быть ещё не
    прочитаны (тесты, alembic), а создавать HTTP-клиент там незачем.
    """
    global _provider
    if _provider is None:
        _provider = OllamaProvider()
    return _provider


def set_llm_provider(provider: LLMProvider | None) -> None:
    """Подменить провайдера (тесты) или сбросить к дефолтному, передав None."""
    global _provider
    _provider = provider
