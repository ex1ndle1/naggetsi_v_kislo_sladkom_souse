"""Утилита для pagination: единообразный offset/limit с метаданными (ТЗ §22)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["Page", "PageMeta", "PageParams", "build_page", "paginate"]


class PageParams(BaseModel):
    """Query-параметры пагинации."""

    page: int = Field(default=1, ge=1, description="Номер страницы (начиная с 1)")
    page_size: int = Field(default=20, ge=1, le=100, description="Размер страницы")


class PageMeta(BaseModel):
    """Метаданные страницы."""

    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class Page[T](BaseModel):
    """Страница результатов с метаданными."""

    items: list[T]
    meta: PageMeta


def build_page[T](items: list[T], params: PageParams, total_items: int) -> Page[T]:
    """Обернуть готовый список в Page.

    Нужно там, где ответ собирается из связей вручную (история промокодов,
    аналитика) и `paginate` неприменим: метаданные страницы должны считаться в
    одном месте, иначе `has_next` будет вычисляться по-разному в разных роутерах.
    """
    total_pages = (total_items + params.page_size - 1) // params.page_size if total_items else 0
    return Page(
        items=items,
        meta=PageMeta(
            page=params.page,
            page_size=params.page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
        ),
    )


async def paginate[T](
    session: AsyncSession,
    stmt: Select[tuple[T]],
    params: PageParams,
) -> Page[T]:
    """Применяет offset/limit к запросу и возвращает результат с метаданными.

    Args:
        session: Сессия БД.
        stmt: SELECT-запрос без limit/offset.
        params: Параметры пагинации.

    Returns:
        Страница результатов с метаинформацией.
    """
    # Считаем общее количество строк.
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_items = (await session.execute(count_stmt)).scalar_one()

    # Применяем offset/limit.
    offset = (params.page - 1) * params.page_size
    result = await session.execute(stmt.limit(params.page_size).offset(offset))
    items = list(result.scalars().all())

    return build_page(items, params, total_items)
