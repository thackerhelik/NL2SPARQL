import asyncio
from dataclasses import dataclass, field
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from src.internal.agents.utils import normalize_tool_name, run_tool_calling_loop
from src.internal.mentions import onehop_readable
from src.internal.mentions.extraction import _to_iri, extract_keywords_from_mentions
from src.internal.mentions.generation import get_candidates_simple
from src.internal.mentions.ranking import bm25_score
from src.internal.prompts import MENTION_AGENT_SYSTEM_PROMPT, replace_prompt_vars
from src.internal.schema_index import is_string_label_pred
from src.internal.sparql import run as run_sparql
from src.internal.utils import LOGGER
from src.schemas.mentions import (
    Candidate,
    DetailedMention,
    Mention,
    MentionsAgentResult,
    MentionStatusRow,
)
from src.schemas.schema_index import SchemaIndex

CANDIDATE_FETCH_LIMIT = 30


# -----------------------------
# CURIE helpers
# -----------------------------
def expand_term(term: str, ctx: SchemaIndex) -> Optional[str]:
    return _to_iri(term, ctx.namespaces)


def compact_iri(iri: str, ctx: SchemaIndex) -> str:
    iri = (iri or "").strip()
    if not iri:
        return iri

    best: Optional[str] = None
    for pfx, ns in (ctx.namespaces or {}).items():
        if iri.startswith(ns):
            curie = f"{pfx}:{iri[len(ns) :]}"
            if best is None or len(curie) < len(best):
                best = curie
    return best or iri


def compact_value(v: Any, ctx: SchemaIndex) -> Any:
    if isinstance(v, str) and "://" in v:
        return compact_iri(v, ctx)
    return v


def _class_label_note(class_iri: str, ctx: SchemaIndex) -> tuple[str, str]:
    cdef = ctx.classes.get(class_iri)
    if not cdef:
        fallback = compact_iri(class_iri, ctx).split(":")[-1]
        return fallback, ""
    label = (
        cdef.labels[0] if cdef.labels else compact_iri(class_iri, ctx).split(":")[-1]
    )
    note = "; ".join(cdef.comments[:2]) if cdef.comments else ""
    return label, note


def _pred_range_compact(pred_iri: str, ctx: SchemaIndex) -> str:
    pdef = ctx.props.get(pred_iri)
    if not pdef:
        return "unk"
    if pdef.literal_datatypes:
        dts = sorted(compact_iri(dt, ctx) for dt in pdef.literal_datatypes)
        return f"lit({','.join(dts)})"
    if pdef.range_classes:
        classes = sorted(compact_iri(c, ctx) for c in pdef.range_classes)
        return f"iri({'|'.join(classes)})"
    return "unk"


def _class_ancestors(class_iri: str, ctx: SchemaIndex) -> set[str]:
    seen: set[str] = set()
    stack = [class_iri]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        cdef = ctx.classes.get(cur)
        if not cdef:
            continue
        for parent in cdef.super_classes | cdef.equivalent_classes:
            if parent not in seen:
                stack.append(parent)
    return seen


def _is_ambiguous_from_scores(scores: List[float]) -> bool:
    if len(scores) < 2:
        return False
    s1 = float(scores[0] or 0.0)
    s2 = float(scores[1] or 0.0)
    if s1 == 0.0 and s2 == 0.0:
        return True
    return abs(s1 - s2) <= (0.1 * max(abs(s1), 1.0))


def _normalize_mention_payload(
    *,
    text: Any = "",
    type_curie: Any = "",
    label_pred: Any = "",
    attrs: Any = None,
) -> Dict[str, Any]:
    return {
        "text": text or "",
        "type": type_curie or "",
        "label_pred": label_pred or "",
        "attrs": attrs or {},
    }


