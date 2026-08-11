import re
from typing import Dict, List, Optional
import unicodedata

from src.internal.llm import chat_message
from src.internal.prompts import MENTION_EXTRACTION_PROMPT, replace_prompt_vars
from src.internal.schema_index import (
    filter_schema,
    is_string_label_pred,
    schema_to_context_string,
)
from src.internal.utils import LOGGER, fix_encoding, timed_async
from src.schemas.mentions import DetailedMention, Mention, MentionList
from src.schemas.schema_index import SchemaIndex


def extract_keywords_from_mentions(
    mentions: List[Mention], min_length: int = 1
) -> List[str]:
    """
    Extracts normalized, punctuation-free keywords from a list of mentions and their attributes.
    """
    keywords = set()
    for m in mentions:
        clean_mention = unicodedata.normalize("NFC", m.text.lower())
        for word in re.findall(r"\w+", clean_mention):
            if len(word) >= min_length:
                keywords.add(word)

        if m.attrs:
            for val in m.attrs.values():
                clean_attr = unicodedata.normalize("NFC", str(val).lower())
                for word in re.findall(r"\w+", clean_attr):
                    if len(word) >= min_length:
                        keywords.add(word)

    return list(keywords)


def build_extractor_prompt(ctx: SchemaIndex) -> str:
    ctx_me = filter_schema(
        ctx,
        keep_only_literal_or_labelable_object=False,
        keep_only_classes_with_predicates=False,
    )
    string_ctx = schema_to_context_string(
        ctx_me,
        include_prefixes=False,
        max_types=100,
        max_preds_per_type=100,
        include_notes=True,
        include_class_relations=True,
    )
    return replace_prompt_vars(MENTION_EXTRACTION_PROMPT, {"string_ctx": string_ctx})


def _to_iri(
    term: str,
    ns: Dict[str, str],
    *,
    known_iris: Optional[set[str]] = None,
) -> Optional[str]:
    term = (term or "").strip()
    if not term:
        return None
    if term.startswith("<") and term.endswith(">"):
        return term[1:-1]
    if "://" in term:
        return term

    resolved_iri = None
    if ":" in term:
        pfx, local = term.split(":", 1)
        if pfx in ns:
            resolved_iri = ns[pfx] + local

    if known_iris:
        # 1. Try exact match if we have one
        if resolved_iri and resolved_iri in known_iris:
            return resolved_iri

        # 2. Try case-insensitive match for the resolved IRI
        if resolved_iri:
            resolved_lower = resolved_iri.lower()
            matches = [i for i in known_iris if i.lower() == resolved_lower]
            if len(matches) == 1:
                return matches[0]

        # 3. Fallback: allow local-name-only or "#Local" forms if they resolve uniquely (case-insensitive)
        term_lower = term.lower()
        candidates = []
        if term.startswith("#"):
            candidates = [i for i in known_iris if i.lower().endswith(term_lower)]
        else:
            candidates = [
                i
                for i in known_iris
                if i.lower().endswith(f"#{term_lower}")
                or i.lower().endswith(f"/{term_lower}")
                or i.lower().endswith(term_lower)
            ]

        candidates = sorted(set(candidates))
        if len(candidates) == 1:
            return candidates[0]

    return resolved_iri


def validate_types(
    mentions: List[Mention], ctx: "SchemaIndex"
) -> List[DetailedMention]:
    """
    Minimal:
      - type must be a known class (CURIE or IRI)
      - label_pred must be a known prop (CURIE or IRI)
      - prop must have type in its domain
      - prop must be literal + include xsd:string in its literal_datatypes
    Invalid mentions are dropped.
    """
    ns = ctx.namespaces
    out: List[DetailedMention] = []
    for m in mentions:
        t = _to_iri(m.type, ns, known_iris=set(ctx.classes.keys()))
        p = _to_iri(m.label_pred, ns, known_iris=set(ctx.props.keys()))
        if not t or t not in ctx.classes:
            LOGGER.warning("Skipping mention with unknown type: %s", m.type)
            continue
        if not p or p not in ctx.props:
            LOGGER.warning("Skipping mention with unknown prop: %s", m.label_pred)
            continue

        ok, resolved_type = is_string_label_pred(ctx, t, p)
        if not ok:
            LOGGER.warning(
                "Skipping mention with prop %s not valid for type %s",
                m.label_pred,
                m.type,
            )
            continue

        if resolved_type and resolved_type != t:
            LOGGER.debug("Resolved mention type %s -> %s", t, resolved_type)
            t = resolved_type

        # Clean text: Strip surrounding quotes that LLM might hallucinate from query
        text = m.text.strip("'\"")

        out.append(
            DetailedMention(text=text, type=t, label_pred=p, attrs=dict(m.attrs))
        )
    return out


@timed_async()
async def extract_mentions(
    q: str, model: str, ctx: SchemaIndex, strict: bool = True
) -> List[DetailedMention]:
    q = fix_encoding(q)
    prompt = build_extractor_prompt(ctx)
    # LOGGER.debug(f"Mention extraction prompt:\n{prompt}")

    ml = await chat_message(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": q},
        ],
        response_model=MentionList,
    )

    if strict:
        valid_mentions = validate_types(ml.mentions, ctx)
        if len(valid_mentions) < len(ml.mentions):
            LOGGER.warning(
                f"Mention validation dropped={len(ml.mentions) - len(valid_mentions)}"
            )
    else:
        valid_mentions = ml.mentions
    LOGGER.info(f"Mention extraction completed count={len(valid_mentions)}")
    return [DetailedMention(**m.model_dump()) for m in valid_mentions]
