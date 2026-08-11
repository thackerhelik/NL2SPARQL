import json
from typing import Any, Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.internal.agents.entity_linking_agent import run_entity_linking_agent
from src.internal.agents.policy_agent import (
    AgentMessageDecision,
    decide_agent_message_action,
)
from src.internal.agents.query_execution_agent import run_query_generation_agent
from src.internal.mentions.state_utils import (
    build_linked_mentions_from_candidates,
    merge_mentions_with_existing_candidates,
    to_detailed_mentions,
)
from src.internal.schema_cache import SCHEMA_CACHE
from src.internal.utils import LOGGER
from src.schemas.mentions import DetailedMention, Mention
from src.schemas.query_generation import LinkedMention, LinkedMentions

router = APIRouter()


class AgentChatRequest(BaseModel):
    type: str
    question: str | None = None
    message: str | None = None
    current_query: str | None = None
    mentions: list[Mention] | None = None
    detailed_mentions: list[DetailedMention] | None = None
    linked_mentions: list[LinkedMention] | None = None
    schema_id: str | None = None
    model: str | None = None


def _log_ws_diag(direction: Literal["in", "out", "state"], **fields: Any) -> None:
    payload = {"direction": direction, **fields}
    payload = {k: v for k, v in payload.items() if v is not None}
    LOGGER.info("[ws] %s", json.dumps(payload, ensure_ascii=False))


async def _send_event(websocket: WebSocket, event_type: str, payload: dict[str, Any]):
    log_fields: dict[str, Any] = {
        "event_type": event_type,
        "stage": payload.get("stage"),
        "error_type": payload.get("error_type"),
    }

    if event_type == "phase":
        log_fields["phase_name"] = payload.get("name")
        log_fields["phase_status"] = payload.get("status")
    elif event_type == "tool_calls":
        calls = payload.get("calls")
        if isinstance(calls, list):
            log_fields["tool_calls"] = [
                {
                    "name": call.get("name"),
                    "arguments": call.get("arguments"),
                }
                for call in calls
            ]
            log_fields["tool_call_count"] = len(calls)
        log_fields["iteration"] = payload.get("iteration")

    _log_ws_diag(
        "out",
        **log_fields,
    )
    await websocket.send_json({"type": event_type, "payload": payload})


def _append_agent_memory(
    memory: list[dict[str, str]],
    role: Literal["user", "assistant", "system"],
    text: str,
) -> None:
    cleaned = text.strip()
    if not cleaned:
        return
    memory.append({"role": role, "content": cleaned})


