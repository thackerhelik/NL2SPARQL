from fastapi import HTTPException

from src.internal.agents.utils import run_tool_calling_loop
from src.internal.queryGeneration.tools import TOOL_REGISTRY
from src.internal.schema_cache import SCHEMA_CACHE
from src.internal.utils import LOGGER, timed_async
from src.schemas.query_generation import Query, SystemPrompt, Tool, UserPrompt
from src.schemas.schema_index import SchemaIndex


# import tiktoken
@timed_async()
async def run_query_generation(
    *,
    model: str,
    schema_id: str,
    user_prompt: UserPrompt,
    system_prompt: SystemPrompt,
    tools: list[Tool],
) -> Query:
    LOGGER.info(f"Tool loop start model={model}")

    # ---
    #  For logging, might remove later
    # encoder = tiktoken.get_encoding("gpt2")
    # def count_tokens(msgs):
    #    return sum(len(encoder.encode(m.get("content") or "")) for m in msgs)
    # ---

    ctx: SchemaIndex = SCHEMA_CACHE.get(schema_id)
    if not ctx:
        raise ValueError(f"Schema with id {schema_id} not found in cache.")

    messages = [
        {"role": "system", "content": system_prompt.query},
        {"role": "user", "content": user_prompt.query},
    ]

    tool_specs = [tool.model_dump() for tool in tools]

    try:
        loop_result = await run_tool_calling_loop(
            model=model,
            messages=messages,
            tools=tool_specs,
            tool_registry=TOOL_REGISTRY,
            ctx=ctx,
            max_iterations=50,
            max_message_history=55,
        )
        final_answer = (loop_result.get("final_answer") or "").strip()
        iterations = int(loop_result.get("iterations") or 0)
        if not final_answer:
            raise HTTPException(
                status_code=500, detail="LLM returned an empty response."
            )

        LOGGER.info(
            f"Tool loop end iterations={iterations} final answer={final_answer}..."
        )

        # total_tokens = count_tokens(messages)
        # LOGGER.info(f"Total tokens used in loop (input + output): {total_tokens}")

        return Query(query=final_answer)

    except Exception:
        LOGGER.exception("Error in tool calling loop")
        raise