def _mention_status_rows(state: "MentionState") -> List[MentionStatusRow]:
    rows: List[MentionStatusRow] = []

    for mention_id, mention_data in enumerate(state.mentions):
        normalized_mention = _normalize_mention_payload(
            text=mention_data.get("text"),
            type_curie=mention_data.get("type"),
            label_pred=mention_data.get("label_pred"),
            attrs=mention_data.get("attrs"),
        )

        normalized_mention = {
            "text": mention_data.get("text") or "",
            "type": mention_data.get("type") or "",
            "label_pred": mention_data.get("label_pred") or "",
            "attrs": mention_data.get("attrs") or {},
        }

        candidates_obj = state.candidates_obj_by_mention_id.get(mention_id) or []
        candidate_count = len(candidates_obj)
        reranked = any(c.score is not None for c in candidates_obj)

        top_iri = None
        top_label = None
        top_score = None
        ambiguous = False

        if candidate_count > 0:
            top = candidates_obj[0]
            top_iri = top.uri
            variants = getattr(top, "variants", None) or []
            if variants and getattr(variants[0], "label", None):
                top_label = variants[0].label
            if not top_label:
                top_label = top.uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]

            if reranked:
                scores = [float(c.score or 0.0) for c in candidates_obj[:2]]
                top_score = float(top.score or 0.0)
                ambiguous = _is_ambiguous_from_scores(scores)
            else:
                score_view = state.candidates_by_mention_id.get(mention_id) or []
                if score_view:
                    top_score = float(score_view[0].get("base_score") or 0.0)
                    view_scores = [
                        float(score_view[i].get("base_score") or 0.0)
                        for i in range(min(2, len(score_view)))
                    ]
                    ambiguous = _is_ambiguous_from_scores(view_scores)

        rows.append(
            MentionStatusRow(
                mention_id=mention_id,
                text=normalized_mention["text"],
                type=normalized_mention["type"],
                label_pred=normalized_mention["label_pred"],
                candidate_count=candidate_count,
                reranked=reranked,
                top_candidate_iri=top_iri,
                top_candidate_label=top_label,
                top_score=top_score,
                ambiguous=ambiguous,
                ready=(candidate_count > 0 and reranked),
            )
        )

    return rows


# -----------------------------
# SPARQL response summarizer
# -----------------------------
def summarize_run_response(
    result: Any, ctx: SchemaIndex, sample_size: int = 5
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}

    boolean = getattr(result, "boolean", None)
    if boolean is not None:
        summary["boolean"] = boolean

    head = getattr(result, "head", None)
    vars_list = getattr(head, "vars", None) if head else None
    vars_list = vars_list or []
    summary["vars"] = vars_list

    results = getattr(result, "results", None)
    bindings = getattr(results, "bindings", None) if results else None
    bindings = bindings or []
    summary["row_count"] = len(bindings)

    sample = []
    for row in bindings[:sample_size]:
        row_out = {}
        for key, value in row.items():
            row_out[key] = compact_value(getattr(value, "value", None), ctx)
        sample.append(row_out)

    summary["sample_bindings"] = sample
    return summary


# -----------------------------
# Session state
# -----------------------------
@dataclass
class MentionState:
    mentions: List[Dict[str, Any]] = field(default_factory=list)
    candidates_by_mention_id: Dict[int, List[Dict[str, Any]]] = field(
        default_factory=dict
    )
    candidates_obj_by_mention_id: Dict[int, List[Candidate]] = field(
        default_factory=dict
    )


