from typing import Any, Awaitable, Callable

from src.internal.agents.utils import normalize_tool_name
from src.internal.mentions.agent import run_entity_linking
from src.internal.mentions.state_utils import build_linked_mentions_from_candidates
from src.internal.schema_cache import SCHEMA_CACHE
from src.internal.utils import LOGGER
from src.schemas.mentions import DetailedMention
from src.schemas.query_generation import LinkedMentions


async def run_entity_linking_agent(
    *,
    ctx: Any,
    schema_id: str | None,
    question: str | None,
    model: str | None,
    current_mentions: list[DetailedMention],
    follow_up_message: str | None,
    send_event: Callable[[str, dict[str, Any]], Awaitable[None]],
) -> tuple[list[DetailedMention], LinkedMentions | None, str | None, str | None]:
    await send_event(
        "phase",
        {"name": "mention_pipeline", "status": "started"},
    )

    if not ctx:
        error_message = "Schema not found for mention pipeline."
        await send_event(
            "phase",
            {"name": "mention_pipeline", "status": "failed"},
        )
        await send_event(
            "error",
            {"message": error_message, "error_type": "mention_pipeline"},
        )
        return current_mentions, None, error_message, None

    try:
        schema_meta = SCHEMA_CACHE.get_meta(schema_id or "")

        # Stream mention-agent tool metadata to frontend, same envelope as query generation.
        async def _on_tool_calls(iteration: int, tool_calls: list[dict[str, Any]]):
            await send_event(
                "tool_calls",
                {
                    "iteration": iteration,
                    "calls": [
                        {
                            "id": call.get("id"),
                            "name": normalize_tool_name(
                                call["function"].get("name", "")
                            ),
                            "arguments": call["function"].get("arguments"),
                        }
                        for call in tool_calls
                    ],
                },
            )

        async def _on_tool_result(
            _: int,
            call_id: str | None,
            func_name: str,
            __: Any,
            observation_json: str,
        ):
            await send_event(
                "tool_result",
                {
                    "tool_call_id": call_id,
                    "name": func_name,
                    "result": observation_json,
                },
            )

        result = await run_entity_linking(
            ctx=ctx,
            question=question,
            model=model,
            max_iterations=50,
            max_message_history=50,
            rerank_fallback=True,
            allow_user_clarification=True,
            kg_description=(schema_meta.description if schema_meta else None),
            previous_mentions=current_mentions or None,
            follow_up_message=follow_up_message,
            on_tool_calls=_on_tool_calls,
            on_tool_result=_on_tool_result,
        )
    except Exception as error:
        error_message = str(error).strip() or error.__class__.__name__
        LOGGER.error("Mention pipeline failed unexpectedly: %s", str(error))
        await send_event(
            "phase",
            {"name": "mention_pipeline", "status": "failed"},
        )
        await send_event(
            "error",
            {"message": error_message, "error_type": "mention_pipeline"},
        )
        return current_mentions, None, error_message, None

    mentions = result.mentions
    linked_mentions = build_linked_mentions_from_candidates(mentions)
    linked_count = len(linked_mentions.mentions)
    total_mentions = len(mentions)

    await send_event(
        "phase",
        {
            "name": "mention_pipeline",
            "status": "finished",
            "mention_count": total_mentions,
            "linked_count": linked_count,
        },
    )
    await send_event(
        "mentions_detected",
        {
            "mentions": [mention.model_dump(mode="json") for mention in mentions],
            "message": "Mentions updated by tool agent.",
        },
    )
    await send_event(
        "linked_entities_ready",
        {
            "linked_count": linked_count,
            "unlinked_count": total_mentions - linked_count,
            "message": "Linked entities refreshed from mention agent output.",
        },
    )

    assistant_message = (result.assistant_message or "").strip() or None
    if assistant_message:
        await send_event(
            "agent_reply",
            {"message": assistant_message},
        )

    return mentions, linked_mentions, None, assistant_message
