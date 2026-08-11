import asyncio
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from rdflib.plugins.sparql.parser import parseQuery

from src.internal.schema_index import _get_ancestors, expr_to_compact_string
from src.internal.sparql import DisallowedQueryTypeError, run, sanitize_query
from src.internal.utils import LOGGER
from src.schemas.query_generation import Function, Tool
from src.schemas.schema_index import SchemaIndex


class EmptyArgs(BaseModel):
    pass


class DescribeClassArgs(BaseModel):
    class_iri: str = Field(
        ..., description="The full IRI of the RDF class to describe."
    )


class DescribePropertyArgs(BaseModel):
    prop_iri: str = Field(
        ..., description="The full IRI of the RDF property to describe."
    )


class ClassIriArgs(BaseModel):
    class_iri: str = Field(..., description="The full IRI of the RDF class.")


class ValidateSparqlArgs(BaseModel):
    query: str = Field(..., description="The SPARQL query string to validate.")


class RunSparqlArgs(BaseModel):
    query: str = Field(
        ...,
        description="The SPARQL query string to execute against the active endpoint of the RDF dataset.",
    )


RUN_QUERY_TIMEOUT_SECONDS = 30.0
RUN_QUERY_SAMPLE_SIZE = 5


def _summarize_run_response(result: Any) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}

    if result.boolean is not None:
        summary["boolean"] = result.boolean

    vars_list = result.head.vars if result.head and result.head.vars else []
    bindings = (
        result.results.bindings
        if result.results is not None and result.results.bindings is not None
        else []
    )
    summary["vars"] = vars_list
    summary["row_count"] = len(bindings)
    sample_bindings = []
    for row in bindings[:RUN_QUERY_SAMPLE_SIZE]:
        sample_bindings.append({key: value.value for key, value in row.items()})
    summary["sample_bindings"] = sample_bindings
    return summary


def get_outgoing_properties(idx: SchemaIndex, class_iri: str) -> List[Dict[str, Any]]:
    """
    Returns properties where the input class (or its superclasses) is the domain.
    """
    if class_iri not in idx.classes:
        return []

    # Get the class and all its ancestors to include inherited properties
    family_tree = _get_ancestors(idx, class_iri)
    outgoing = []

    for p in idx.props.values():
        # If any domain of the property is in the class's ancestor tree
        if any(dom in family_tree for dom in p.domains):
            label = p.labels[0] if p.labels else p.iri.split("/")[-1].split("#")[-1]
            outgoing.append(
                {
                    "iri": p.iri,
                    "label": label,
                    "range": sorted(list(p.range_classes) + list(p.literal_datatypes)),
                }
            )

    return sorted(outgoing, key=lambda x: x["label"].lower())


def get_incoming_properties(idx: SchemaIndex, class_iri: str) -> List[Dict[str, Any]]:
    """
    Returns properties where the input class is explicitly listed as the range.
    """
    if class_iri not in idx.classes:
        return []

    incoming = []
    for p in idx.props.values():
        # Range is typically specific, so we check if the class_iri is in range_classes
        if class_iri in p.range_classes:
            label = p.labels[0] if p.labels else p.iri.split("/")[-1].split("#")[-1]
            incoming.append(
                {"iri": p.iri, "label": label, "domain": sorted(list(p.domains))}
            )

    return sorted(incoming, key=lambda x: x["label"].lower())


def list_classes(idx: SchemaIndex) -> List[Dict[str, str]]:
    out = []
    for c in idx.classes.values():
        label = c.labels[0] if c.labels else c.iri.split("/")[-1]
        out.append({"iri": c.iri, "label": label})
    return sorted(out, key=lambda x: x["label"].lower())


def describe_class(idx: SchemaIndex, class_iri: str) -> Optional[Dict]:
    c = idx.classes.get(class_iri)
    if not c:
        return None

    def compact(exprs):
        return [expr_to_compact_string(e, idx.namespaces) for e in (exprs or [])]

    return {
        "iri": c.iri,
        "labels": c.labels,
        "comments": c.comments,
        "super_classes": sorted(c.super_classes),
        "super_class_exprs": compact(getattr(c, "super_class_exprs", [])),
        "equivalent_class_exprs": compact(getattr(c, "equivalent_class_exprs", [])),
    }


def list_properties(idx: SchemaIndex) -> List[Dict[str, Any]]:
    out = []
    for p in idx.props.values():
        label = p.labels[0] if p.labels else p.iri.split("/")[-1]

        # Combine ranges into a single descriptive list
        ranges = sorted(list(p.range_classes) + list(p.literal_datatypes))
        domains = sorted(list(p.domains))

        out.append({"iri": p.iri, "label": label, "domains": domains, "ranges": ranges})
    return sorted(out, key=lambda x: x["label"].lower())