# -----------------------------
# Tool: create/edit/delete mention
# -----------------------------
async def create_mention(
    *,
    state: MentionState,
    text: str,
    type_curie: str,
    label_pred: str,
    attrs: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    mention = _normalize_mention_payload(
        text=text,
        type_curie=type_curie,
        label_pred=label_pred,
        attrs=attrs,
    )

    # Check for duplicate mention before adding
    for indexm, m in enumerate(state.mentions):
        if m["text"] == mention["text"]:
            error = f"Duplicate mention with text '{mention['text']}' already exists at index {indexm}."
            LOGGER.warning(error)
            return {"error_type": "args", "error_message": error}

    state.mentions.append(mention)
    mention_id = len(state.mentions) - 1
    state.candidates_by_mention_id.pop(mention_id, None)
    state.candidates_obj_by_mention_id.pop(mention_id, None)
    return {
        "mention_id": mention_id,
        "status": (await mention_status(state=state)),
    }


async def edit_mention(
    *,
    state: MentionState,
    mention_id: int,
    text: str,
    type_curie: str,
    label_pred: str,
    attrs: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if mention_id < 0 or mention_id >= len(state.mentions):
        return {"error_type": "args", "error_message": "invalid mention_id"}
    state.mentions[mention_id] = _normalize_mention_payload(
        text=text,
        type_curie=type_curie,
        label_pred=label_pred,
        attrs=attrs,
    )
    state.candidates_by_mention_id.pop(mention_id, None)
    state.candidates_obj_by_mention_id.pop(mention_id, None)
    return {
        "mention_id": mention_id,
        "status": (await mention_status(state=state)),
    }


async def delete_mention(
    *,
    state: MentionState,
    mention_id: int,
) -> Dict[str, Any]:
    if mention_id < 0 or mention_id >= len(state.mentions):
        return {"error_type": "args", "error_message": "invalid mention_id"}
    state.mentions.pop(mention_id)
    state.candidates_by_mention_id.pop(mention_id, None)
    state.candidates_obj_by_mention_id.pop(mention_id, None)

    # Reindex candidate maps to match shifted mention indexes after deletion.
    state.candidates_by_mention_id = {
        (idx - 1 if idx > mention_id else idx): items
        for idx, items in state.candidates_by_mention_id.items()
    }
    state.candidates_obj_by_mention_id = {
        (idx - 1 if idx > mention_id else idx): items
        for idx, items in state.candidates_obj_by_mention_id.items()
    }

    return {
        "deleted": True,
        "mention_id": mention_id,
        "status": (await mention_status(state=state)),
    }


# -----------------------------
# Tool: schema_tool
# - list_classes
# - describe_class (includes label_predicates and super_classes)
# -----------------------------
async def schema_tool(
    *,
    ctx: SchemaIndex,
    mode: str,
    class_curie: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    mode = (mode or "").strip()

    if mode == "list_classes":
        items = []
        for iri in ctx.classes.keys():
            label, note = _class_label_note(iri, ctx)
            items.append({"curie": compact_iri(iri, ctx), "label": label, "note": note})
        items.sort(key=lambda x: (x["curie"], x["label"]))
        res = {"classes": items[:limit]}
        LOGGER.debug("schema_tool list_classes result: %s", res)
        return res

    if mode == "describe_class":
        if not class_curie:
            return {"error_type": "args", "error_message": "missing class_curie"}

        class_iri = expand_term(class_curie, ctx)
        if not class_iri or class_iri not in ctx.classes:
            return {"error_type": "schema", "error_message": "unknown class"}

        cdef = ctx.classes[class_iri]
        label, note = _class_label_note(class_iri, ctx)

        eligible_domains = _class_ancestors(class_iri, ctx)
        predicates: List[Dict[str, str]] = []
        label_preds = []
        for p_iri, pdef in ctx.props.items():
            if not (pdef.domains & eligible_domains):
                continue
            p_label = (
                pdef.labels[0] if pdef.labels else p_iri.split("/")[-1].split("#")[-1]
            )
            row = {
                "curie": compact_iri(p_iri, ctx),
                "label": p_label,
                "rng": _pred_range_compact(p_iri, ctx),
                "note": "; ".join(pdef.comments[:2]) if pdef.comments else "",
            }
            predicates.append(row)

            ok, _resolved_type = is_string_label_pred(ctx, class_iri, p_iri)
            if ok:
                label_preds.append(row)

        predicates.sort(key=lambda x: (x["curie"], x["label"]))
        label_preds.sort(key=lambda x: (x["curie"], x["label"]))

        def _class_rows(iris: set[str]) -> List[Dict[str, str]]:
            rows: List[Dict[str, str]] = []
            for iri in sorted(iris):
                item_label, _item_note = _class_label_note(iri, ctx)
                rows.append({"curie": compact_iri(iri, ctx), "label": item_label})
            return rows

        return {
            "class": {
                "curie": compact_iri(class_iri, ctx),
                "label": label,
                "note": note,
            },
            "relations": {
                "subClassOf": _class_rows(cdef.super_classes)[:20],
                "equiv": _class_rows(cdef.equivalent_classes)[:20],
                "disjointWith": _class_rows(cdef.disjoint_with)[:20],
            },
            "predicates": predicates[:limit],
            "label_predicates": label_preds[:limit],
        }

    return {"error_type": "args", "error_message": f"unknown mode {mode}"}


# -----------------------------
# Tool: probe_class_label_pred
# - simple existence/sample via LIMIT 1
# -----------------------------
async def probe_class_label_pred(
    *,
    ctx: SchemaIndex,
    class_curie: str,
    label_pred_curie: str,
) -> Dict[str, Any]:
    if not getattr(ctx, "endpoint", None):
        return {"error_type": "endpoint", "error_message": "ctx.endpoint is not set"}

    class_iri = expand_term(class_curie, ctx)
    pred_iri = expand_term(label_pred_curie, ctx)
    if not class_iri or not pred_iri:
        return {
            "error_type": "args",
            "error_message": "could not expand class_curie or label_pred_curie",
        }

    query = f"""
    SELECT ?s ?label WHERE {{
      ?s a <{class_iri}> .
      ?s <{pred_iri}> ?label .
    }} LIMIT 1
    """.strip()

    result = await run_sparql(ctx.endpoint, query, ctx=ctx, validate=True)
    summary = summarize_run_response(result, ctx, sample_size=1)

    found = bool(summary.get("row_count", 0))
    sample = (summary.get("sample_bindings") or [None])[0]
    return {"found": found, "sample": sample}


# -----------------------------
# Tool: search_candidates
# - uses get_candidates_simple only (build_candidate_query_from_mention strict + optional relaxed)
# - no onehop fetching, no BM25
# - returns compact summary only; use list_candidates for inspection
# -----------------------------
async def search_candidates(
    *,
    ctx: SchemaIndex,
    state: MentionState,
    mention_id: int,
    relaxed_fallback: bool = True,
) -> Dict[str, Any]:
    if mention_id < 0 or mention_id >= len(state.mentions):
        return {"error_type": "args", "error_message": "invalid mention_id"}

    m = state.mentions[mention_id]
    text = (m.get("text") or "").strip()
    type_curie = (m.get("type") or "").strip()
    label_pred_curie = (m.get("label_pred") or "").strip()
    attrs = m.get("attrs") or {}

    if not text or not type_curie or not label_pred_curie:
        return {
            "mention_id": mention_id,
            "candidate_count": 0,
            "reason": "missing_text_or_type_or_label_pred",
        }

    mention = Mention(
        text=text, type=type_curie, label_pred=label_pred_curie, attrs=attrs
    )

    try:
        candidates_obj = await get_candidates_simple(
            ctx,
            mention,
            limit=CANDIDATE_FETCH_LIMIT,
            relaxed_fallback=relaxed_fallback,
        )
    except Exception as exc:
        LOGGER.warning(
            "search_candidates failed mention_id=%s text=%s err=%s",
            mention_id,
            text,
            str(exc),
        )
        state.candidates_obj_by_mention_id[mention_id] = []
        state.candidates_by_mention_id[mention_id] = []
        return {
            "mention_id": mention_id,
            "candidate_count": 0,
            "reason": "candidate_search_error",
            "error_message": str(exc),
        }
    state.candidates_obj_by_mention_id[mention_id] = candidates_obj

    out: List[Dict[str, Any]] = []
    for idx, c in enumerate(candidates_obj):
        uri = getattr(c, "uri", None)

        label = None
        variants = getattr(c, "variants", None) or []
        if variants:
            label = getattr(variants[0], "label", None)

        if not label and uri:
            label = uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]

        match_exact = bool(getattr(c, "match_exact", False))
        tokens_matched = int(getattr(c, "tokens_matched", 0) or 0)
        degree = int(getattr(c, "degree", 0) or 0)

        base_score = (1000 if match_exact else 0) + (10 * tokens_matched) + degree

        out.append(
            {
                "idx": idx,
                "uri": compact_iri(uri, ctx) if uri else None,
                "label": label,
                "base_score": float(base_score),
            }
        )

    state.candidates_by_mention_id[mention_id] = out

    return {
        "mention_id": mention_id,
        "candidate_count": len(out),
        "fetched_limit": CANDIDATE_FETCH_LIMIT,
        "reason": "no_candidates" if len(out) == 0 else None,
    }


# -----------------------------
# Tool: list_candidates
# -----------------------------
async def list_candidates(
    *,
    state: MentionState,
    mention_id: int,
    offset: int = 0,
    limit: int = 3,
) -> Dict[str, Any]:
    if limit < 1:
        limit = 1
    if limit > 50:
        limit = 50
    if offset < 0:
        offset = 0

    items = state.candidates_by_mention_id.get(mention_id) or []
    return {
        "mention_id": mention_id,
        "offset": offset,
        "limit": limit,
        "candidate_count": len(items),
        "candidates": items[offset : offset + limit],
    }


# -----------------------------
# Tool: describe_candidate
# - bounded SELECT ?p ?o LIMIT N
# -----------------------------
async def describe_candidate(
    *,
    ctx: SchemaIndex,
    candidate_curie_or_iri: str,
    limit: int = 25,
) -> Dict[str, Any]:
    if not getattr(ctx, "endpoint", None):
        return {"error_type": "endpoint", "error_message": "ctx.endpoint is not set"}

    iri = expand_term(candidate_curie_or_iri, ctx) or candidate_curie_or_iri
    iri = iri.strip("<>").strip()

    query = f"""
    SELECT ?p ?o WHERE {{
      <{iri}> ?p ?o .
    }} LIMIT {int(limit)}
    """.strip()

    result = await run_sparql(ctx.endpoint, query, ctx=ctx, validate=True)
    summary = summarize_run_response(result, ctx)

    sb = summary.get("sample_bindings") or []
    for row in sb:
        if "p" in row:
            row["p"] = compact_value(row["p"], ctx)
        if "o" in row:
            row["o"] = compact_value(row["o"], ctx)
    summary["sample_bindings"] = sb

    return {"summary": summary}


# -----------------------------
# Tool: boost_candidates
# - adjusts local ordering only
# -----------------------------
async def boost_candidates(
    *,
    state: MentionState,
    mention_id: int,
    adjustments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    items = state.candidates_by_mention_id.get(mention_id) or []
    items_obj = state.candidates_obj_by_mention_id.get(mention_id) or []
    if not items:
        return {
            "error_type": "state",
            "error_message": "no candidates stored for mention_id",
        }

    scores: Dict[int, float] = {}
    for c in items:
        idx = int(c["idx"])
        base = float(
            c.get("boosted_score")
            if c.get("boosted_score") is not None
            else (c.get("base_score") or 0.0)
        )
        scores[idx] = base

    for adj in adjustments:
        idx = int(adj.get("idx"))
        delta = float(adj.get("delta") or 0.0)
        scores[idx] = scores.get(idx, 0.0) + delta

    boosted = []
    for c in items:
        idx = int(c["idx"])
        boosted_score = scores.get(idx, float(c.get("base_score") or 0.0))
        boosted.append({**c, "boosted_score": boosted_score})

    boosted.sort(key=lambda x: float(x.get("boosted_score") or 0.0), reverse=True)
    state.candidates_by_mention_id[mention_id] = boosted
    if items_obj:
        remapped: List[Candidate] = []
        for c in boosted:
            idx = int(c.get("idx", -1))
            if 0 <= idx < len(items_obj):
                remapped.append(items_obj[idx])
        if remapped:
            state.candidates_obj_by_mention_id[mention_id] = remapped

    return {"mention_id": mention_id, "top": boosted[: min(3, len(boosted))]}


async def mention_status(
    *,
    state: MentionState,
    mention_id: Optional[int] = None,
) -> Dict[str, Any]:
    rows = _mention_status_rows(state)
    if mention_id is not None:
        rows = [r for r in rows if r.mention_id == mention_id]
    return {
        "mention_indexes": [r.mention_id for r in rows],
        "mentions": [r.model_dump(mode="json") for r in rows],
        "all_ready": bool(rows) and all(r.ready for r in rows),
    }


# -----------------------------
# Tool: rerank_once
# - real: fetch onehop context for top_k candidates and call bm25_score
# - budgeted to once per question
# -----------------------------


def _sanitize_keywords(keywords: List[str], max_kw: int = 30) -> List[str]:
    seen = set()
    out: List[str] = []
    for kw in keywords or []:
        for t in re.findall(r"\w+", str(kw).lower()):
            if len(t) < 2 or t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= max_kw:
                return out
    return out


async def rerank_mention(
    *,
    ctx,
    state: MentionState,
    mention_id: int,
    keywords: List[str],
    limit_each: int = 30,
) -> Dict[str, Any]:
    """
    Rerank candidates for one mention using:
      - onehop_readable(ctx, candidate.uri, keywords=keywords)
      - bm25_score(ctx, keywords, candidates)

    Requires candidates already stored in STATE.candidates_obj_by_mention_id[mention_id].
    """
    kws = _sanitize_keywords(keywords)

    candidates_obj = state.candidates_obj_by_mention_id.get(mention_id) or []
    if not candidates_obj:
        return {"mention_id": mention_id, "candidate_count": 0, "ranked": []}

    # Fetch one-hop context for all candidates for this mention.
    tasks = [
        onehop_readable(ctx, c.uri, keywords=kws, limit_each=limit_each)
        for c in candidates_obj
    ]
    contexts_or_errors = await asyncio.gather(*tasks, return_exceptions=True)
    for c, maybe_context in zip(candidates_obj, contexts_or_errors, strict=True):
        if isinstance(maybe_context, Exception):
            LOGGER.warning(
                "onehop_readable failed mention_id=%s uri=%s err=%s",
                mention_id,
                c.uri,
                str(maybe_context),
            )
            c.context = []
        else:
            c.context = maybe_context

    try:
        ranked = bm25_score(ctx, kws, candidates_obj)
    except Exception as exc:
        LOGGER.warning("bm25 rerank failed mention_id=%s err=%s", mention_id, str(exc))
        ranked = candidates_obj

    ranked_view_all: List[Dict[str, Any]] = []
    for idx, c in enumerate(ranked):
        label = None
        variants = getattr(c, "variants", None) or []
        if variants and getattr(variants[0], "label", None):
            label = variants[0].label
        if not label:
            label = c.uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]

        ranked_view_all.append(
            {
                "idx": idx,
                "uri": compact_iri(c.uri, ctx),
                "label": label,
                "score": float(c.score or 0.0),
            }
        )

    # Store ranked order back into provided state
    state.candidates_obj_by_mention_id[mention_id] = ranked
    state.candidates_by_mention_id[mention_id] = [
        {
            "idx": r["idx"],
            "uri": r["uri"],
            "label": r["label"],
            "base_score": r["score"],
        }
        for r in ranked_view_all
    ]

    return {
        "mention_id": mention_id,
        "candidate_count": len(ranked),
        "keywords_used": kws,
        "top_k": ranked_view_all[: min(3, len(ranked_view_all))],
    }


# -----------------------------
# Tool arg schemas
# -----------------------------
class CreateMentionArgs(BaseModel):
    text: str = Field(..., description="Exact user-query span for the mention.")
    type_curie: str = Field(..., description="CURIE for the mention class.")
    label_pred: str = Field(..., description="CURIE for the label predicate.")
    attrs: Dict[str, str] = Field(default_factory=dict)


class EditMentionArgs(BaseModel):
    mention_id: int = Field(..., description="Mention index from mention_status.")
    text: str = Field(..., description="Exact user-query span for the mention.")
    type_curie: str = Field(..., description="CURIE for the mention class.")
    label_pred: str = Field(..., description="CURIE for the label predicate.")
    attrs: Dict[str, str] = Field(default_factory=dict)


class DeleteMentionArgs(BaseModel):
    mention_id: int = Field(..., description="Mention index from mention_status.")


class SchemaToolArgs(BaseModel):
    mode: str = Field(..., description="list_classes | describe_class")
    class_curie: Optional[str] = Field(None, description="Used only for describe_class")
    limit: int = Field(50, ge=1, le=500)


class ProbeClassLabelPredArgs(BaseModel):
    class_curie: str
    label_pred_curie: str


class SearchCandidatesArgs(BaseModel):
    mention_id: int
    relaxed_fallback: bool = True


class ListCandidatesArgs(BaseModel):
    mention_id: int
    offset: int = Field(0, ge=0)
    limit: int = Field(3, ge=1, le=50)


class DescribeCandidateArgs(BaseModel):
    candidate_curie_or_iri: str
    limit: int = Field(20, ge=1, le=50)


class BoostCandidatesArgs(BaseModel):
    mention_id: int
    adjustments: List[Dict[str, Any]] = Field(
        ...,
        description="List of {idx:int, delta:float, reason?:str}",
    )


class RerankMentionArgs(BaseModel):
    mention_id: int
    keywords: List[str] = Field(..., description="LLM-provided keywords for BM25")
    limit_each: int = Field(30, ge=1, le=100)


class MentionStatusArgs(BaseModel):
    mention_id: Optional[int] = Field(
        None,
        description="Optional mention index filter. Omit to list all mentions with indexes.",
    )


# -----------------------------
# Tool specs (what you pass to the LLM)
# -----------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_mention",
            "description": "Create one mention. The returned mention_id is the index used by mention_status and other mention tools.",
            "parameters": CreateMentionArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_mention",
            "description": "Replace one existing mention by mention_id.",
            "parameters": EditMentionArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_mention",
            "description": "Delete one mention by mention_id.",
            "parameters": DeleteMentionArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schema_tool",
            "description": "Schema access for mention extraction. Returns CURIEs.",
            "parameters": SchemaToolArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_candidates",
            "description": "Search candidates for a mention using get_candidates_simple (strict + optional relaxed only). Fetches 30 candidates and returns summary only.",
            "parameters": SearchCandidatesArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_candidates",
            "description": "List stored candidates for a mention with pagination. Use after search_candidates when candidate_count > 1 or uncertain.",
            "parameters": ListCandidatesArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_candidate",
            "description": "Inspect one candidate with bounded triples (?p ?o). Use for top shortlist from list_candidates.",
            "parameters": DescribeCandidateArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "boost_candidates",
            "description": "Apply small score adjustments to stored candidates for a mention to adjust final ordering after inspection/rerank.",
            "parameters": BoostCandidatesArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rerank_mention",
            "description": "Fetch one-hop context for ALL current candidates for this mention and BM25 re-rank using provided keywords.",
            "parameters": RerankMentionArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mention_status",
            "description": "Get indexed mention status. Use this to list all mentions and mention_ids, or inspect one mention by mention_id.",
            "parameters": MentionStatusArgs.model_json_schema(),
        },
    },
]


