from __future__ import annotations

"""
SchemaIndex data model.

This module defines the in-memory representation of an RDF/OWL schema as used by:
  - schema loading (`src.internal.schema_index.load_schema_bytes`)
  - schema context rendering (`src.internal.schema_index.schema_to_context_string`)
  - schema exploration tools (`src.internal.queryGeneration.tools`)

We intentionally do NOT do OWL reasoning here. We only record direct axioms that
appear in the schema, so they can be rendered/inspected by the LLM tooling.
"""

from typing import Dict, List, Literal, Optional, Set

from pydantic import BaseModel, Field


class ClassExpr(BaseModel):
    """
    Minimal OWL class-expression AST (best-effort parsing).

    Supported forms:
      - iri: a named class IRI
      - union: owl:unionOf (RDF list)
      - intersection: owl:intersectionOf (RDF list)
      - complement: owl:complementOf (single argument)
      - oneOf: owl:oneOf (RDF list of individuals)
    """

    kind: Literal["iri", "union", "intersection", "complement", "oneOf"]
    iri: Optional[str] = None  # kind=iri
    items: List[ClassExpr] = Field(default_factory=list)  # union/intersection
    arg: Optional[ClassExpr] = None  # complement


class ClassDef(BaseModel):
    """Definition of an RDF/OWL class extracted from the schema graph."""

    iri: str
    labels: List[str] = Field(default_factory=list)
    comments: List[str] = Field(default_factory=list)

    super_classes: Set[str] = Field(default_factory=set)  # rdfs:subClassOf
    super_class_exprs: List[ClassExpr] = Field(default_factory=list)  # owl expressions
    equivalent_classes: Set[str] = Field(default_factory=set)  # owl:equivalentClass
    equivalent_class_exprs: List[ClassExpr] = Field(default_factory=list)
    disjoint_with: Set[str] = Field(default_factory=set)  # owl:disjointWith
    disjoint_with_exprs: List[ClassExpr] = Field(default_factory=list)
    disjoint_union_of: List[ClassExpr] = Field(
        default_factory=list
    )  # owl:disjointUnionOf
    union_of: List[ClassExpr] = Field(default_factory=list)  # owl:unionOf
    intersection_of: List[ClassExpr] = Field(default_factory=list)  # owl:intersectionOf
    one_of: List[ClassExpr] = Field(default_factory=list)  # owl:oneOf


class PropDef(BaseModel):
    """Definition of an RDF/OWL property extracted from the schema graph."""

    iri: str
    labels: List[str] = Field(default_factory=list)
    comments: List[str] = Field(default_factory=list)

    domains: Set[str] = Field(default_factory=set)  # rdfs:domain
    literal_datatypes: Set[str] = Field(
        default_factory=set
    )  # rdfs:range in XSD namespace
    range_classes: Set[str] = Field(default_factory=set)  # rdfs:range for non XSD IRIs

    super_properties: Set[str] = Field(default_factory=set)  # rdfs:subPropertyOf
    equivalent_properties: Set[str] = Field(
        default_factory=set
    )  # owl:equivalentProperty
    inverses: Set[str] = Field(default_factory=set)  # owl:inverseOf
    property_types: Set[str] = Field(
        default_factory=set
    )  # rdf:type values like owl:ObjectProperty etc


class SchemaIndex(BaseModel):
    """Container for parsed schema artifacts (namespaces, classes, properties)."""

    endpoint: Optional[str] = None
    base_iri: Optional[str] = None
    namespaces: Dict[str, str] = Field(default_factory=dict)  # prefix -> namespace
    classes: Dict[str, ClassDef] = Field(default_factory=dict)  # iri -> def
    props: Dict[str, PropDef] = Field(default_factory=dict)  # iri -> def


# Resolve forward references in ClassExpr (pydantic).
ClassExpr.model_rebuild()
