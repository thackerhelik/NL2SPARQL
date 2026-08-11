from collections import defaultdict
import re
import traceback
from typing import Dict, List
import unicodedata

from src.internal import sparql
from src.internal.schema_index import curie_to_iri, is_string_label_pred, make_curie
from src.internal.utils import LOGGER, normalize_text, timed_async
from src.schemas.mentions import Candidate, CandidateVariant, Mention
from src.schemas.schema_index import SchemaIndex


def _values_block(var: str, terms: list[str]) -> str:
    if not terms:
        return f"VALUES ?{var} {{}}"
    items = []
    for t in terms:
        t = (t or "").strip()
        if not t:
            continue
        if t.startswith("<") and t.endswith(">"):
            items.append(t)
        elif "://" in t:
            items.append(f"<{t}>")
        elif ":" in t:
            items.append(t)  # CURIE
        else:
            items.append(f"<{t}>")
    return f"VALUES ?{var} {{ {' '.join(items)} }}"


def cell(v):
    if hasattr(v, "value"):
        return v.value
    return v.get("value") if isinstance(v, dict) else v


def rows_to_candidates(rows, role_name: str, mention_text: str) -> List[Candidate]:
    grouped: Dict[str, List[CandidateVariant]] = defaultdict(list)
    normalized_mention = normalize_text(mention_text)

    for r in rows:
        uri = cell(r.get("s"))
        pred = cell(r.get("p"))
        label = cell(r.get("label"))

        if not uri or not pred:
            continue

        try:
            exact = int(float(cell(r.get("exact")))) if r.get("exact") else 0
        except Exception:
            exact = 0

        # Accent-insensitive exact match fallback in Python
        if not exact and isinstance(label, str):
            exact = int(normalize_text(label) == normalized_mention)

        try:
            tokens_matched = (
                int(float(cell(r.get("tokensMatched"))))
                if r.get("tokensMatched")
                else 0
            )
        except Exception:
            tokens_matched = 0

        try:
            degree = int(float(cell(r.get("degree")))) if r.get("degree") else 0
        except Exception:
            degree = 0

        grouped[uri].append(
            CandidateVariant(
                uri=uri,
                pred=pred,
                label=label,
                role=role_name,
                match_exact=bool(exact),
                tokens_matched=tokens_matched,
                degree=degree,
            )
        )

    out = []
    for uri, variants in grouped.items():
        # Candidate overall matches are the max of its variants
        max_tokens = max((v.tokens_matched for v in variants), default=0)
        max_degree = max((v.degree for v in variants), default=0)
        has_exact = any(v.match_exact for v in variants)
        out.append(
            Candidate(
                uri=uri,
                variants=variants,
                tokens_matched=max_tokens,
                degree=max_degree,
                match_exact=has_exact,
            )
        )
    return out


def literal_predicates_for_type(idx: SchemaIndex, type_curie: str) -> list[str]:
    class_iri = curie_to_iri(type_curie, idx.namespaces)
    preds: list[str] = []
    for prop in idx.props.values():
        if class_iri not in (prop.domains or set()):
            continue
        if not prop.literal_datatypes:
            continue
        preds.append(make_curie(prop.iri, idx.namespaces))
    return sorted(set(preds))