# -----------------------------
# Tool registry (what run_tool_calling_loop uses)
# -----------------------------
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "create_mention": {
        "model": CreateMentionArgs,
        "takes_ctx": False,
        "takes_state": True,
        "logic": lambda state, **kw: create_mention(state=state, **kw),
    },
    "edit_mention": {
        "model": EditMentionArgs,
        "takes_ctx": False,
        "takes_state": True,
        "logic": lambda state, **kw: edit_mention(state=state, **kw),
    },
    "delete_mention": {
        "model": DeleteMentionArgs,
        "takes_ctx": False,
        "takes_state": True,
        "logic": lambda state, **kw: delete_mention(state=state, **kw),
    },
    "schema_tool": {
        "model": SchemaToolArgs,
        "takes_ctx": True,
        "takes_state": False,
        "logic": lambda ctx, **kw: schema_tool(ctx=ctx, **kw),
    },
    "probe_class_label_pred": {
        "model": ProbeClassLabelPredArgs,
        "takes_ctx": True,
        "takes_state": False,
        "logic": lambda ctx, **kw: probe_class_label_pred(ctx=ctx, **kw),
    },
    "search_candidates": {
        "model": SearchCandidatesArgs,
        "takes_ctx": True,
        "takes_state": True,
        "logic": lambda ctx, state, **kw: search_candidates(ctx=ctx, state=state, **kw),
    },
    "list_candidates": {
        "model": ListCandidatesArgs,
        "takes_ctx": False,
        "takes_state": True,
        "logic": lambda state, **kw: list_candidates(state=state, **kw),
    },
    "describe_candidate": {
        "model": DescribeCandidateArgs,
        "takes_ctx": True,
        "takes_state": False,
        "logic": lambda ctx, **kw: describe_candidate(ctx=ctx, **kw),
    },
    "boost_candidates": {
        "model": BoostCandidatesArgs,
        "takes_ctx": False,
        "takes_state": True,
        "logic": lambda state, **kw: boost_candidates(state=state, **kw),
    },
    "rerank_mention": {
        "model": RerankMentionArgs,
        "takes_ctx": True,
        "takes_state": True,
        "logic": lambda ctx, state, **kw: rerank_mention(ctx=ctx, state=state, **kw),
    },
    "mention_status": {
        "model": MentionStatusArgs,
        "takes_ctx": False,
        "takes_state": True,
        "logic": lambda state, **kw: mention_status(state=state, **kw),
    },
}


