import os
import re
from typing import Any, Union

from dotenv import load_dotenv
from ollama import AsyncClient
from openai import AsyncClient as OpenAIAsyncClient
from pydantic import BaseModel

load_dotenv()

RWTH_GPT_PREFIX = "RWTH-GPT-"

OLLAMA_CLIENT = AsyncClient(
    host="http://ollama.warhol.informatik.rwth-aachen.de",
    headers={"x-api-key": os.getenv("OLLAMA_API_KEY")},
)

OPENAI_CLIENT = OpenAIAsyncClient(
    base_url="https://chat.kiconnect.nrw/api/v1",
    api_key=os.getenv("RWTHGPT_API_KEY"),
)

SANITIZE_STRUCTURED_RESPONSE = re.compile(r"\{.*\}", re.DOTALL)


def sanitize_structured_response(content: str) -> str:
    match = SANITIZE_STRUCTURED_RESPONSE.search(content)
    if not match:
        print(content)
        raise ValueError("No JSON object found in the response")

    raw_json = match.group(0)

    # Only apply mojibake recovery on the raw JSON string.
    # We do NOT apply fix_encoding() here, because replacing \u escapes in the raw payload
    # before JSON parsing can corrupt surrogate pairs or literal escaped backslashes.
    # We let Pydantic (json.loads) natively handle unicode escapes during parsing.
    try:
        raw_json = raw_json.encode("latin1").decode("utf8")
    except Exception:
        pass

    return raw_json


async def chat_message(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    response_model: type[BaseModel] | None = None,
) -> Union[dict[str, Any], BaseModel]:
    if model.startswith(RWTH_GPT_PREFIX):
        kwargs: dict[str, Any] = {
            "model": model[len(RWTH_GPT_PREFIX) :],
            "messages": messages,
        }
        if tools is not None:
            kwargs["tools"] = tools
        if response_model is not None:
            kwargs["response_format"] = response_model
            response = await OPENAI_CLIENT.chat.completions.parse(**kwargs)
            return response_model.model_validate_json(
                response.choices[0].message.content
            )
        else:
            response = await OPENAI_CLIENT.chat.completions.create(**kwargs)
            return response.choices[0].message.model_dump()

    kwargs = {"model": model, "messages": messages}
    if tools is not None:
        kwargs["tools"] = tools
    if response_model is not None:
        kwargs["format"] = response_model.model_json_schema()
    response = await OLLAMA_CLIENT.chat(**kwargs)

    if response_model is not None:
        return response_model.model_validate_json(
            sanitize_structured_response(response.message.content)
        )
    return response.message.model_dump()
