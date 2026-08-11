from typing import Any, Literal

from pydantic import BaseModel

from src.internal.llm import chat_message
from src.internal.mentions.state_utils import mentions_to_text
from src.internal.utils import LOGGER

MAX_AGENT_MEMORY = 16


class AgentMessageDecision(BaseModel):
    action: Literal[
        "mention_pipeline",
        "generate_query",
        "reply_user",
    ]
    reply: str | None = None
    user_intent: str | None = None


def _compact_message_memory_for_policy(
    memory: list[dict[str, str]],
) -> list[dict[str, str]]:
    # Keep only minimal valid chat history for policy prompts.
    filtered: list[dict[str, str]] = []
    for entry in memory:
        role = entry.get("role", "")
        content = (entry.get("content", "") or "").strip()
        if role not in {"user", "assistant", "system"}:
            continue
        if not content:
            continue
        filtered.append({"role": role, "content": content})

    if len(filtered) <= MAX_AGENT_MEMORY:
        return filtered
    return filtered[-MAX_AGENT_MEMORY:]


async def decide_agent_message_action(
    *,
    model: str,
    question: str,
    mentions: list[Any],
    linked_mentions: list[Any] | None,
    has_previous_query: bool,
    last_failed_stage: str | None,
    last_failed_error: str | None,
    message_memory: list[dict[str, str]],
    user_message: str,
    schema_name: str | None = None,
    schema_description: str | None = None,
) -> AgentMessageDecision:
    # Derive lightweight session counters used in policy prompt.
    linked_count = len(linked_mentions.mentions) if linked_mentions is not None else 0
    unlinked_count = max(0, len(mentions) - linked_count)

    system_prompt = (
        "You classify a user message for a flexible NL2SPARQL agent flow. "
        "Return JSON with keys: action, reply, user_intent. "
        "Allowed actions: mention_pipeline, generate_query, reply_user. "
        "Use mention_pipeline for mention extraction/entity-linking concerns, include user intent in words. "
        "Use mention_pipeline whenever user asks to change who/what the query is about (entity switch), "
        "including cues like 'instead', 'replace', 'use X not Y', "
        "or corrections to names/entities even if a previous query already exists. "
        "Use generate_query for requests to generate/refine/fix/run/execute query or adjust result shape "
        "when the underlying entities do not need to change. "
        "Use reply_user when user asks for clarification/explanation/chitchat OR when intent is ambiguous and you need more information before running backend actions. "
        "When using reply_user for ambiguity, set reply to a concise follow-up question that helps choose the next action. "
        "Set user_intent to a precise edit instructions for mention_pipeline or generate_query actions. "
        "For reply_user, set user_intent to null. "
        "If linked_count is 0 or unlinked_count > 0 and user asks to continue/retry, prefer mention_pipeline over generate_query, unless the user explicitly requests query generation. "
        "If there is a recent mention/linking failure and user asks to continue/retry, prefer mention_pipeline. "
        "Prefer mention_pipeline if there are unlinked mentions unless users explicitly request query generation with unchanged entities. "
        "When uncertain whether entities changed, choose reply_user with one concise clarification question before generate_query.\n\n"
        "Knowledge graph metadata:\n"
        f"- name: {schema_name or 'none'}\n"
        f"- description: {schema_description or 'none'}\n\n"
        "Current session state:\n"
        f"- linked_count: {linked_count}\n"
        f"- unlinked_count: {unlinked_count}\n"
        f"- has_previous_query: {has_previous_query}\n"
        f"- last_failed_stage: {last_failed_stage or 'none'}\n"
        f"- last_failed_error: {last_failed_error or 'none'}\n"
        f"- question: {question}\n"
        f"- current_mentions:\n{mentions_to_text(mentions)}"
    )

    effective_history = _compact_message_memory_for_policy(message_memory)
    # Drop duplicated trailing user message to avoid echo bias.
    if effective_history:
        last = effective_history[-1]
        if (
            last.get("role") == "user"
            and (last.get("content") or "").strip() == user_message.strip()
        ):
            effective_history = effective_history[:-1]

    llm_messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        *effective_history,
        {
            "role": "user",
            "content": user_message,
        },
    ]

    resp = await chat_message(
        model=model,
        messages=llm_messages,
        response_model=AgentMessageDecision,
    )

    LOGGER.info(f"[Policy Agent]: {resp.model_dump_json(exclude_none=True)}")
    # make sure model reply are added to conversation
    return resp