def build_mention_agent_system_prompt(
    description: str, *, allow_user_clarification: bool = True
) -> str:
    clarification_step = (
        "5) If status shows ambiguity or missing candidates, ask a concise clarification question."
        if allow_user_clarification
        else "5) Do best-effort only. If status shows ambiguity or missing candidates, do not ask the user; continue with the strongest available candidates."
    )
    completion_gate = (
        "Only finish when mention_status reports all mentions ready, or when you ask for user clarification."
        if allow_user_clarification
        else "Only finish when mention_status reports all mentions processed. Never ask for user clarification."
    )
    return replace_prompt_vars(
        MENTION_AGENT_SYSTEM_PROMPT,
        {
            "{kg_description}": description,
            "{clarification_step}": clarification_step,
            "{completion_gate}": completion_gate,
        },
    ).strip()


def _state_to_detailed_mentions(state: MentionState) -> List[DetailedMention]:
    detailed: List[DetailedMention] = []

    for mention_id, mention_data in enumerate(state.mentions):
        normalized_mention = _normalize_mention_payload(
            text=mention_data.get("text"),
            type_curie=mention_data.get("type"),
            label_pred=mention_data.get("label_pred"),
            attrs=mention_data.get("attrs"),
        )
        candidates = state.candidates_obj_by_mention_id.get(mention_id) or []
        selected_iri = candidates[0].uri if candidates else None
        detailed.append(
            DetailedMention(
                text=normalized_mention["text"],
                type=normalized_mention["type"],
                label_pred=normalized_mention["label_pred"],
                attrs=normalized_mention["attrs"],
                selected_candidate_iri=selected_iri,
                candidates=candidates,
            )
        )

    return detailed