async def _send_stage_context(
    websocket: WebSocket,
    *,
    stage: str,
    note: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {"stage": stage}
    if note:
        cleaned_note = note.strip()
        if cleaned_note:
            payload["note"] = cleaned_note
    if extra:
        payload.update(extra)

    await _send_event(websocket, "stage_context", payload)


@router.websocket("/ws")
async def agent_chat(websocket: WebSocket):
    # Open session and emit initial ready state.
    await websocket.accept()
    await _send_event(websocket, "connection", {"status": "ready"})

    initial_request: AgentChatRequest | None = None
    session_mentions: list[Any] | None = None
    session_linked_mentions: LinkedMentions | None = None
    current_client_query: str | None = None
    agent_message_memory: list[dict[str, str]] = []
    last_failed_stage: str | None = None
    last_failed_error: str | None = None

    try:
        while True:
            # Parse incoming websocket request envelope.
            data = await websocket.receive_json()
            request = AgentChatRequest.model_validate(data)
            _log_ws_diag(
                "in",
                request_type=request.type,
                has_question=bool(request.question),
                has_message=bool(request.message),
                has_mentions=bool(request.mentions),
                has_detailed_mentions=bool(request.detailed_mentions),
                has_linked_mentions=bool(request.linked_mentions),
            )

            if request.type == "start":
                # Start initializes or restores a session context.
                if initial_request is not None:
                    await _send_event(
                        websocket,
                        "error",
                        {
                            "message": "Session already active. Send feedback to revise mentions instead of starting a new query."
                        },
                    )
                    continue

                if not request.question or not request.schema_id or not request.model:
                    await _send_event(
                        websocket,
                        "error",
                        {"message": "Missing question, schema_id, or model for start."},
                    )
                    continue

                ctx = SCHEMA_CACHE.get(request.schema_id)

                agent_message_memory = []
                initial_request = request
                session_mentions = []
                session_linked_mentions = None
                current_client_query = request.current_query
                _log_ws_diag(
                    "state",
                    transition="start_initialized",
                    schema_id=request.schema_id,
                    model=request.model,
                )

                restored_mentions: list[DetailedMention] = []
                if request.detailed_mentions is not None:
                    restored_mentions = request.detailed_mentions
                elif request.mentions is not None:
                    restored_mentions = to_detailed_mentions(request.mentions)

                if restored_mentions:
                    # Restore path skips fresh extraction.
                    session_mentions = restored_mentions
                    if request.linked_mentions:
                        session_linked_mentions = LinkedMentions(
                            mentions=request.linked_mentions
                        )
                    else:
                        session_linked_mentions = build_linked_mentions_from_candidates(
                            restored_mentions
                        )

                    await _send_stage_context(
                        websocket,
                        stage="restoring",
                        note="Session restored.",
                    )
                    continue

                await _send_stage_context(
                    websocket,
                    stage="mention_extraction",
                    note="New chat session started.",
                )
                # Fresh session path starts mention extraction/linking with tool agent.
                (
                    mentions,
                    linked_mentions,
                    extraction_error,
                    mention_agent_message,
                ) = await run_entity_linking_agent(
                    ctx=ctx,
                    schema_id=request.schema_id,
                    question=request.question,
                    model=request.model,
                    current_mentions=[],
                    follow_up_message=None,
                    send_event=lambda event_type, payload: _send_event(
                        websocket, event_type, payload
                    ),
                )
                if extraction_error:
                    last_failed_stage = "mention_extraction"
                    last_failed_error = extraction_error
                    await _send_event(
                        websocket,
                        "agent_reply",
                        {
                            "message": "Mention extraction failed. Send a follow-up message (for example, continue) to retry.",
                        },
                    )
                    continue

                last_failed_stage = None
                last_failed_error = None

                session_mentions = mentions
                session_linked_mentions = linked_mentions
                if mention_agent_message:
                    _append_agent_memory(
                        agent_message_memory, "assistant", mention_agent_message
                    )
                continue

            if request.type == "set_mentions":
                # Sync mention edits from frontend selection UI.
                if initial_request is None or session_mentions is None:
                    await _send_event(
                        websocket,
                        "agent_reply",
                        {
                            "message": "Session is still restoring. Mention sync skipped for now; retry in a moment."
                        },
                    )
                    continue

                if request.mentions is None:
                    await _send_event(
                        websocket,
                        "error",
                        {"message": "Missing mentions payload for set_mentions."},
                    )
                    continue

                await _send_stage_context(
                    websocket,
                    stage="mention_revision",
                    note="Applying mention edits from frontend selection.",
                )
                revised_mentions = to_detailed_mentions(request.mentions)
                LOGGER.info(
                    "[set_mentions] payload_count=%s payload_texts=%s",
                    len(revised_mentions),
                    [mention.text for mention in revised_mentions],
                )
                LOGGER.info(
                    "[set_mentions] session_before_count=%s session_before_texts=%s",
                    len(session_mentions),
                    [mention.text for mention in session_mentions],
                )
                merged_mentions, _, _ = merge_mentions_with_existing_candidates(
                    existing_mentions=session_mentions,
                    revised_mentions=revised_mentions,
                )
                LOGGER.info(
                    "[set_mentions] merged_count=%s merged_texts=%s",
                    len(merged_mentions),
                    [mention.text for mention in merged_mentions],
                )
                linked_mentions = build_linked_mentions_from_candidates(merged_mentions)
                linked_count = len(linked_mentions.mentions)
                total_mentions = len(merged_mentions)
                await _send_event(
                    websocket,
                    "mentions_detected",
                    {
                        "mentions": [
                            mention.model_dump(mode="json")
                            for mention in merged_mentions
                        ],
                        "message": "Mentions synced from frontend.",
                    },
                )
                await _send_event(
                    websocket,
                    "linked_entities_ready",
                    {
                        "linked_count": linked_count,
                        "unlinked_count": total_mentions - linked_count,
                        "message": "Linked entities refreshed from your mention selections.",
                    },
                )
                session_mentions = merged_mentions
                session_linked_mentions = linked_mentions
                continue

            if request.type == "set_query":
                # Sync latest editor query into session state.
                if initial_request is None:
                    await _send_event(
                        websocket,
                        "agent_reply",
                        {
                            "message": "No active session yet. Query sync skipped.",
                        },
                    )
                    continue

                current_client_query = (request.current_query or "").strip() or None
                initial_request = initial_request.model_copy(
                    update={"current_query": current_client_query}
                )
                await _send_event(
                    websocket,
                    "query_synced",
                    {"current_query": current_client_query},
                )
                continue

            if request.type == "agent_message":
                # Agent message uses policy classification before dispatch.
                if initial_request is None:
                    if request.question and request.schema_id and request.model:
                        initial_request = AgentChatRequest(
                            type="start",
                            question=request.question,
                            schema_id=request.schema_id,
                            model=request.model,
                        )
                        session_mentions = []
                        session_linked_mentions = None
                        current_client_query = None
                        agent_message_memory = []
                        await _send_event(
                            websocket,
                            "agent_reply",
                            {
                                "message": "Session context initialized from your message. Proceeding with mention extraction.",
                            },
                        )
                    else:
                        await _send_event(
                            websocket,
                            "agent_reply",
                            {
                                "message": "No active session yet. Please send a start request (question + schema + model) or use the main input send flow.",
                            },
                        )
                        continue

                if session_mentions is None:
                    session_mentions = []

                user_message = (request.message or request.question or "").strip()
                if not user_message:
                    await _send_event(
                        websocket,
                        "error",
                        {"message": "Missing text for agent message."},
                    )
                    continue
                _append_agent_memory(agent_message_memory, "user", user_message)

                try:
                    schema_meta = SCHEMA_CACHE.get_meta(initial_request.schema_id or "")
                    schema_name = schema_meta.name if schema_meta is not None else None
                    schema_description = (
                        schema_meta.description if schema_meta is not None else None
                    )

                    decision = await decide_agent_message_action(
                        model=initial_request.model,
                        question=initial_request.question,
                        mentions=session_mentions,
                        linked_mentions=session_linked_mentions,
                        has_previous_query=bool(current_client_query),
                        last_failed_stage=last_failed_stage,
                        last_failed_error=last_failed_error,
                        message_memory=agent_message_memory,
                        user_message=user_message,
                        schema_name=schema_name,
                        schema_description=schema_description,
                    )
                except Exception as e:
                    LOGGER.error("Agent message decision failed: %s", str(e))
                    decision = AgentMessageDecision(
                        action="generate_query",
                        reply="Proceeding with query generation using current session context.",
                    )

                await _send_event(
                    websocket,
                    "agent_decision",
                    {
                        "action": decision.action,
                        "reply": decision.reply,
                    },
                )
                if decision.reply:
                    _append_agent_memory(
                        agent_message_memory, "assistant", decision.reply
                    )

                if decision.action == "reply_user":
                    # Clarification-only branch.
                    await _send_event(
                        websocket,
                        "agent_reply",
                        {
                            "message": decision.reply
                            or "I'm not fully sure what you want next. Should I update mentions/linking or generate/refine the query?",
                        },
                    )
                    continue

                ctx = SCHEMA_CACHE.get(initial_request.schema_id or "")
                inferred_user_intent = (decision.user_intent or user_message).strip()

                if decision.action == "mention_pipeline":
                    # Mention pipeline branch: extraction/revision/linking.
                    await _send_stage_context(
                        websocket,
                        stage="mention_revision",
                        note="Applying mention updates with tool agent.",
                    )
                    (
                        session_mentions,
                        session_linked_mentions,
                        mention_error,
                        mention_agent_message,
                    ) = await run_entity_linking_agent(
                        ctx=ctx,
                        schema_id=initial_request.schema_id,
                        question=initial_request.question,
                        model=initial_request.model,
                        current_mentions=session_mentions,
                        follow_up_message=inferred_user_intent,
                        send_event=lambda event_type, payload: _send_event(
                            websocket, event_type, payload
                        ),
                    )

                    if mention_error:
                        last_failed_stage = "mention_pipeline"
                        last_failed_error = mention_error
                        _append_agent_memory(
                            agent_message_memory,
                            "system",
                            f"Mention pipeline failed: {mention_error}",
                        )
                        continue

                    if mention_agent_message:
                        _append_agent_memory(
                            agent_message_memory, "assistant", mention_agent_message
                        )

                    if (
                        session_linked_mentions is not None
                        and session_linked_mentions.mentions
                    ):
                        last_failed_stage = None
                        last_failed_error = None
                    elif session_mentions is not None and session_mentions:
                        last_failed_stage = None
                        last_failed_error = None
                    else:
                        last_failed_stage = "mention_pipeline"
                        last_failed_error = (
                            "Mention pipeline did not produce usable state."
                        )
                    continue

                if decision.action == "generate_query":
                    # Query branch: generate/refine and optionally execute.
                    query_edit_intent = (
                        inferred_user_intent if current_client_query else None
                    )
                    current_client_query = await run_query_generation_agent(
                        websocket=websocket,
                        ctx=ctx,
                        request=initial_request,
                        linked_mentions=session_linked_mentions,
                        previous_query=current_client_query,
                        edit_instructions=query_edit_intent,
                        send_stage_context=_send_stage_context,
                        send_event=_send_event,
                    )
                    if current_client_query is None:
                        last_failed_stage = "query_generation"
                        last_failed_error = "Query generation failed."
                        _append_agent_memory(
                            agent_message_memory,
                            "system",
                            "Query generation failed and can be retried with current context.",
                        )
                    else:
                        last_failed_stage = None
                        last_failed_error = None
                        _append_agent_memory(
                            agent_message_memory,
                            "assistant",
                            "Query generation succeeded.",
                        )
                    continue

                await _send_event(
                    websocket,
                    "error",
                    {
                        "message": f"Unsupported policy action: {decision.action}",
                    },
                )
                continue

            await _send_event(
                websocket,
                "error",
                {"message": f"Unsupported message type: {request.type}"},
            )

    except WebSocketDisconnect:
        LOGGER.info("Agent websocket disconnected.")
