from typing import Any

from src.internal.agents.utils import normalize_tool_name, run_tool_calling_loop
from src.internal.queryGeneration.prompt_construction import prompt_construction
from src.internal.queryGeneration.tools import TOOL_REGISTRY, get_tools_spec
from src.internal.sparql import DisallowedQueryTypeError, run
from src.internal.utils import LOGGER
from src.schemas.query_generation import RequestQueryGeneration

MAX_QUERY_GENERATION_ITERATIONS = 50


def _strip_code_fences(text: str) -> str:
    return text.replace("```sparql", "").replace("```", "").strip()


async def run_query_generation_agent(
    *,
    websocket: Any,
    ctx: Any,
    request: Any,
    linked_mentions: Any,
    previous_query: str | None,
    edit_instructions: str | None,
    send_stage_context: Any,
    send_event: Any,
) -> str | None:
    # Build base prompts from confirmed linked mentions.
    prompt_request = RequestQueryGeneration(
        question=request.question or "",
        mentions=linked_mentions,
        model=request.model or "",
        schema_id=request.schema_id or "",
    )
    user_prompt, system_prompt = prompt_construction(prompt_request)

    system_prompt_query = system_prompt.query
    user_prompt_query = user_prompt.query
    editing_mode = bool(previous_query and edit_instructions)

    if editing_mode:
        # Editing mode refines an existing query instead of regenerating.
        system_prompt_query = (
            f"{system_prompt_query}\n\n"
            "EDITING MODE:\n"
            "- You are editing an existing SPARQL query, not writing from scratch.\n"
            "- Apply the requested changes while preserving still-valid parts of the previous query.\n"
            "- Verify new classes and properties you want to use using the provided tools.\n"
        )
        user_prompt_query = (
            f"{user_prompt_query}\n\n"
            f"Previous SPARQL Query:\n{previous_query}\n\n"
            f"Edit Instructions:\n{edit_instructions}\n"
        )

    await send_stage_context(
        websocket,
        stage="query_generation",
        note="Started query generation from confirmed linked entities.",
    )

    await send_event(
        websocket,
        "phase",
        {"name": "query_generation", "status": "started"},
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt_query},
        {"role": "user", "content": user_prompt_query},
    ]
    tool_specs = [tool.model_dump() for tool in get_tools_spec()]
    final_answer = ""

    try:
        # Stream tool call metadata to frontend.
        async def _on_tool_calls(iteration: int, tool_calls: list[dict[str, Any]]):
            await send_event(
                websocket,
                "tool_calls",
                {
                    "iteration": iteration,
                    "calls": [
                        {
                            "id": call.get("id"),
                            "name": normalize_tool_name(call["function"]["name"]),
                            "arguments": call["function"]["arguments"],
                        }
                        for call in tool_calls
                    ],
                },
            )

        # Stream tool observations to frontend.
        async def _on_tool_result(
            _: int,
            call_id: str | None,
            func_name: str,
            __: Any,
            observation_json: str,
        ):
            await send_event(
                websocket,
                "tool_result",
                {
                    "tool_call_id": call_id,
                    "name": func_name,
                    "result": observation_json,
                },
            )

        loop_result = await run_tool_calling_loop(
            model=request.model or "",
            messages=messages,
            tools=tool_specs,
            tool_registry=TOOL_REGISTRY,
            ctx=ctx,
            max_iterations=MAX_QUERY_GENERATION_ITERATIONS,
            normalize_tool_name_fn=normalize_tool_name,
            on_tool_calls=_on_tool_calls,
            on_tool_result=_on_tool_result,
        )

        final_answer = (loop_result.get("final_answer") or "").strip()
    except Exception as error:
        LOGGER.error("Query generation failed in websocket flow: %s", str(error))
        await send_event(
            websocket,
            "phase",
            {
                "name": "query_generation",
                "status": "failed",
                "reason": "runtime_error",
            },
        )
        await send_event(
            websocket,
            "error",
            {
                "message": str(error).strip() or error.__class__.__name__,
                "error_type": "query_generation",
            },
        )
        return None

    if not final_answer:
        await send_event(
            websocket,
            "phase",
            {
                "name": "query_generation",
                "status": "failed",
                "reason": "iteration_limit",
            },
        )
        await send_event(
            websocket,
            "error",
            {
                "message": "Query generation did not return a final answer within the iteration limit."
            },
        )
        return None

    generated_query = _strip_code_fences(final_answer)
    await send_event(
        websocket,
        "phase",
        {"name": "query_generation", "status": "finished"},
    )
    await send_event(
        websocket,
        "final_query",
        {"query": generated_query},
    )

    # Execute generated query and stream results/errors.

    await send_stage_context(
        websocket,
        stage="query_execution",
        note="Running query execution with validation enabled.",
    )
    await send_event(
        websocket,
        "phase",
        {"name": "query_execution", "status": "started"},
    )
    try:
        result = await run(
            endpoint=ctx.endpoint,
            query=generated_query,
            validate=True,
            ctx=ctx,
        )
        await send_event(
            websocket,
            "query_result",
            result.model_dump(mode="json"),
        )
        await send_event(
            websocket,
            "phase",
            {"name": "query_execution", "status": "finished"},
        )
    except DisallowedQueryTypeError as error:
        await send_event(
            websocket,
            "error",
            {"message": str(error), "error_type": "forbidden"},
        )
    except ValueError as error:
        await send_event(
            websocket,
            "error",
            {"message": str(error), "error_type": "syntax"},
        )
    except Exception as error:
        LOGGER.error("Websocket query execution failed: %s", str(error))
        await send_event(
            websocket,
            "error",
            {
                "message": str(error).strip() or error.__class__.__name__,
                "error_type": "query_execution",
            },
        )

    return generated_query
