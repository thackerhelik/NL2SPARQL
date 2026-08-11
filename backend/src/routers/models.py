from fastapi import APIRouter

from src.internal.llm import OLLAMA_CLIENT, OPENAI_CLIENT, RWTH_GPT_PREFIX
from src.internal.utils import LOGGER

router = APIRouter()


async def _list_ollama_models() -> list[str]:
    response = await OLLAMA_CLIENT.list()
    names: list[str] = []
    for item in response.models:
        model_name = item.model
        names.append(model_name)
    return names


async def _list_openai_models() -> list[str]:
    response = await OPENAI_CLIENT.models.list()
    names: list[str] = []
    for item in response.data:
        model_name = item.id
        names.append(f"{RWTH_GPT_PREFIX}{model_name}")
    return names


@router.get("", response_model=list[str])
async def list_models() -> list[str]:
    try:
        ollama_models = await _list_ollama_models()
    except Exception as e:
        LOGGER.error(f"Error fetching Ollama models: {e}")
        ollama_models = []
    openai_models = await _list_openai_models()

    merged = ollama_models + openai_models
    filtered = [
        name
        for name in merged
        if ("embed" not in name.lower()) and ("test" not in name.lower())
    ]

    return sorted(set(filtered))