def build_candidate_query_from_mention(
    idx,
    mention,
    limit: int = 50,
    strict: bool = True,
    validate_label_pred: bool = True,
) -> str:
    """
    Build candidate query using:
      - mention.type        -> class
      - mention.label_pred  -> EXACT predicate to match labels
    """

    ok, resolved_type = is_string_label_pred(idx, mention.type, mention.label_pred)
    if not ok:
        error = f"Invalid label_pred for type: {mention.type} / {mention.label_pred}"
        LOGGER.error(error)
        if validate_label_pred:
            raise ValueError(error)
    if resolved_type and resolved_type != mention.type:
        mention.type = resolved_type

    # Remove zero-width spaces, soft hyphens, and other invisible formatting characters
    clean_text = re.sub(
        r"[\u00AD\u200B-\u200D\uFEFF]", "", (mention.text or "")
    ).strip()
    if clean_text.endswith("."):
        clean_text = clean_text.rstrip(".")
    q_esc = clean_text.strip('"').replace('"', '\\"')

    vals_cls = _values_block("cls", [mention.type])
    vals_p = _values_block("p", [mention.label_pred])

    if strict:
        filter_clause = f'FILTER(CONTAINS(LCASE(STR(?label)), LCASE("{q_esc}")))'
        select_extras = ""
        order_extras = ""
    else:
        # Match all tokens found in mention text, split by non-word characters to get initials (supporting unicode)
        # Normalize to NFC to prevent splitting on decomposed accents
        clean_norm = unicodedata.normalize("NFC", clean_text)
        tokens = [t for t in re.split(r"[^\w]", clean_norm) if t]

        conditions = []
        token_scores = []
        for t in tokens:
            t_esc = t.replace('"', '\\"')  # Escape double quotes for sparql string

            # Create an unaccented version of the token to support databases that strip accents
            t_unaccented = "".join(
                c
                for c in unicodedata.normalize("NFD", t)
                if unicodedata.category(c) != "Mn"
            )
            t_unaccented_esc = t_unaccented.replace('"', '\\"')

            if len(t) == 1:
                # Single letter: Matches start of word (initials or full words starting with letter)
                cond = f'REGEX(STR(?label), "(^|\\\\W){t_esc}", "i")'
                if t_unaccented != t:
                    cond = f'({cond} || REGEX(STR(?label), "(^|\\\\W){t_unaccented_esc}", "i"))'
            else:
                cond = f'CONTAINS(LCASE(STR(?label)), LCASE("{t_esc}"))'
                if t_unaccented != t:
                    cond = f'({cond} || CONTAINS(LCASE(STR(?label)), LCASE("{t_unaccented_esc}")))'

            conditions.append(cond)
            token_scores.append(f"IF({cond}, 1, 0)")

        if conditions:
            filter_clause = f"FILTER({' || '.join(conditions)})"
            token_score_expr = " + ".join(token_scores)
            select_extras = f"\n       ({token_score_expr} AS ?tokensMatched)"
            order_extras = " DESC(?tokensMatched)"
        else:
            # Fallback to strict case if no tokens found
            filter_clause = f'FILTER(CONTAINS(LCASE(STR(?label)), LCASE("{q_esc}")))'
            select_extras = ""
            order_extras = ""

    # Note: Right now we are assuming xsd:string or label english labels.
    query = rf"""SELECT ?s ?p ?label (STRLEN(STR(?label)) AS ?labelLen)
       (IF(LCASE(REPLACE(STR(?label), "\\.$", ""))=LCASE("{q_esc}"), 1, 0) AS ?exact)
       (COUNT(?extra_o) AS ?degree){select_extras}
WHERE {{
  {vals_cls}
  {vals_p}
  ?s a ?cls ; ?p ?label .
  FILTER(isLiteral(?label))
  {filter_clause}
  FILTER(LANG(?label) = "" || LANGMATCHES(LANG(?label), "en"))
  OPTIONAL {{ ?s ?extra_p ?extra_o }}
}}
GROUP BY ?s ?p ?label
ORDER BY DESC(?exact){order_extras} DESC(?degree) ASC(?labelLen) LCASE(STR(?label))
LIMIT {int(limit)}
""".strip()
    return query


def refine_query_with_attrs(idx: SchemaIndex, og_query: str, mention: Mention) -> str:
    if not mention.attrs:
        LOGGER.warning("Refine query called with no attrs")
        return og_query

    class_iri = curie_to_iri(mention.type, idx.namespaces)

    # only literal predicates on this class
    literal_props = []
    for p in idx.props.values():
        if class_iri in (p.domains or set()) and p.literal_datatypes:
            literal_props.append(p)

    def _norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())

    # map key -> predicate CURIE
    key_to_pred: Dict[str, str] = {}
    for p in literal_props:
        p_curie = make_curie(p.iri, idx.namespaces)
        if getattr(p, "labels", None):
            for lab in p.labels:
                key_to_pred[_norm(lab)] = p_curie
        key_to_pred[_norm(p_curie.split(":", 1)[-1])] = p_curie

    triples = []
    filters = []

    for k, v in (mention.attrs or {}).items():
        p_curie = key_to_pred.get(_norm(k))
        if not p_curie:
            continue

        var = f"?v_{_norm(k) or 'attr'}"
        triples.append(f"?s {p_curie} {var} .")

        v_esc = str(v).replace('"', '\\"')
        filters.append(f'FILTER(CONTAINS(LCASE(STR({var})), LCASE("{v_esc}")))')

    if not triples:
        LOGGER.warning("Refine query found no matching attrs")
        return og_query

    insert_block = "\n  " + "\n  ".join(triples + filters) + "\n"

    q = og_query

    # Insert before the closing brace of WHERE that is followed by query modifiers
    m = re.search(
        r"\}\s*(ORDER\s+BY|GROUP\s+BY|HAVING|LIMIT|OFFSET)\b", q, flags=re.IGNORECASE
    )
    if m:
        brace_pos = m.start()
        return q[:brace_pos] + insert_block + q[brace_pos:]

    # Fallback: insert before the last '}' in the query
    last = q.rfind("}")
    if last != -1:
        return q[:last] + insert_block + q[last:]

    return q


