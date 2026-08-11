from src.internal.prompts import QUERY_CONSTRUCTION_PROMPT, replace_prompt_vars
from src.internal.schema_cache import SCHEMA_CACHE
from src.schemas.query_generation import (
    RequestQueryGeneration,
    SystemPrompt,
    UserPrompt,
)


def _render_examples_text(request: RequestQueryGeneration) -> str:
    merged: list[tuple[str, str]] = []

    meta = SCHEMA_CACHE.get_meta(request.schema_id)
    schema_examples = meta.examples if meta else []
    for item in schema_examples:
        question = str(item.get("question", "")).strip()
        sparql = str(item.get("sparql", "")).strip()
        if not question or not sparql:
            continue
        key = (question, sparql)
        merged.append(key)

    for item in request.examples or []:
        question = item.question.strip()
        sparql = item.sparql.strip()
        if not question or not sparql:
            continue
        key = (question, sparql)
        merged.append(key)

    if not merged:
        return "No examples available."

    sections: list[str] = []
    for question, sparql in merged:
        sections.append(f"Q: {question}\nA:\n{sparql}")

    return "\n\n".join(sections)


def prompt_construction(request: RequestQueryGeneration):
    examples_text = _render_examples_text(request)

    # Inject variables into system prompt
    system_prompt = replace_prompt_vars(
        QUERY_CONSTRUCTION_PROMPT,
        {
            "{examples}": examples_text,
        },
    ).strip()

    # Build dynamic mention block
    mentions_text = "\n".join(
        f"Mention {i}:\n"
        f"- text: {mention.text}, type: {mention.type}, "
        f"label: {mention.label_pred}, attrs: {mention.attrs}, iri: {mention.iri}"
        for i, mention in enumerate(request.mentions.mentions, start=1)
    )

    user_prompt = f"""
Question:
{request.question}

Extracted Mentions with Linked Entities:
{mentions_text}
""".strip()

    return UserPrompt(query=user_prompt), SystemPrompt(query=system_prompt)
