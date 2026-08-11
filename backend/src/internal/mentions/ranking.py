from collections import Counter
import math
import re
from typing import List

from src.internal.utils import normalize_text
from src.schemas.mentions import Candidate
from src.schemas.schema_index import SchemaIndex


def simplify_predicate(predicate: str, ctx: SchemaIndex) -> str:
    """
    If predicate is an IRI, try to shorten to CURIE using ctx.namespaces.
    Otherwise return as-is (for CURIEs) or fallback to localname.
    """
    predicate = (predicate or "").strip()
    if not predicate:
        return predicate

    # Already a CURIE
    if ":" in predicate and not predicate.startswith("http"):
        return predicate

    # Try CURIE shortening for full IRIs using namespaces
    if predicate.startswith("http"):
        # prefer longest matching namespace IRI (avoid collisions)
        best_pfx = None
        best_base = None
        for pfx, base in (ctx.namespaces or {}).items():
            if predicate.startswith(base) and (
                best_base is None or len(base) > len(best_base)
            ):
                best_pfx = pfx
                best_base = base
        if best_pfx and best_base:
            return f"{best_pfx}:{predicate[len(best_base) :]}"

        # fallback: localname
        return predicate.rsplit("#", 1)[-1].rsplit("/", 1)[-1]

    return predicate


def candidate_to_text(candidate: Candidate, ctx: SchemaIndex) -> str:
    sentences: list[str] = []

    for variant in candidate.variants:
        if variant.label:
            sentences.append(f"label {variant.label}")

    for triple in candidate.context:
        pred = triple.p
        value = triple.value
        if pred and value:
            simple_pred = simplify_predicate(pred, ctx)
            sentences.append(f"{simple_pred} {value}")

    text = " . ".join(sentences)
    return text


def bm25_score(
    ctx: SchemaIndex, keywords: List[str], candidates: List[Candidate], k1=1.5, b=0.75
):
    docs = [candidate_to_text(c, ctx) for c in candidates]

    # Tokenize and normalize query terms
    query_terms = []
    for k in keywords:
        query_terms.extend(re.findall(r"\w+", normalize_text(k)))

    # Tokenize and normalize documents
    tokenized = [re.findall(r"\w+", normalize_text(d)) for d in docs]

    N = len(docs)
    if N == 0:
        return candidates

    avgdl = sum(len(d) for d in tokenized) / N if N else 1

    for i, d in enumerate(tokenized):
        dl = len(d)
        tf = Counter(d)
        bm25 = 0.0
        for t in query_terms:
            n_t = sum(t in doc for doc in tokenized)
            if n_t == 0:
                continue

            # Using BM25L/Lucene IDF formula to prevent negative scores
            idf = math.log(1.0 + (N - n_t + 0.5) / (n_t + 0.5))

            tf_td = tf[t]
            norm = tf_td * (k1 + 1) / (tf_td + k1 * (1 - b + b * dl / avgdl))
            bm25 += idf * norm

        # --- Hybrid Scoring Logic ---
        # 1. Start with BM25 base
        score = bm25

        # 2. Significant boost for exact matches from SPARQL stage
        if candidates[i].match_exact:
            score += 100.0

        # 3. Boost for token overlap count from SPARQL stage (Massive weight to prevent popularity bias)
        score += float(candidates[i].tokens_matched) * 50.0

        # 4. Tie-breaker based on graph degree (popularity)
        if candidates[i].degree > 0:
            score += math.log10(float(candidates[i].degree) + 1.0) * 0.1

        candidates[i].score = score

    return sorted(candidates, key=lambda x: (x.score or 0.0), reverse=True)