def _detailed_mentions_to_text(mentions: List[DetailedMention]) -> str:
    if not mentions:
        return "No mentions yet."
    lines: List[str] = []
    for i, m in enumerate(mentions, start=1):
        lines.append(
            f"{i}. text={m.text}, type={m.type}, label_pred={m.label_pred}, attrs={m.attrs}"
        )
    return "\n".join(lines)


def _seed_state_from_detailed_mentions(
    *, ctx: SchemaIndex, state: MentionState, mentions: List[DetailedMention]
) -> None:
    state.mentions = []
    state.candidates_by_mention_id = {}
    state.candidates_obj_by_mention_id = {}

    for mention_id, mention in enumerate(mentions):
        state.mentions.append(
            _normalize_mention_payload(
                text=mention.text,
                type_curie=mention.type,
                label_pred=mention.label_pred,
                attrs=mention.attrs,
            )
        )

        candidates_obj = list(mention.candidates or [])
        state.candidates_obj_by_mention_id[mention_id] = candidates_obj

        preview: List[Dict[str, Any]] = []
        for idx, candidate in enumerate(candidates_obj):
            label = None
            variants = getattr(candidate, "variants", None) or []
            if variants and getattr(variants[0], "label", None):
                label = variants[0].label
            if not label:
                label = candidate.uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
            preview.append(
                {
                    "idx": idx,
                    "uri": compact_iri(candidate.uri, ctx),
                    "label": label,
                    "base_score": float(candidate.score or 0.0),
                }
            )
        state.candidates_by_mention_id[mention_id] = preview


