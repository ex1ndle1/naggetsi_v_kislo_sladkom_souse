"""Telegram-бот для проверки промокодов Наггетсы30.

Команды:
  /start         — приветствие и инструкция
  /check CODE    — проверить промокод по коду
  /activate CODE — погасить промокод
  Любое сообщение из одного слова ≤ 20 символов воспринимается как код для проверки.

Бот может проверять статус и погашать промокоды. Альтернатива — погашение через веб-кабинет мерчанта.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime

import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ── Конфигурация из окружения ───────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BACKEND_URL: str = os.environ.get("BACKEND_URL", "http://backend:8000")
BOT_API_KEY: str = os.environ.get("BOT_API_KEY", "")

_HEADERS = {"X-Bot-Api-Key": BOT_API_KEY, "Content-Type": "application/json"}

# ── Aiogram ──────────────────────────────────────────────────────────────────
# Токен проверяется в main(): Bot() создаётся лениво, чтобы пустое значение
# давало понятный лог, а не ValidationError на импорте.
dp = Dispatcher()


# ── Вспомогательные функции ──────────────────────────────────────────────────

async def lookup_code(code: str) -> str:
    """Вызывает /api/v1/bot/promo/{code} и формирует читаемый ответ.

    Не пробрасывает текст ошибки из API в чат: пользователь получает
    аккуратное сообщение, а детали видны только в логах контейнера.
    """
    url = f"{BACKEND_URL}/api/v1/bot/promo/{code.upper().strip()}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=_HEADERS)
    except httpx.RequestError as exc:
        log.error("backend unreachable: %s", exc)
        return "⚠️ Не удалось связаться с сервером. Попробуйте позже."

    if resp.status_code == 404:
        return f"❌ Промокод <b>{code.upper()}</b> не найден."

    if resp.status_code == 403:
        log.error("bot api key rejected or not configured")
        return "⚠️ Бот не настроен. Обратитесь к администратору."

    if resp.status_code != 200:
        log.error("unexpected status %s from backend", resp.status_code)
        return "⚠️ Ошибка при проверке кода. Попробуйте позже."

    data = resp.json()
    title = data.get("benefit_title", "Льгота")
    status = data.get("status", "UNKNOWN")
    redeemable = data.get("is_redeemable", False)
    expires_at_raw: str | None = data.get("expires_at")
    redeemed_at_raw: str | None = data.get("redeemed_at")
    discount_note: str | None = data.get("employee_plan_discount_note")

    expires_str = ""
    if expires_at_raw:
        try:
            dt = datetime.fromisoformat(expires_at_raw.replace("Z", "+00:00"))
            expires_str = dt.strftime("%d.%m.%Y")
        except ValueError:
            expires_str = expires_at_raw[:10]

    redeemed_str = ""
    if redeemed_at_raw:
        try:
            dt = datetime.fromisoformat(redeemed_at_raw.replace("Z", "+00:00"))
            redeemed_str = dt.strftime("%d.%m.%Y")
        except ValueError:
            redeemed_str = redeemed_at_raw[:10]

    if status == "REDEEMED":
        return (
            f"🔴 Промокод <b>{code.upper()}</b> уже погашен.\n"
            f"Льгота: {title}\n"
            f"Погашен: {redeemed_str or '—'}"
        )
    if status == "EXPIRED":
        return (
            f"⏳ Промокод <b>{code.upper()}</b> истёк.\n"
            f"Льгота: {title}\n"
            f"Истёк: {expires_str or '—'}"
        )
    if status == "REVOKED":
        return f"🚫 Промокод <b>{code.upper()}</b> отозван."

    if redeemable:
        discount_line = f"\nСкидка: <b>{discount_note}</b>" if discount_note else ""
        return (
            f"✅ Промокод <b>{code.upper()}</b> действителен.\n"
            f"Льгота: {title}{discount_line}\n"
            f"Действует до: {expires_str or '—'}"
        )

    # Статус ISSUED, но is_redeemable=False (например, ещё не наступил valid_from)
    return (
        f"⚠️ Промокод <b>{code.upper()}</b> пока нельзя погасить.\n"
        f"Льгота: {title}\n"
        f"Статус: {status}"
    )


def is_bare_code(text: str) -> bool:
    """Короткое слово без пробелов — скорее всего код, а не команда."""
    return bool(text) and " " not in text.strip() and len(text.strip()) <= 24


async def redeem_code(code: str) -> str:
    """Погашает промокод через /api/v1/bot/promo/{code}/redeem."""
    url = f"{BACKEND_URL}/api/v1/bot/promo/{code.upper().strip()}/redeem"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, headers=_HEADERS)
    except httpx.RequestError as exc:
        log.error("backend unreachable: %s", exc)
        return "⚠️ Не удалось связаться с сервером. Попробуйте позже."

    if resp.status_code == 404:
        return f"❌ Промокод <b>{code.upper()}</b> не найден."

    if resp.status_code == 403:
        log.error("bot api key rejected or not configured")
        return "⚠️ Бот не настроен. Обратитесь к администратору."

    if resp.status_code == 400:
        # Код уже погашен, истёк или отозван
        return f"⚠️ Промокод <b>{code.upper()}</b> уже погашен, истёк или недоступен."

    if resp.status_code != 200:
        log.error("unexpected status %s from backend", resp.status_code)
        return "⚠️ Ошибка при погашении кода. Попробуйте позже."

    data = resp.json()
    message = data.get("message", f"Промокод {code.upper()} погашен!")
    return f"✅ {message}"


# ── Хендлеры ────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    await message.answer(
        "👋 Привет! Я бот для проверки и активации промокодов <b>Наггетсы30</b>.\n\n"
        "Команды:\n"
        "<code>/check CODE</code> — проверить статус промокода\n"
        "<code>/activate CODE</code> — погасить промокод\n\n"
        "Или просто напиши код сообщением для проверки.",
        parse_mode="HTML",
    )


@dp.message(Command("check"))
async def cmd_check(message: types.Message) -> None:
    if not message.text:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Укажи код после команды:\n<code>/check ABCDEF-1234</code>",
            parse_mode="HTML",
        )
        return
    code = parts[1].strip()
    await message.answer(await lookup_code(code), parse_mode="HTML")


@dp.message(Command("activate"))
async def cmd_activate(message: types.Message) -> None:
    """Погасить промокод одной командой: /activate CODE"""
    if not message.text:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "❓ Укажи код после команды:\n<code>/activate ABCDEF-1234</code>",
            parse_mode="HTML",
        )
        return
    code = parts[1].strip()
    await message.answer(await redeem_code(code), parse_mode="HTML")


@dp.message()
async def handle_text(message: types.Message) -> None:
    """Обработка произвольного сообщения — пробуем как промокод."""
    text = (message.text or "").strip()
    if not text:
        return
    if is_bare_code(text):
        await message.answer(await lookup_code(text), parse_mode="HTML")
    else:
        await message.answer(
            "Не понял. Отправь промокод или используй /check CODE.",
            parse_mode="HTML",
        )


# ── Запуск ──────────────────────────────────────────────────────────────────

async def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        log.error("TELEGRAM_BOT_TOKEN is not set — bot cannot start")
        raise SystemExit(1)
    if not BOT_API_KEY:
        log.warning("BOT_API_KEY is not set — /api/v1/bot/promo endpoint will reject all requests")
    log.info("Starting Наггетсы30 promo-check bot (polling)")
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await dp.start_polling(bot, handle_signals=True)


if __name__ == "__main__":
    asyncio.run(main())
