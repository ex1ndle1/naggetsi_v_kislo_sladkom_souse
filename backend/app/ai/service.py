"""AI-сценарии NEXUS30 §17-§19.

1. Консьерж сотрудника — ранжирование каталога, доступного его тарифу.
2. Ассистент мерчанта — черновик описания льготы.
3. Отчёт для компании — рекомендации по агрегатам занятости мест и активности.

Fraud-скоринг удалён вместе с платёжным доменом: противодействие злоупотреблениям
в NEXUS30 детерминированное (лимиты, проверки §14, rate-limit, аудит), а не
вероятностное. LLM не участвует в решениях о доступе.

Общий принцип: модель никогда не расширяет права. Консьерж получает allowlist из
SQL-выборки и всё, что вне него, отбрасывается; ассистент мерчанта отдаёт черновик,
который публикуется обычным CRUD после ревью человеком.
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.ai.provider import LLMProvider, LLMUnavailableError, get_llm_provider
from app.core.enums import BenefitCategory
from app.core.logging import get_logger

__all__ = [
    "ConciergeResult",
    "MerchantDraft",
    "OfferDraftResult",
    "company_insights",
    "generate_offer_draft",
    "rank_benefits_for_employee",
]

logger = get_logger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


def _extract_json(text: str) -> Any:
    """Достать JSON из ответа модели.

    Модели охотно оборачивают JSON в ```-блоки и пояснения, поэтому берём первый
    сбалансированный фрагмент, а не парсим строку целиком.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = _JSON_BLOCK.search(text)
    if not match:
        raise ValueError("no JSON found in model response")
    return json.loads(match.group(0))


class ConciergeResult(BaseModel):
    """Результат сценария 1."""

    benefit_ids: list[UUID]
    reasoning: str | None = None
    ai_used: bool


class MerchantDraft(BaseModel):
    """Черновик льготы от модели. Не публикуется автоматически."""

    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10, max_length=4000)
    category: BenefitCategory
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("tags")
    @classmethod
    def _trim_tags(cls, value: list[str]) -> list[str]:
        return [tag.strip()[:32] for tag in value if tag.strip()]


class OfferDraftResult(BaseModel):
    """Ответ сценария 2 с признаком, участвовала ли модель."""

    draft: MerchantDraft
    ai_used: bool


_CONCIERGE_SYSTEM = (
    "You are a corporate benefits concierge. "
    "You receive a catalog of benefits the employee is ELIGIBLE for and a query. "
    "Rank the most relevant ones. "
    'Respond with JSON only: {"benefit_ids": ["<id>", ...], "reasoning": "<one sentence>"}. '
    "Use only ids present in the catalog. Never invent ids."
)

_MERCHANT_SYSTEM = (
    "You are a marketing assistant for a merchant publishing a corporate benefit offer. "
    "Write a clear, factual title and description. Do not invent discounts, prices or dates. "
    'Respond with JSON only: {"title": "...", "description": "...", '
    '"category": "<one of the allowed categories>", "tags": ["..."]}.'
)

_INSIGHTS_SYSTEM = (
    "You are an HR analytics assistant for a corporate benefits platform. "
    "You receive aggregated metrics about seat allocation and benefit usage. "
    "Write a short markdown report: what stands out, and 2-4 concrete recommendations. "
    "Base every statement on the numbers provided. Do not invent data."
)


async def rank_benefits_for_employee(
    *,
    query: str,
    eligible: list[dict[str, Any]],
    employee_context: dict[str, Any],
    provider: LLMProvider | None = None,
) -> ConciergeResult:
    """Сценарий 1: ранжирование уже отфильтрованного каталога.

    ``eligible`` формируется вызывающим кодом через ``visible_benefits_query`` — этот
    список и есть граница прав. Модель может только переупорядочить его; ID вне
    списка отбрасываются. При недоступности LLM возвращается исходный порядок из SQL
    (``ai_used=False``), то есть функциональность деградирует, а не падает.
    """
    allowlist = {str(item["id"]) for item in eligible}
    sql_order = [UUID(str(item["id"])) for item in eligible]

    if not eligible:
        return ConciergeResult(benefit_ids=[], ai_used=False)

    llm = provider or get_llm_provider()
    prompt = (
        f"Employee context: {json.dumps(employee_context, ensure_ascii=False)}\n\n"
        f"Query: {query}\n\n"
        f"Eligible catalog: {json.dumps(eligible, ensure_ascii=False)}"
    )

    try:
        raw = await llm.complete(prompt, system=_CONCIERGE_SYSTEM)
        parsed = _extract_json(raw)
    except (LLMUnavailableError, ValueError, json.JSONDecodeError) as exc:
        logger.info("concierge_fallback", reason=type(exc).__name__)
        return ConciergeResult(benefit_ids=sql_order, ai_used=False)

    if isinstance(parsed, list):
        parsed = {"benefit_ids": parsed}
    if not isinstance(parsed, dict):
        logger.info("concierge_fallback", reason="unexpected_payload_type")
        return ConciergeResult(benefit_ids=sql_order, ai_used=False)

    ranked: list[UUID] = []
    seen: set[str] = set()
    for candidate in parsed.get("benefit_ids") or []:
        candidate_str = str(candidate)
        # Отбрасываем всё, чего не было в разрешённой выборке: галлюцинация модели
        # не должна превращаться в доступ к чужой льготе.
        if candidate_str not in allowlist or candidate_str in seen:
            continue
        seen.add(candidate_str)
        ranked.append(UUID(candidate_str))

    if not ranked:
        logger.info("concierge_fallback", reason="no_valid_ids")
        return ConciergeResult(benefit_ids=sql_order, ai_used=False)

    reasoning = parsed.get("reasoning")
    return ConciergeResult(
        benefit_ids=ranked,
        reasoning=str(reasoning)[:500] if reasoning else None,
        ai_used=True,
    )


async def generate_offer_draft(
    *,
    merchant_name: str,
    hint: str,
    provider: LLMProvider | None = None,
) -> OfferDraftResult | None:
    """Сценарий 2: черновик описания льготы.

    Возвращает None, если модель недоступна или ответ не проходит валидацию: пустой
    черновик лучше выдуманного. Скидки, даты и лимиты модель не задаёт — их
    заполняет мерчант, потому что это условия договора, а не текст.
    """
    llm = provider or get_llm_provider()
    categories = ", ".join(category.value for category in BenefitCategory)
    prompt = (
        f"Merchant: {merchant_name}\nAllowed categories: {categories}\n\nMerchant's description of the offer: {hint}"
    )

    try:
        raw = await llm.complete(prompt, system=_MERCHANT_SYSTEM)
        parsed = _extract_json(raw)
        draft = MerchantDraft.model_validate(parsed)
    except (LLMUnavailableError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        logger.info("offer_draft_unavailable", reason=type(exc).__name__)
        return None

    return OfferDraftResult(draft=draft, ai_used=True)


async def company_insights(
    *,
    metrics: dict[str, Any],
    provider: LLMProvider | None = None,
) -> str | None:
    """Сценарий 3: текстовые рекомендации по агрегатам компании.

    На вход идут только агрегаты из ``analytics.service`` — без email'ов, имён и
    промокодов. Возвращает None при недоступности модели; числовая аналитика
    остаётся доступной вызывающему коду независимо от этого.
    """
    llm = provider or get_llm_provider()
    prompt = f"Aggregated company metrics:\n{json.dumps(metrics, ensure_ascii=False, indent=2)}"

    try:
        return await llm.complete(prompt, system=_INSIGHTS_SYSTEM)
    except LLMUnavailableError as exc:
        logger.info("company_insights_unavailable", reason=type(exc).__name__)
        return None