async def run_entity_linking(
    *,
    ctx: SchemaIndex,
    question: str,
    model: str,
    kg_description: str | None = None,
    max_iterations: int = 50,
    max_message_history: int = 50,
    rerank_fallback: bool = True,
    allow_user_clarification: bool = True,
    previous_mentions: List[DetailedMention] | None = None,
    follow_up_message: str | None = None,
    on_tool_calls: Callable[[int, list[dict[str, Any]]], Awaitable[None] | None]
    | None = None,
    on_tool_result: Callable[[int, str | None, str, Any, str], Awaitable[None] | None]
    | None = None,
) -> MentionsAgentResult:
    """
    Run the tool-centric mentions agent and return DetailedMention objects.

    Fallback behavior:
      - if `rerank_mention` was not called by the agent, rerank all mention candidate
        lists once using keywords extracted from the question.
    """
    state = MentionState()
    if previous_mentions:
        _seed_state_from_detailed_mentions(
            ctx=ctx, state=state, mentions=previous_mentions
        )

    description = (kg_description or "").strip() or "Unavailable."
    system_prompt = build_mention_agent_system_prompt(
        description, allow_user_clarification=allow_user_clarification
    )
    editing_mode = bool(
        previous_mentions and follow_up_message and follow_up_message.strip()
    )

    user_prompt = question
    if editing_mode:
        system_prompt += (
            "\n\nEDITING MODE:\n"
            "- You are revising an existing mention state, not starting from scratch.\n"
            "- Preserve valid existing mentions where possible.\n"
            "- Apply only changes requested in the follow-up instruction.\n"
            "- Re-run candidate search for changed/new mentions.\n"
            "- Ensure final state is complete and consistent.\n\n"
            f"Existing mentions:\n{_detailed_mentions_to_text(previous_mentions or [])}\n\n"
        )
        user_prompt = (
            f"Original question:\n{user_prompt.strip()}\n"
            f"Follow-up instruction:\n{(follow_up_message or '').strip()}"
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    loop_result = await run_tool_calling_loop(
        state=state,
        model=model,
        messages=messages,
        tools=TOOLS,
        tool_registry=TOOL_REGISTRY,
        ctx=ctx,
        max_iterations=max_iterations,
        max_message_history=max_message_history,
        normalize_tool_name_fn=normalize_tool_name,
        on_tool_calls=on_tool_calls,
        on_tool_result=on_tool_result,
    )

    if rerank_fallback:
        keyword_source = f"{question} {(follow_up_message or '').strip()}".strip()
        keyword_mentions = (
            [Mention(text=keyword_source, type="", label_pred="", attrs={})]
            if keyword_source
            else []
        )
        keywords = sorted(
            extract_keywords_from_mentions(keyword_mentions, min_length=2)
        )[:20]
        if keywords:
            status_rows = _mention_status_rows(state)
            missing_rerank_ids = [
                row.mention_id
                for row in status_rows
                if row.candidate_count > 0 and not row.reranked
            ]
            if missing_rerank_ids:
                LOGGER.warning(
                    "Reranking fallback triggered ids=%s", missing_rerank_ids
                )
            for mention_id in missing_rerank_ids:
                try:
                    await rerank_mention(
                        ctx=ctx,
                        state=state,
                        mention_id=mention_id,
                        keywords=keywords,
                    )
                except Exception:
                    LOGGER.exception(
                        "rerank fallback failed for mention_id=%s", mention_id
                    )

    mentions = _state_to_detailed_mentions(state)
    status_rows = _mention_status_rows(state)
    assistant_message = (loop_result.get("final_answer") or "").strip() or None
    return MentionsAgentResult(
        mentions=mentions,
        assistant_message=assistant_message,
        status=status_rows,
    )
