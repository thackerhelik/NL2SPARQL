from typing import List

from src.internal import sparql
from src.internal.utils import LOGGER, timed_async
from src.schemas.mentions import OneHopTriple
from src.schemas.schema_index import SchemaIndex


def _get_priority_blocks(
    keywords: List[str], target_var: str = "?value"
) -> tuple[str, str]:
    if not keywords:
        return "", ""

    conditions = []
    for w in keywords:
        w_esc = str(w).replace('"', '\\"')
        conditions.append(
            f'IF(CONTAINS(LCASE(STR({target_var})), LCASE("{w_esc}")), 1, 0)'
        )

    score_expr = " + ".join(conditions)
    bind_score = f"BIND(({score_expr}) AS ?priority)"
    order_by = f"ORDER BY DESC(?priority) LCASE(STR({target_var}))"

    return bind_score, order_by


def build_onehop_literals(iri: str, keywords: List[str] = None, limit: int = 50) -> str:
    keywords = keywords or []
    bind_score, order_by = _get_priority_blocks(keywords, "?value")
    return f"""SELECT ?p (STR(?o) AS ?value)
WHERE {{
  VALUES ?s {{ <{iri}> }}
  ?s ?p ?o .
  MINUS {{ ?s rdf:type ?o }}
  FILTER(isLiteral(?o))
  {bind_score}
}}
{order_by}
LIMIT {int(limit)}
""".strip()


def build_onehop_iris(iri: str, keywords: List[str] = None, limit: int = 50) -> str:
    keywords = keywords or []
    bind_score, order_by = _get_priority_blocks(keywords, "?value")
    return f"""SELECT ?p ?value
WHERE {{
  VALUES ?s {{ <{iri}> }}
  ?s ?p ?o .
  MINUS {{ ?s rdf:type ?o }}
  FILTER(isIRI(?o))

  OPTIONAL {{ ?o rdfs:label  ?lab  . FILTER(isLiteral(?lab)) }}
  OPTIONAL {{ ?o foaf:name   ?nm   . FILTER(isLiteral(?nm))  }}
  OPTIONAL {{ ?o schema:name ?snm  . FILTER(isLiteral(?snm)) }}

  BIND(COALESCE(?lab, ?nm, ?snm, STR(?o)) AS ?value)
  {bind_score}
}}
{order_by}
LIMIT {int(limit)}
""".strip()


def build_onehop_iris_in(iri: str, keywords: List[str] = None, limit: int = 50) -> str:
    keywords = keywords or []
    bind_score, order_by = _get_priority_blocks(keywords, "?value")
    return f"""SELECT ?p ?value
WHERE {{
  VALUES ?center {{ <{iri}> }}
  ?s ?p ?center .
  FILTER(isIRI(?s))

  OPTIONAL {{ ?s rdfs:label  ?lab  . FILTER(isLiteral(?lab)) }}
  OPTIONAL {{ ?s foaf:name   ?nm   . FILTER(isLiteral(?nm))  }}
  OPTIONAL {{ ?s schema:name ?snm  . FILTER(isLiteral(?snm)) }}

  BIND(COALESCE(?lab, ?nm, ?snm, STR(?s)) AS ?value)
  {bind_score}
}}
{order_by}
LIMIT {int(limit)}
""".strip()


@timed_async()
async def onehop_readable(
    ctx: SchemaIndex, iri: str, keywords: List[str] = None, limit_each: int = 50
) -> List[OneHopTriple]:
    """Fetch one hop triples around iri and merge into a clean list."""
    rows = []

    result1 = await sparql.run(
        ctx.endpoint, build_onehop_literals(iri, keywords, limit_each), ctx=ctx
    )
    rows += result1.results.bindings

    result2 = await sparql.run(
        ctx.endpoint, build_onehop_iris(iri, keywords, limit_each), ctx=ctx
    )
    rows += result2.results.bindings

    result3 = await sparql.run(
        ctx.endpoint, build_onehop_iris_in(iri, keywords, limit_each), ctx=ctx
    )
    rows += result3.results.bindings

    def cell(b, k):
        v = b.get(k)
        if hasattr(v, "value"):
            return v.value
        return v.get("value") if isinstance(v, dict) else v

    out: list[OneHopTriple] = []
    seen = set()

    for r in rows:
        p = cell(r, "p")
        v = cell(r, "value")
        if not p or not v:
            continue
        key = (p, v)
        if key in seen:
            continue
        seen.add(key)
        out.append(OneHopTriple(p=p, value=v))

    LOGGER.info(f"One-hop context end uri={iri} triples={len(out)}")
    return out