def describe_property(idx: SchemaIndex, prop_iri: str) -> Optional[Dict]:
    p = idx.props.get(prop_iri)
    if not p:
        return None

    return {
        "iri": p.iri,
        "labels": p.labels,
        "comments": getattr(p, "comments", []),
        "domains": sorted(p.domains),
        "range_classes": sorted(p.range_classes),
        "literal_datatypes": sorted(p.literal_datatypes),
        "super_properties": sorted(getattr(p, "super_properties", set())),
        "equivalent_properties": sorted(getattr(p, "equivalent_properties", set())),
        "inverse_properties": sorted(p.inverses),
    }


def validate_sparql(query: str) -> Dict[str, Any]:
    try:
        parseQuery(query)
        return {"valid": True, "error": None}
    except Exception as e:
        return {"valid": False, "error": str(e)}


async def run_sparql_query(idx: SchemaIndex, query: str) -> Dict[str, Any]:
    executed_query = sanitize_query(query)
    if not idx.endpoint:
        return {
            "ok": False,
            "error_type": "endpoint",
            "error_message": "No endpoint configured for active schema.",
            "summary": {},
            "executed_query": executed_query,
        }

    try:
        result = await asyncio.wait_for(
            run(endpoint=idx.endpoint, query=executed_query, validate=True, ctx=idx),
            timeout=RUN_QUERY_TIMEOUT_SECONDS,
        )
        return {
            "ok": True,
            "error_type": None,
            "error_message": None,
            "summary": _summarize_run_response(result),
            # "executed_query": executed_query,
        }
    except TimeoutError:
        LOGGER.error(
            f"SPARQL query execution timed out after {RUN_QUERY_TIMEOUT_SECONDS:.0f}s."
        )
        return {
            "ok": False,
            "error_type": "timeout",
            "error_message": (
                f"Query execution timed out after {RUN_QUERY_TIMEOUT_SECONDS:.0f}s."
            ),
            "summary": {},
            "executed_query": executed_query,
        }
    except DisallowedQueryTypeError as e:
        LOGGER.error(f"Disallowed query type: {str(e)}")
        return {
            "ok": False,
            "error_type": "forbidden",
            "error_message": str(e),
            "summary": {},
            "executed_query": executed_query,
        }
    except ValueError as e:
        LOGGER.error(f"Query validation error: {str(e)}")
        return {
            "ok": False,
            "error_type": "syntax",
            "error_message": str(e),
            "summary": {},
            "executed_query": executed_query,
        }
    except Exception as e:
        LOGGER.error(f"Unexpected error during query execution: {str(e)}")
        return {
            "ok": False,
            "error_type": "endpoint",
            "error_message": str(e),
            "summary": {},
            "executed_query": executed_query,
        }


TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "list_classes": {
        "logic": list_classes,
        "model": EmptyArgs,
        "description": "List all classes in the RDF schema with IRIs and labels.",
        "takes_ctx": True,
    },
    "describe_class": {
        "logic": describe_class,
        "model": DescribeClassArgs,
        "description": "Get labels, comments, and super-classes for a given class.",
        "takes_ctx": True,
    },
    "get_outgoing_properties": {
        "logic": get_outgoing_properties,
        "model": ClassIriArgs,
        "description": "Get all properties (attributes/relations) where this class or its parents are the domain.",
        "takes_ctx": True,
    },
    "get_incoming_properties": {
        "logic": get_incoming_properties,
        "model": ClassIriArgs,
        "description": "Get all properties where this class is the expected range/value type.",
        "takes_ctx": True,
    },
    #    "list_properties": {
    #        "logic": list_properties,
    #        "model": EmptyArgs,
    #        "description": "List all properties in the RDF schema with IRIs and range kinds.",
    #        "takes_ctx": True,
    #    },
    "describe_property": {
        "logic": describe_property,
        "model": DescribePropertyArgs,
        "description": "Describe a property: domain, range, super-properties, and inverses.",
        "takes_ctx": True,
    },
    "run_sparql_query": {
        "logic": run_sparql_query,
        "model": RunSparqlArgs,
        "description": (
            "Validate and run the SPARQL query against the active endpoint and return a small "
            "result/error summary."
        ),
        "takes_ctx": True,
    },
}


def get_tools_spec() -> List[Tool]:
    return [
        Tool(
            function=Function(
                name=name,
                description=info["description"],
                parameters=info["model"].model_json_schema(),
            )
        )
        for name, info in TOOL_REGISTRY.items()
    ]
