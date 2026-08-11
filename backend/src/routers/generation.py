from fastapi import APIRouter, status

from src.internal.queryGeneration.prompt_construction import prompt_construction
from src.internal.queryGeneration.tool_calling_loop import run_query_generation
from src.internal.queryGeneration.tools import get_tools_spec
from src.schemas.query_generation import (
    Query,
    RequestQueryGeneration,
)

router = APIRouter()


@router.post(
    "",
    status_code=status.HTTP_200_OK,
    response_model=Query,  # call from frontend
)
async def queryGeneration(request: RequestQueryGeneration):
    # prompt construction
    user_prompt, system_prompt = prompt_construction(request)

    return await run_query_generation(
        model=request.model,
        schema_id=request.schema_id,
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        tools=get_tools_spec(),
    )
