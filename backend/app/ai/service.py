"""AI service: интеграция с Ollama для трёх сценариев (ТЗ §18-20).

1. Персонализированные рекомендации льгот
2. Оценка риска fraud при оплате
3. Генерация отчётов для компаний
"""

import json
from typing import Any

import httpx

from app.core.config import settings

__all__ = ["AIService", "get_benefit_recommendations", "assess_fraud_risk", "generate_company_report"]


class AIService:
    """Wrapper для Ollama API с graceful fallback."""

    def __init__(self):
        self.enabled = settings.ai_enabled
        self.base_url = settings.ollama_host
        self.api_key = settings.ollama_api_key.get_secret_value()
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout_seconds

    async def _call(self, prompt: str, system: str | None = None) -> str | None:
        """Вызов Ollama API с fallback при ошибке."""
        if not self.enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                }
                if system:
                    payload["system"] = system

                response = await client.post(
                    f"{self.base_url}/api/generate",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "").strip()

        except Exception as e:
            # Graceful degradation: логируем ошибку и возвращаем None
            print(f"[AI] Ollama error: {e}")
            return None

    async def recommend_benefits(
        self,
        employee_profile: dict[str, Any],
        available_benefits: list[dict[str, Any]],
    ) -> list[str] | None:
        """Сценарий 1: Персонализированные рекомендации льгот.

        Возвращает список benefit_id в порядке релевантности.
        При ошибке AI возвращает None → фоллбэк на дефолтную сортировку.
        """
        system_prompt = (
            "You are a benefits recommendation assistant. "
            "Analyze employee profile and suggest the most relevant benefits. "
            "Return only a JSON array of benefit IDs in order of relevance."
        )

        user_prompt = (
            f"Employee profile: {json.dumps(employee_profile)}\n\n"
            f"Available benefits: {json.dumps(available_benefits)}\n\n"
            "Recommend benefits based on employee's role, company, and preferences. "
            "Return JSON array: [\"benefit_id_1\", \"benefit_id_2\", ...]"
        )

        response = await self._call(user_prompt, system=system_prompt)
        if not response:
            return None

        try:
            # Парсим JSON из ответа
            benefit_ids = json.loads(response)
            if isinstance(benefit_ids, list):
                return benefit_ids
        except (json.JSONDecodeError, ValueError):
            pass

        return None

    async def assess_fraud(
        self,
        payment_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Сценарий 2: Оценка риска fraud при оплате.

        Возвращает {"risk_score": float, "reason": str}.
        При ошибке AI возвращает None → пропускаем проверку.
        """
        system_prompt = (
            "You are a fraud detection assistant. "
            "Analyze payment data and assess fraud risk (0.0 = safe, 1.0 = suspicious). "
            "Return only JSON: {\"risk_score\": 0.0-1.0, \"reason\": \"explanation\"}."
        )

        user_prompt = (
            f"Payment data: {json.dumps(payment_data)}\n\n"
            "Assess fraud risk based on amount, frequency, employee history, etc."
        )

        response = await self._call(user_prompt, system=system_prompt)
        if not response:
            return None

        try:
            result = json.loads(response)
            if "risk_score" in result and isinstance(result["risk_score"], (int, float)):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

        return None

    async def generate_report(
        self,
        company_data: dict[str, Any],
        metrics: dict[str, Any],
    ) -> str | None:
        """Сценарий 3: Генерация отчёта для компании.

        Возвращает markdown-отчёт.
        При ошибке AI возвращает None → фоллбэк на простую таблицу.
        """
        system_prompt = (
            "You are a corporate benefits analytics assistant. "
            "Generate a concise markdown report based on company metrics."
        )

        user_prompt = (
            f"Company: {company_data.get('name')}\n\n"
            f"Metrics: {json.dumps(metrics, indent=2)}\n\n"
            "Generate a brief analytics report in markdown format with insights and recommendations."
        )

        response = await self._call(user_prompt, system=system_prompt)
        return response


# Глобальный экземпляр
_ai_service = AIService()


async def get_benefit_recommendations(
    employee_profile: dict[str, Any],
    available_benefits: list[dict[str, Any]],
) -> list[str] | None:
    """Обёртка для удобства: рекомендации льгот."""
    return await _ai_service.recommend_benefits(employee_profile, available_benefits)


async def assess_fraud_risk(payment_data: dict[str, Any]) -> dict[str, Any] | None:
    """Обёртка для удобства: оценка fraud."""
    return await _ai_service.assess_fraud(payment_data)


async def generate_company_report(
    company_data: dict[str, Any],
    metrics: dict[str, Any],
) -> str | None:
    """Обёртка для удобства: генерация отчёта."""
    return await _ai_service.generate_report(company_data, metrics)