@timed_async()
async def get_candidates_with_fallback(
    ctx: SchemaIndex, mention: Mention, limit: int = 30
) -> List[Candidate]:
    role_name = mention.type
    base_q = None

    try:
        base_q = build_candidate_query_from_mention(
            ctx, mention, limit=limit, strict=True
        )
    except Exception:
        pass

    try:
        candidates: List[Candidate] = []

        if base_q is not None:
            result = await sparql.run(ctx.endpoint, base_q, ctx=ctx)
            base_rows = result.results.bindings
            candidates = rows_to_candidates(base_rows, role_name, mention.text)
            LOGGER.info(
                f"Candidates fetched mention={mention.text} count={len(candidates)}"
            )

        if not candidates and base_q:
            try:
                relaxed_q = build_candidate_query_from_mention(
                    ctx, mention, limit=limit, strict=False
                )
                result = await sparql.run(ctx.endpoint, relaxed_q, ctx=ctx)
                base_rows = result.results.bindings
                candidates = rows_to_candidates(base_rows, role_name, mention.text)
                if candidates:
                    base_q = relaxed_q
                LOGGER.info(
                    f"Relaxed candidates fetched mention={mention.text} count={len(candidates)}"
                )
            except Exception as e:
                LOGGER.debug(f"Relaxed candidate fetch failed error={e}")

        # Edge case: LLM got the wrong label_pred, try other literal preds for type (linear consider parallelization?)
        used_preds = {mention.label_pred}
        if not candidates:
            for pred in literal_predicates_for_type(ctx, mention.type):
                if pred in used_preds:
                    continue
                used_preds.add(pred)
                mention.label_pred = pred

                try:
                    base_q = build_candidate_query_from_mention(
                        ctx, mention, limit=limit, strict=True
                    )
                    result = await sparql.run(ctx.endpoint, base_q, ctx=ctx)
                    base_rows = result.results.bindings
                    alt_candidates = rows_to_candidates(
                        base_rows, role_name, mention.text
                    )

                    # Try relaxed search if strict fails
                    if not alt_candidates:
                        relaxed_q = build_candidate_query_from_mention(
                            ctx, mention, limit=limit, strict=False
                        )
                        result = await sparql.run(ctx.endpoint, relaxed_q, ctx=ctx)
                        base_rows = result.results.bindings
                        alt_candidates = rows_to_candidates(
                            base_rows, role_name, mention.text
                        )
                        if alt_candidates:
                            base_q = relaxed_q

                    candidates.extend(alt_candidates)
                    LOGGER.info(
                        f"Candidates fetched mention={mention.text} pred={pred} count={len(alt_candidates)}"
                    )
                    if len(candidates):
                        break
                except Exception as e:
                    LOGGER.error(
                        f"Alternate candidate fetch failed mention={mention.text} pred={pred} error={e}"
                    )

        LOGGER.info(base_q)  # base_q can be base or relaxed query

        # Edge case: We got too many candidates, refine with attrs
        saturated = len(candidates) >= limit
        if saturated and mention.attrs:  # force refinement only when we have attrs
            LOGGER.info(f"Refining candidates mention={mention.text}")
            refined_q = refine_query_with_attrs(ctx, base_q, mention)
            LOGGER.debug(f"Refined query={sparql.sanitize_query(refined_q)}")
            result = await sparql.run(ctx.endpoint, refined_q, ctx=ctx)
            refined_rows = result.results.bindings
            return rows_to_candidates(refined_rows, role_name, mention.text)
        return candidates
    except Exception:
        LOGGER.debug(traceback.format_exc())
        # If base failed and we have attrs, try refined once
        if mention.attrs:
            try:
                refined_q = refine_query_with_attrs(ctx, base_q, mention)
                result = await sparql.run(ctx.endpoint, refined_q, ctx=ctx, debug=True)
                refined_rows = result.results.bindings
                return rows_to_candidates(refined_rows, role_name, mention.text)
            except Exception:
                LOGGER.error(traceback.format_exc())
                LOGGER.warning(f"Candidate refinement failed mention={mention.text}")
                # fall through to empty list on double failure
                return []
        # No attrs -> nothing else to try
        LOGGER.warning(f"Candidate fetch failed mention={mention.text}")
        return []


@timed_async()
async def get_candidates_simple(
    ctx: SchemaIndex,
    mention: Mention,
    limit: int = 30,
    relaxed_fallback: bool = True,
) -> List[Candidate]:
    role_name = mention.type

    # Strict query
    q = build_candidate_query_from_mention(
        ctx, mention, limit=limit, strict=True, validate_label_pred=False
    )
    result = await sparql.run(ctx.endpoint, q, ctx=ctx, debug=True)
    rows = result.results.bindings
    candidates = rows_to_candidates(rows, role_name, mention.text)

    if candidates or not relaxed_fallback:
        return candidates

    # Optional relaxed retry
    q_relaxed = build_candidate_query_from_mention(
        ctx, mention, limit=limit, strict=False, validate_label_pred=False
    )
    result_relaxed = await sparql.run(ctx.endpoint, q_relaxed, ctx=ctx)
    rows_relaxed = result_relaxed.results.bindings
    return rows_to_candidates(rows_relaxed, role_name, mention.text)
