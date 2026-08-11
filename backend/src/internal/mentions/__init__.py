import asyncio
from typing import List

from src.internal.utils import LOGGER
from src.schemas.mentions import DetailedMention
from src.schemas.schema_index import SchemaIndex

from .context import onehop_readable
from .generation import get_candidates_with_fallback
from .ranking import bm25_score


async def process_mention(
    idx: SchemaIndex,
    query: str,
    mention: DetailedMention,
    keywords: List[str],
    limit: int,
):
    """Given a mention, fetch candidates and rank them."""
    LOGGER.info(f"Process mention start text={mention.text} type={mention.type}")
    candidates = await get_candidates_with_fallback(idx, mention, limit)

    if not candidates:
        LOGGER.info(f"Process mention no candidates text={mention.text}")
        mention.candidates = []
        return

    asyncios_tasks = [
        onehop_readable(idx, candidate.uri, keywords=keywords, limit_each=100) for candidate in candidates
    ]
    for candidate, context in zip(
        candidates, await asyncio.gather(*asyncios_tasks), strict=True
    ):
        candidate.context = context

    mention.candidates = bm25_score(idx, keywords, candidates)
    LOGGER.info(
        f"Process mention done text={mention.text} candidates={len(mention.candidates)}"
    )
