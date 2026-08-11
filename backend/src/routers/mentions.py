import asyncio
from typing import List

from fastapi import APIRouter, HTTPException, status

from src.internal.mentions import process_mention
from src.internal.mentions.agent import run_entity_linking
from src.internal.mentions.extraction import (
    extract_keywords_from_mentions,
    extract_mentions,
)
from src.internal.schema_cache import SCHEMA_CACHE
from src.internal.utils import LOGGER
from src.schemas.mentions import DetailedMention, RequestMentions

router = APIRouter()


@router.post("", status_code=status.HTTP_200_OK, response_model=List[DetailedMention])
async def get_mentions(request: RequestMentions):
    LOGGER.info(
        f"Mentions request schema_id={request.schema_id} model={request.model} query={request.query}"
    )
    index = SCHEMA_CACHE.get(request.schema_id)
    if not index:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema with id {request.schema_id} not found",
        )

    mentions: List[DetailedMention] = await extract_mentions(
        q=request.query, model=request.model, ctx=index
    )
    LOGGER.info(f"Extracted mentions {mentions}")

    keyword_list = extract_keywords_from_mentions(mentions, min_length=1)

    await asyncio.gather(
        *[
            process_mention(
                index, request.query, mention, keyword_list, limit=request.limit
            )
            for mention in mentions
        ]
    )

    LOGGER.info(f"Mentions request completed count={len(mentions)}")
    return mentions


@router.post(
    "/agent", status_code=status.HTTP_200_OK, response_model=List[DetailedMention]
)
async def get_mentions_with_agent(request: RequestMentions):
    LOGGER.info(
        f"Mentions request schema_id={request.schema_id} model={request.model} query={request.query}"
    )
    index = SCHEMA_CACHE.get(request.schema_id)
    meta = SCHEMA_CACHE.get_meta(request.schema_id)
    if not index:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema with id {request.schema_id} not found",
        )
    result = await run_entity_linking(
        ctx=index,
        question=request.query,
        model=request.model,
        max_iterations=50,
        rerank_fallback=True,
        allow_user_clarification=False,
        kg_description=(meta.description if meta else None),
    )
    LOGGER.info("Mentions agent request completed count=%s", len(result.mentions))
    return result.mentions
