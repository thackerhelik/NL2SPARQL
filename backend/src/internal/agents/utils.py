import inspect
import json
import re
from typing import Any, Awaitable, Callable

from src.internal.llm import chat_message
from src.internal.utils import LOGGER


def normalize_tool_name(raw_name: str) -> str:
    cleaned = (raw_name or "").strip()
    if not cleaned:
        return ""
    cleaned = re.split(r"[<\s]", cleaned, maxsplit=1)[0]
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "", cleaned)
    return cleaned


def truncate_text(value: str, max_chars: int = 2500) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}... [truncated {len(value) - max_chars} chars]"


def compact_messages(
    messages: list[dict[str, Any]],
    *,
    max_messages: int = 20,
    fixed_prefix_count: int = 2,
) -> list[dict[str, Any]]:
    if len(messages) <= max_messages:
        return messages

    LOGGER.debug("Compacting messages")
    fixed_prefix_count = max(0, min(fixed_prefix_count, max_messages, len(messages)))
    fixed = messages[:fixed_prefix_count]
    tail = messages[fixed_prefix_count:]
    keep_tail = max_messages - fixed_prefix_count
    return fixed + tail[-keep_tail:]


def _invoke_tool_logic(
    *,
    info: dict[str, Any],
    ctx: Any,
    state: Any,
    func_args: dict[str, Any],
) -> Any:
    logic = info["logic"]
    takes_ctx = bool(info.get("takes_ctx", True))
    takes_state = bool(info.get("takes_state", False))

    if takes_ctx and takes_state:
        return logic(ctx, state, **func_args)
    if takes_ctx:
        return logic(ctx, **func_args)
    if takes_state:
        return logic(state, **func_args)
    return logic(**func_args)


async def run_tool_calling_loop(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    tool_registry: dict[str, Any],
    ctx: Any,
    state: Any | None = None,
    max_iterations: int = 20,
    max_message_history: int = 20,
    fixed_prefix_count: int = 2,
    normalize_tool_name_fn: Callable[[str], str] | None = None,
    on_iteration: Callable[
        [int, dict[str, Any], list[dict[str, Any]]], Awaitable[None] | None
    ]
    | None = None,
    on_tool_calls: Callable[[int, list[dict[str, Any]]], Awaitable[None] | None]
    | None = None,
    on_tool_result: Callable[[int, str | None, str, Any, str], Awaitable[None] | None]
    | None = None,
) -> dict[str, Any]:
    iterations = 0
    final_answer = ""

    while iterations < max_iterations:
        # Ask model for next action or final answer.
        iterations += 1
        messages = compact_messages(
            messages,
            max_messages=max_message_history,
            fixed_prefix_count=fixed_prefix_count,
        )

        res_msg = await chat_message(
            model=model,
            messages=messages,
            tools=tools,
        )

        messages.append(res_msg)

        if on_iteration is not None:
            maybe = on_iteration(iterations, res_msg, messages)
            if inspect.isawaitable(maybe):
                await maybe

        tool_calls = res_msg.get("tool_calls") or []
        if not tool_calls:
            # Loop ends when model returns plain content.
            final_answer = (res_msg.get("content") or "").strip()
            break

        if on_tool_calls is not None:
            maybe = on_tool_calls(iterations, tool_calls)
            if inspect.isawaitable(maybe):
                await maybe

        for tool_call in tool_calls:
            # Normalize tool name and parse JSON args.
            raw_name = tool_call["function"].get("name", "")
            func_name = (
                normalize_tool_name_fn(raw_name)
                if normalize_tool_name_fn is not None
                else raw_name
            )
            args = tool_call["function"].get("arguments")
            call_id = tool_call.get("id")

            if isinstance(args, str) and args.strip():
                try:
                    args = json.loads(args)
                except json.JSONDecodeError as exc:
                    args = {"_raw_arguments": args}
                    LOGGER.warning(
                        "Failed to parse tool args for %s: %s", func_name, str(exc)
                    )
            elif not isinstance(args, dict):
                args = {}

            LOGGER.info(f"Tool call name={func_name} args={args}")

            if func_name not in tool_registry:
                observation: Any = f"Error: Tool {func_name} not found."
            else:
                # Execute tool logic, optionally injecting ctx.
                info = tool_registry[func_name]
                try:
                    func_args = info["model"](**args).model_dump()
                except Exception as exc:
                    LOGGER.warning(
                        "Tool arg validation failed for %s args=%s err=%s",
                        func_name,
                        truncate_text(str(args), max_chars=800),
                        str(exc),
                    )
                    observation = {
                        "error_type": "args",
                        "error_message": f"Invalid args for tool {func_name}: {str(exc)}",
                    }
                else:
                    try:
                        observation = _invoke_tool_logic(
                            info=info,
                            ctx=ctx,
                            state=state,
                            func_args=func_args,
                        )
                        if inspect.isawaitable(observation):
                            observation = await observation
                    except Exception as exc:
                        LOGGER.exception("Tool execution failed for %s", func_name)
                        observation = {
                            "error_type": "tool_execution",
                            "error_message": f"Tool {func_name} failed: {str(exc)}",
                        }

            try:
                observation_json = json.dumps(observation, ensure_ascii=False)
            except TypeError:
                observation_json = json.dumps(
                    {"error_type": "serialization", "error_message": str(observation)},
                    ensure_ascii=False,
                )

            if on_tool_result is not None:
                maybe = on_tool_result(
                    iterations,
                    call_id,
                    func_name,
                    args,
                    observation_json,
                )
                if inspect.isawaitable(maybe):
                    await maybe

            messages.append(
                {
                    "role": "tool",
                    "content": observation_json,
                    "tool_call_id": call_id,
                }
            )
    LOGGER.info(
        f"Agent finished after {iterations} iters with final answer: {final_answer}"
    )
    return {
        "final_answer": final_answer,
        "iterations": iterations,
        "messages": messages,
    }
