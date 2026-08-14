"""Генерация промокодов (NEXUS30 §12).

Формат: PREFIX-XXXXX-XXXXX
  PREFIX — 3 буквы из названия merchant (или категории, если название короткое)
  XXXXX  — crypto-random из безошибочного алфавита

Алфавит исключает 0/O/1/I/L: код читают вслух и вводят руками у мерчанта.
Энтропия: 10 символов × log2(31) ≈ 49.5 бит — достаточно против угадывания,
а уникальность в БД гарантирует unique constraint на code.

Запрещённые форматы из ТЗ: PROMO123, USER-42, BENEFIT-1 — предсказуемы.
"""

import re
import secrets

__all__ = ["generate_promo_code", "make_prefix", "CODE_ALPHABET"]

# Без 0, O, 1, I, L — визуально неоднозначные символы.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

GROUP_LENGTH = 5
GROUP_COUNT = 2


def make_prefix(source: str, fallback: str = "PRM") -> str:
    """Собрать 3-буквенный префикс из названия merchant/категории.

    'Fitness Zone' → 'FIT', 'IT Academy' → 'ITA', '' → 'PRM'
    """
    letters = re.sub(r"[^A-Za-z]", "", source).upper()
    if len(letters) >= 3:
        return letters[:3]
    if letters:
        return (letters + fallback)[:3]
    return fallback


def _random_group() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(GROUP_LENGTH))


def generate_promo_code(prefix_source: str = "") -> str:
    """Сгенерировать промокод вида FIT-8XK29-QJ4M7."""
    prefix = make_prefix(prefix_source)
    groups = [_random_group() for _ in range(GROUP_COUNT)]
    return "-".join([prefix, *groups])
