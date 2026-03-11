from __future__ import annotations

"""
Shared GrailCatalog lookup helpers used by both stash_service and grail_service.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import GrailCatalog
from backend.services.item_parsing import ParsedItem

QUALITY_UNIQUE = 7
QUALITY_SET = 5


async def build_catalog_lookup(
    session: AsyncSession,
    all_page_items: list[list[ParsedItem]],
) -> dict[tuple, GrailCatalog]:
    """
    Batch-fetch GrailCatalog entries for all unique/set items across multiple pages.
    Returns a dict keyed by ("unique", unique_id) or ("set", set_id).
    """
    unique_ids: set[int] = set()
    set_ids: set[int] = set()

    for page_items in all_page_items:
        for item in page_items:
            if item.quality == QUALITY_UNIQUE and item.unique_id is not None:
                unique_ids.add(item.unique_id)
            elif item.quality == QUALITY_SET and item.set_id is not None:
                set_ids.add(item.set_id)

    lookup: dict[tuple, GrailCatalog] = {}

    if unique_ids:
        result = await session.execute(
            select(GrailCatalog).where(
                GrailCatalog.quality == "unique",
                GrailCatalog.unique_id.in_(unique_ids),
            )
        )
        for cat in result.scalars().all():
            lookup[("unique", cat.unique_id)] = cat

    if set_ids:
        result = await session.execute(
            select(GrailCatalog).where(
                GrailCatalog.quality == "set",
                GrailCatalog.set_id.in_(set_ids),
            )
        )
        for cat in result.scalars().all():
            lookup[("set", cat.set_id)] = cat

    return lookup


async def lookup_catalog_item(
    session: AsyncSession,
    item: ParsedItem,
) -> GrailCatalog | None:
    """
    Look up a single ParsedItem in GrailCatalog.
    Matches unique items by unique_id, set items by set_id only (item_code not required).
    """
    if item.quality == QUALITY_UNIQUE and item.unique_id is not None:
        result = await session.execute(
            select(GrailCatalog).where(
                GrailCatalog.quality == "unique",
                GrailCatalog.unique_id == item.unique_id,
            )
        )
        return result.scalar_one_or_none()

    if item.quality == QUALITY_SET and item.set_id is not None:
        result = await session.execute(
            select(GrailCatalog).where(
                GrailCatalog.quality == "set",
                GrailCatalog.set_id == item.set_id,
            )
        )
        return result.scalar_one_or_none()

    return None
