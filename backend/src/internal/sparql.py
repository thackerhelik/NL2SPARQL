import re

import httpx
from pyparsing.exceptions import ParseException
from rdflib.namespace import RDF
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.term import URIRef
from sparqlx import SPARQLWrapper
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt
from tenacity.wait import wait_exponential

from src.internal.schema_index import render_prefixes_for_query
from src.internal.utils import LOGGER
from src.schemas.run_query import RunQueryResponse
from src.schemas.schema_index import SchemaIndex

SANTIZE_1 = re.compile(r"^```(?:sparql)?\s*", re.IGNORECASE)
SANTIZE_2 = re.compile(r"\s*```$", re.MULTILINE)
_FOUND_FORM_RE = re.compile(r"found '([A-Za-z]+)'")
_FORM_EXPECTATION_MSG = (
    "Expected {SelectQuery | ConstructQuery | DescribeQuery | AskQuery}"
)


class DisallowedQueryTypeError(ValueError):
    pass


def sanitize_query(q: str) -> str:
    q = re.sub(SANTIZE_1, "", q)
    q = re.sub(SANTIZE_2, "", q)
    return q.strip()


def _collect_schema_terms(node, _seen=None):
    """
    Walk rdflib algebra and yield:
      - All predicate IRIs in triple patterns
      - All rdf:type object IRIs (class references)
    """
    if _seen is None:
        _seen = set()

    node_id = id(node)
    if node_id in _seen:
        return
    _seen.add(node_id)

    if isinstance(node, CompValue):
        if node.name == "BGP":
            for _s, p, o in node.get("triples", []):
                if isinstance(p, URIRef):
                    yield p

                if p == RDF.type and isinstance(o, URIRef):
                    yield o

        for value in node.values():
            yield from _collect_schema_terms(value, _seen)

    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _collect_schema_terms(item, _seen)


def validate_schema_usage(query: str, idx: SchemaIndex) -> None:
    """
    Validate that:
      1. All PREFIX namespace IRIs are declared in the SchemaIndex
      2. All predicates and rdf:type classes belonging to the base IRI
         exist in the SchemaIndex (idx.props / idx.classes)
    """
    try:
        parsed = parseQuery(query)
    except Exception as e:
        raise ValueError(f"Could not parse query for schema validation: {e}") from e

    prologue = parsed[0]
    valid_namespaces = set(idx.namespaces.values())
    base_iri = getattr(idx, "base_iri", None)
    try:
        prepared = prepareQuery(query)
    except Exception as e:
        raise ValueError(f"Could not prepare query: {e}") from e

    prologue = prepared.prologue
    declared_prefixes = prologue.namespace_manager.namespaces()

    valid_namespaces = set(idx.namespaces.values())

    for prefix, namespace in declared_prefixes:
        iri = str(namespace)

        if iri not in valid_namespaces:
            raise ValueError(
                f"Invalid namespace IRI <{iri}> for prefix '{prefix}'. "
                "This namespace is not registered in the schema index."
            )
    if not base_iri:
        return

    try:
        prepared = prepareQuery(query)
    except Exception as e:
        raise ValueError(f"Could not prepare query for schema validation: {e}") from e

    for iri in _collect_schema_terms(prepared.algebra):
        iri_str = str(iri)

        if not iri_str.startswith(base_iri):
            continue

        if iri_str in idx.props or iri_str in idx.classes:
            continue

        raise ValueError(f"Term <{iri_str}> not found in schema.")


def _collect_iris(node, _seen=None):
    """
    Recursively walk an rdflib algebra node and yield every URIRef found.
    Handles dicts, lists, and algebra CompValue objects.
    """
    if _seen is None:
        _seen = set()

    node_id = id(node)
    if node_id in _seen:
        return
    _seen.add(node_id)

    if isinstance(node, URIRef):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _collect_iris(v, _seen)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _collect_iris(item, _seen)
    elif hasattr(node, "__dict__"):
        for v in vars(node).values():
            yield from _collect_iris(v, _seen)


def validate_query(query: str, ctx=None) -> str:
    clean_query = sanitize_query(query)
    try:
        parsed_query = parseQuery(clean_query)
    except ParseException as e:
        parse_error_text = str(e)
        if _FORM_EXPECTATION_MSG in parse_error_text:
            match = _FOUND_FORM_RE.search(str(e))
            query_form = match.group(1) if match else "UNKNOWN"
            raise DisallowedQueryTypeError(
                f"Query form '{query_form}' is not allowed."
            ) from e
        LOGGER.error(f"SPARQL Parsing failed for query: {clean_query[:100]}...")
        raise ValueError(f"Invalid SPARQL syntax: {str(e)}") from e
    except Exception as e:
        LOGGER.error(f"SPARQL Parsing failed for query: {clean_query[:100]}...")
        raise ValueError(f"Invalid SPARQL syntax: {str(e)}") from e
    query_type = getattr(parsed_query[1], "name", "")
    if query_type == "ConstructQuery":
        raise DisallowedQueryTypeError("Query form 'CONSTRUCT' is not allowed.")

    validate_schema_usage(clean_query, ctx)

    full_query = (
        f"{render_prefixes_for_query(ctx, clean_query)}\n\n{clean_query}".strip()
    )

    return full_query


async def run(
    endpoint: str, query: str, ctx, debug: bool = False, validate: bool = False
) -> RunQueryResponse:
    if validate:
        query = validate_query(query, ctx)
    else:
        query = sanitize_query(query)

    if ctx is not None and "PREFIX" not in query.upper():
        query = f"{render_prefixes_for_query(ctx, query)}\n\n{query}".strip()

    if debug:
        LOGGER.debug(f"SPARQL Query:\n{query}")

    s = SPARQLWrapper(
        endpoint,
        query_method="POST",
        aclient_config={
            "timeout": 60.0,
            "headers": {"User-Agent": "NL2SPARQL/0.1 (jeffry.cacho@rwth-aachen.de)"},
        },
    )

    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(
                lambda exc: isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code == 429
            ),
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            reraise=True,
        ):
            with attempt:
                result = await s.aquery(query)
        return RunQueryResponse(**result.json())
    except Exception as e:
        LOGGER.error(f"SPARQL Endpoint error at {endpoint}: {e}")
        raise
