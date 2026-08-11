import re
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import unquote

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD

from src.schemas.schema_index import ClassDef, ClassExpr, PropDef, SchemaIndex


def load_schema_bytes(
    data: bytes,
    *,
    base_iri: Optional[str] = None,
    rdf_format: Optional[str] = None,
) -> SchemaIndex:
    """
    Parse schema bytes into a `SchemaIndex`.

    What we extract:
      - Namespaces/prefixes as provided by the RDF parser (plus rdf/rdfs/owl/xsd defaults)
      - Classes: labels/comments, and *direct* OWL class axioms (subClassOf/equivalent/disjoint*)
      - Properties: labels/comments, rdf:type, domain/range, subPropertyOf, equivalentProperty, inverseOf

    Notes:
      - We intentionally do not infer domains/ranges from OWL Restrictions yet.
      - OWL class expressions are parsed only for union/intersection/complement constructs.
    """

    g = Graph()
    parse_kwargs = {"publicID": base_iri} if base_iri else {}

    tried: list[str] = []
    if rdf_format is not None:
        tried.append(rdf_format)
        g.parse(data=data, format=rdf_format, **parse_kwargs)
    else:
        for fmt in [None, "xml", "turtle", "n3", "nt", "json-ld", "trig"]:
            try:
                tried.append("auto" if fmt is None else fmt)
                g.parse(data=data, format=fmt, **parse_kwargs)
                break
            except Exception:
                if fmt == "trig":
                    raise ValueError(
                        f"Could not parse schema bytes (tried: {', '.join(tried)})"
                    ) from None

    ns: Dict[str, str] = {pfx: str(uri) for pfx, uri in g.namespaces()}
    ns = _ensure_default_prefixes(ns)
    idx = SchemaIndex(namespaces=ns)
    if base_iri is not None and isinstance(base_iri, str):
        idx.base_iri = base_iri

    # -------- classes --------
    # We include both owl:Class and rdfs:Class.
    class_nodes: Set[URIRef] = set()
    for s in g.subjects(RDF.type, OWL.Class):
        if isinstance(s, URIRef):
            class_nodes.add(s)
    for s in g.subjects(RDF.type, RDFS.Class):
        if isinstance(s, URIRef):
            class_nodes.add(s)

    for c in class_nodes:
        iri = str(c)
        cd = idx.classes.get(iri) or ClassDef(iri=iri)

        cd.labels = _collect_literals(g, c, RDFS.label)
        cd.comments = _collect_literals(g, c, RDFS.comment)

        # OWL/RDFS class relations can point to:
        #  - a named class IRI, OR
        #  - a blank node describing a class expression (unionOf/intersectionOf/complementOf)
        for o in g.objects(c, RDFS.subClassOf):
            if isinstance(o, URIRef):
                cd.super_classes.add(str(o))
            else:
                expr = _parse_class_expr(g, o)
                if expr is not None:
                    _dedupe_append_expr(cd.super_class_exprs, expr)

        for o in g.objects(c, OWL.equivalentClass):
            if isinstance(o, URIRef):
                cd.equivalent_classes.add(str(o))
            else:
                expr = _parse_class_expr(g, o)
                if expr is not None:
                    _dedupe_append_expr(cd.equivalent_class_exprs, expr)

        for o in g.objects(c, OWL.disjointWith):
            if isinstance(o, URIRef):
                cd.disjoint_with.add(str(o))
            else:
                expr = _parse_class_expr(g, o)
                if expr is not None:
                    _dedupe_append_expr(cd.disjoint_with_exprs, expr)

        for o in g.objects(c, OWL.disjointUnionOf):
            # owl:disjointUnionOf is typically an RDF list of classes/class expressions
            if isinstance(o, BNode | URIRef):
                for item in _parse_rdf_list(g, o):
                    expr = _parse_class_expr(g, item)
                    if expr is not None:
                        _dedupe_append_expr(cd.disjoint_union_of, expr)

        for o in g.objects(c, OWL.unionOf):
            if isinstance(o, BNode | URIRef):
                for item in _parse_rdf_list(g, o):
                    expr = _parse_class_expr(g, item)
                    if expr is not None:
                        _dedupe_append_expr(cd.union_of, expr)

        for o in g.objects(c, OWL.intersectionOf):
            if isinstance(o, BNode | URIRef):
                for item in _parse_rdf_list(g, o):
                    expr = _parse_class_expr(g, item)
                    if expr is not None:
                        _dedupe_append_expr(cd.intersection_of, expr)

        for o in g.objects(c, OWL.oneOf):
            if isinstance(o, BNode | URIRef):
                for item in _parse_rdf_list(g, o):
                    # individuals stored as kind="iri" expressions
                    if isinstance(item, URIRef):
                        _dedupe_append_expr(
                            cd.one_of, ClassExpr(kind="iri", iri=str(item))
                        )

        idx.classes[iri] = cd

    # -------- properties --------
    # We include:
    #  - any subject explicitly typed as a known RDF/OWL property class, AND
    #  - any predicate used anywhere in the schema graph (best-effort discovery)
    prop_nodes: Set[URIRef] = set()

    property_type_iris = {
        RDF.Property,
        OWL.ObjectProperty,
        OWL.DatatypeProperty,
        OWL.AnnotationProperty,
        OWL.OntologyProperty,
        OWL.FunctionalProperty,
        OWL.InverseFunctionalProperty,
        OWL.SymmetricProperty,
        OWL.TransitiveProperty,
    }
    for t in property_type_iris:
        for s in g.subjects(RDF.type, t):
            if isinstance(s, URIRef):
                prop_nodes.add(s)

    for p in set(g.predicates()):
        if isinstance(p, URIRef):
            prop_nodes.add(p)

    for p in prop_nodes:
        iri = str(p)
        pd = idx.props.get(iri) or PropDef(iri=iri)

        pd.labels = _collect_literals(g, p, RDFS.label)
        pd.comments = _collect_literals(g, p, RDFS.comment)

        for t in g.objects(p, RDF.type):
            if isinstance(t, URIRef):
                pd.property_types.add(str(t))

        pd.domains |= {
            str(o) for o in g.objects(p, RDFS.domain) if isinstance(o, URIRef)
        }

        for o in g.objects(p, RDFS.range):
            if not isinstance(o, URIRef):
                continue
            o_str = str(o)
            if o_str.startswith(str(XSD)):
                pd.literal_datatypes.add(o_str)
            else:
                pd.range_classes.add(o_str)

        pd.super_properties |= {
            str(o) for o in g.objects(p, RDFS.subPropertyOf) if isinstance(o, URIRef)
        }
        pd.equivalent_properties |= {
            str(o)
            for o in g.objects(p, OWL.equivalentProperty)
            if isinstance(o, URIRef)
        }

        for o in g.objects(p, OWL.inverseOf):
            if isinstance(o, URIRef):
                pd.inverses.add(str(o))

        idx.props[iri] = pd

    for piri, pd in list(idx.props.items()):
        for inv in list(pd.inverses):
            inv_pd = idx.props.get(inv)
            if inv_pd is None:
                inv_pd = PropDef(iri=inv)
                idx.props[inv] = inv_pd
            inv_pd.inverses.add(piri)

    return idx


def _ensure_default_prefixes(namespaces: Dict[str, str]) -> Dict[str, str]:
    defaults = {"rdf": str(RDF), "rdfs": str(RDFS), "owl": str(OWL), "xsd": str(XSD)}
    out = dict(namespaces)
    for k, v in defaults.items():
        out.setdefault(k, v)
    return out


def make_curie(iri: str, namespaces: Dict[str, str]) -> str:
    iri_u = unquote(iri)
    best: Optional[Tuple[str, str]] = None
    best_len = -1
    for pfx, ns in namespaces.items():
        ns_u = unquote(ns)
        if iri_u.startswith(ns_u) and len(ns_u) > best_len:
            best = (pfx, ns_u)
            best_len = len(ns_u)
    if best is None:
        return iri
    pfx, ns_u = best
    return f"{pfx}:{iri_u[best_len:]}"


def _collect_literals(g: Graph, s: URIRef, p: URIRef) -> List[str]:
    out: List[str] = []
    for o in g.objects(s, p):
        if isinstance(o, Literal):
            val = str(o).strip()
            if val and val not in out:
                out.append(val)
    return out


def _parse_rdf_list(g: Graph, head: URIRef | BNode) -> List[URIRef | BNode]:
    """Parse an RDF list head into items. Returns [] on malformed lists."""
    try:
        return [i for i in Collection(g, head) if isinstance(i, URIRef | BNode)]
    except Exception:
        return []


def _dedupe_append_expr(dst: List[ClassExpr], expr: ClassExpr) -> None:
    """Append a class expression if an identical one is not already present."""
    key = expr.model_dump()
    for existing in dst:
        if existing.model_dump() == key:
            return
    dst.append(expr)


def _parse_class_expr(
    g: Graph,
    node: URIRef | BNode,
    *,
    _seen: Optional[Set[str]] = None,
) -> Optional[ClassExpr]:
    """
    Parse a node as a minimal OWL class expression.

    Supported:
      - Named IRI (treated as kind="iri")
      - Blank node expressions:
          * owl:unionOf (RDF list)
          * owl:intersectionOf (RDF list)
          * owl:complementOf (single target)

    Anything else returns None.
    """
    if isinstance(node, URIRef):
        return ClassExpr(kind="iri", iri=str(node))

    if not isinstance(node, BNode):
        return None

    if _seen is None:
        _seen = set()
    nid = str(node)
    if nid in _seen:
        return None
    _seen.add(nid)

    # owl:unionOf / owl:intersectionOf are RDF lists
    for pred, kind in (
        (OWL.unionOf, "union"),
        (OWL.intersectionOf, "intersection"),
        (OWL.oneOf, "oneOf"),
    ):
        for lst in g.objects(node, pred):
            if isinstance(lst, BNode | URIRef):
                items: List[ClassExpr] = []
                for item in _parse_rdf_list(g, lst):
                    if kind == "oneOf":
                        if isinstance(item, URIRef):
                            items.append(ClassExpr(kind="iri", iri=str(item)))
                    else:
                        sub = _parse_class_expr(g, item, _seen=_seen)
                        if sub is not None:
                            items.append(sub)
                if items:
                    return ClassExpr(kind=kind, items=items)

    # owl:complementOf points to a single class expression
    for target in g.objects(node, OWL.complementOf):
        if isinstance(target, BNode | URIRef):
            sub = _parse_class_expr(g, target, _seen=_seen)
            if sub is not None:
                return ClassExpr(kind="complement", arg=sub)

    # Fallback: treat as unknown bnode expression (ignore)
    return None


# Filter


def filter_schema(
    idx: SchemaIndex,
    *,
    keep_only_literal_or_labelable_object: bool = False,
    include_predicates: bool = True,
    keep_only_classes_with_predicates: bool = False,
) -> SchemaIndex:
    if not include_predicates:
        return SchemaIndex(
            namespaces=dict(idx.namespaces),
            classes=dict(idx.classes),
            props={},
        )

    # domain(class IRI) -> list[PropDef] (from original idx)
    domain_to_props: Dict[str, list] = {}
    for p in idx.props.values():
        for d in getattr(p, "domains", set()) or set():
            domain_to_props.setdefault(d, []).append(p)

    def class_is_labelable(class_iri: str) -> bool:
        for p2 in domain_to_props.get(class_iri, []):
            for dt in getattr(p2, "literal_datatypes", set()) or set():
                if _is_xsd(dt) and _xsd_local(dt).lower() == "string":
                    return True
        return False

    new_props: Dict[str, PropDef] = {}

    for p in idx.props.values():
        domains = getattr(p, "domains", set()) or set()
        if not domains:
            continue

        lit_dts = getattr(p, "literal_datatypes", set()) or set()
        rng_cls = getattr(p, "range_classes", set()) or set()

        has_lit = bool(lit_dts)
        has_obj = bool(rng_cls)

        if not has_lit and not has_obj:
            continue

        if keep_only_literal_or_labelable_object:
            if has_lit:
                keep = True
            else:
                keep = any(class_is_labelable(t) for t in rng_cls)
            if not keep:
                continue

        new_props[p.iri] = PropDef(
            iri=p.iri,
            labels=list(getattr(p, "labels", []) or []),
            comments=list(getattr(p, "comments", []) or []),
            domains=set(domains),
            literal_datatypes=set(lit_dts),
            range_classes=set(rng_cls),
        )

    # Filter classes if requested
    new_classes = dict(idx.classes)
    if keep_only_classes_with_predicates:
        # Collect all classes that appear as domains in the filtered properties
        classes_with_preds = set()
        for p in new_props.values():
            classes_with_preds.update(getattr(p, "domains", set()) or set())

        # Keep only those classes
        new_classes = {
            iri: cls_def
            for iri, cls_def in idx.classes.items()
            if iri in classes_with_preds
        }

    return SchemaIndex(
        namespaces=dict(idx.namespaces),
        classes=new_classes,
        props=new_props,
    )


def _is_xsd(dt_iri: str) -> bool:
    return dt_iri.startswith("http://www.w3.org/2001/XMLSchema#")


def _xsd_local(dt_iri: str) -> str:
    # http://www.w3.org/2001/XMLSchema#string -> string
    if "#" in dt_iri:
        return dt_iri.rsplit("#", 1)[-1]
    return dt_iri.rsplit("/", 1)[-1]


# Compact context renderer


def schema_to_context_string(
    idx: SchemaIndex,
    *,
    include_prefixes: bool = True,
    max_types: Optional[int] = None,
    max_preds_per_type: Optional[int] = None,
    include_notes: bool = True,
    include_predicates: bool = True,
    include_type_header: bool = True,
    include_pred_header: bool = True,
    include_class_relations: bool = True,
    include_superclasses: bool = True,
    include_equivalents: bool = True,
    include_disjoints: bool = True,
    include_disjoint_unions: bool = True,
    include_unions: bool = True,
    include_intersections: bool = True,
    include_one_of: bool = True,
    include_owl_expressions: bool = True,
    max_rel_items: Optional[int] = None,
) -> str:
    """
    Render a compact, LLM-friendly schema summary.

    The output format is intentionally regular:
      - Each Type row is `type_curie | label | optional comments`
      - Each Predicate row is `pred_curie | label | rng:...`
      - OWL class relations (subClassOf/equiv/disjoint*) are printed as extra lines
        under the type and must not be confused with predicate rows.
    """
    lines: List[str] = []

    if include_prefixes:
        lines.append("PREFIXES")
        for pfx, ns in sorted(idx.namespaces.items()):
            lines.append(f"{pfx}: <{ns}>")
        lines.append("")

    lines.append("SCHEMA")
    lines.append(
        "Legend: type | label | opt(note) ; pred | label | rng: lit(xsd:*) or iri(Type)"
    )
    if include_class_relations:
        legend2 = "Legend2: subClassOf/equiv/disjointWith/disjointUnionOf: CURIEs and owl:* expressions"
        lines.append(legend2)
    lines.append("")

    # domain -> predicates
    domain_to_preds: Dict[str, List[PropDef]] = {}
    if include_predicates:
        for p in idx.props.values():
            for d in p.domains:
                domain_to_preds.setdefault(d, []).append(p)

    # sorted types
    types = sorted(
        idx.classes.values(), key=lambda c: make_curie(c.iri, idx.namespaces)
    )
    if max_types is not None:
        types = types[:max_types]

    if include_type_header:
        lines.append("Types:")

    for c in types:
        c_id = make_curie(c.iri, idx.namespaces)
        c_label = c.labels[0] if c.labels else c_id.split(":")[-1]
        line = f"{c_id} | {c_label} | "
        if include_notes and c.comments:
            line += f"{';'.join(c.comments)}"
        lines.append(line)

        if include_class_relations:
            if include_superclasses:
                sups = getattr(c, "super_classes", set()) or set()
                sup_exprs = (
                    getattr(c, "super_class_exprs", [])
                    if include_owl_expressions
                    else []
                )
                if sups:
                    lines.append(
                        f"  subClassOf: {_fmt_curie_list(sups, idx.namespaces, max_items=max_rel_items)}"
                    )
                if sup_exprs:
                    lines.append(
                        f"  subClassOf: {_fmt_expr_list(sup_exprs, idx.namespaces, max_items=max_rel_items)}"
                    )

            if include_equivalents:
                eqs = getattr(c, "equivalent_classes", set()) or set()
                eq_exprs = (
                    getattr(c, "equivalent_class_exprs", [])
                    if include_owl_expressions
                    else []
                )
                if eqs:
                    lines.append(
                        f"  equiv: {_fmt_curie_list(eqs, idx.namespaces, max_items=max_rel_items)}"
                    )
                if eq_exprs:
                    lines.append(
                        f"  equiv: {_fmt_expr_list(eq_exprs, idx.namespaces, max_items=max_rel_items)}"
                    )

            if include_disjoints:
                dis = getattr(c, "disjoint_with", set()) or set()
                dis_exprs = (
                    getattr(c, "disjoint_with_exprs", [])
                    if include_owl_expressions
                    else []
                )
                if dis:
                    lines.append(
                        f"  disjointWith: {_fmt_curie_list(dis, idx.namespaces, max_items=max_rel_items)}"
                    )
                if dis_exprs:
                    lines.append(
                        f"  disjointWith: {_fmt_expr_list(dis_exprs, idx.namespaces, max_items=max_rel_items)}"
                    )

            if include_disjoint_unions:
                du = getattr(c, "disjoint_union_of", []) or []
                if du and include_owl_expressions:
                    lines.append(
                        f"  disjointUnionOf: {_fmt_expr_list(du, idx.namespaces, max_items=max_rel_items)}"
                    )

            if include_unions:
                unions = getattr(c, "union_of", []) or []
                if unions and include_owl_expressions:
                    lines.append(
                        f"  unionOf: {_fmt_expr_list(unions, idx.namespaces, max_items=max_rel_items)}"
                    )

            if include_intersections:
                inters = getattr(c, "intersection_of", []) or []
                if inters and include_owl_expressions:
                    lines.append(
                        f"  intersectionOf: {_fmt_expr_list(inters, idx.namespaces, max_items=max_rel_items)}"
                    )

            if include_one_of:
                ones = getattr(c, "one_of", []) or []
                if ones and include_owl_expressions:
                    lines.append(
                        f"  oneOf: {_fmt_expr_list(ones, idx.namespaces, max_items=max_rel_items)}"
                    )

        preds: List[PropDef] = []
        if include_predicates:
            preds = domain_to_preds.get(c.iri, [])
            preds.sort(key=lambda p: make_curie(p.iri, idx.namespaces))
            if max_preds_per_type is not None:
                preds = preds[:max_preds_per_type]

        if preds:
            if include_pred_header:
                lines.append("  Predicates:")
            for p in preds:
                p_id = make_curie(p.iri, idx.namespaces)
                p_label = p.labels[0] if p.labels else p_id.split(":")[-1]
                rng = _range_compact(p, idx.namespaces)
                line = f"    {p_id} | {p_label} | rng:{rng}"
                if include_notes and p.comments:
                    line += f" | {'; '.join(p.comments)}"
                lines.append(line)

        lines.append("")

    return "\n".join(lines).rstrip()


def _range_compact(p: PropDef, namespaces: Dict[str, str]) -> str:
    if p.literal_datatypes:
        dts = sorted(make_curie(dt, namespaces) for dt in p.literal_datatypes)
        return f"lit({','.join(dts)})"
    if p.range_classes:
        cs = sorted(make_curie(c, namespaces) for c in p.range_classes)
        return f"iri({'|'.join(cs)})"
    return "unk"


def _fmt_curie_list(
    iris: Iterable[str], namespaces: Dict[str, str], *, max_items: Optional[int] = None
) -> str:
    items = [make_curie(i, namespaces) for i in iris]
    items = sorted(dict.fromkeys(items))  # stable dedupe
    if max_items is not None:
        items = items[:max_items]
    return ", ".join(items)


def _fmt_expr_list(
    exprs: Iterable[ClassExpr],
    namespaces: Dict[str, str],
    *,
    max_items: Optional[int] = None,
) -> str:
    items = [_expr_compact(e, namespaces) for e in exprs]
    items = [i for i in items if i]
    items = sorted(dict.fromkeys(items))
    if max_items is not None:
        items = items[:max_items]
    return ", ".join(items)


def _expr_compact(
    expr: ClassExpr, namespaces: Dict[str, str], *, _depth: int = 0
) -> str:
    """Compact, one-line representation used for printing and tool output."""
    if _depth > 6:
        return "..."
    k = expr.kind
    if k == "iri":
        return make_curie(expr.iri or "", namespaces)
    if k in ("union", "intersection"):
        parts = [_expr_compact(i, namespaces, _depth=_depth + 1) for i in expr.items]
        parts = [p for p in parts if p]
        inner = "|".join(parts)
        return f"{k}Of({inner})" if inner else ""
    if k == "oneOf":
        parts = [_expr_compact(i, namespaces, _depth=_depth + 1) for i in expr.items]
        parts = [p for p in parts if p]
        inner = "|".join(parts)
        return f"oneOf({inner})" if inner else ""
    if k == "complement":
        inner = (
            _expr_compact(expr.arg, namespaces, _depth=_depth + 1) if expr.arg else ""
        )
        return f"complementOf({inner})" if inner else ""
    return ""


def expr_to_compact_string(expr: ClassExpr, namespaces: Dict[str, str]) -> str:
    """Public helper for turning a `ClassExpr` into a compact string."""
    return _expr_compact(expr, namespaces)


# Helpers


def curie_to_iri(term: str, namespaces: Dict[str, str]) -> str:
    if term.startswith("<") and term.endswith(">"):
        return term[1:-1]
    if "://" in term:
        return term
    if ":" not in term:
        return term
    pfx, suf = term.split(":", 1)
    ns = namespaces.get(pfx)
    return (ns + suf) if ns else term


def _get_ancestors(idx: SchemaIndex, start_node: str) -> Set[str]:
    """
    Return all ancestors (transitive superclasses and equivalent classes) of start_node.
    Includes start_node itself.
    """
    ancestors = {start_node}
    stack = [start_node]

    while stack:
        curr = stack.pop()

        if curr not in idx.classes:
            continue

        cd = idx.classes[curr]
        # Check both super classes and equivalent classes
        candidates = cd.super_classes | cd.equivalent_classes

        for parent in candidates:
            if parent not in ancestors:
                ancestors.add(parent)
                stack.append(parent)

    return ancestors


def _choose_best_by_ancestor_distance(
    *,
    start: str,
    candidates: Set[str],
    idx: SchemaIndex,
) -> Optional[str]:
    """
    Choose the closest candidate to `start` walking up the class hierarchy.

    Distance is measured over (superClassOf ∪ equivalentClass) edges, using the
    same relations as `_get_ancestors`. Returns None if no candidate is reachable.
    """
    if not candidates:
        return None
    if start in candidates:
        return start

    # BFS to compute minimal ancestor distance.
    seen = {start}
    frontier = [start]
    while frontier:
        curr = frontier.pop(0)
        if curr not in idx.classes:
            continue
        cd = idx.classes[curr]
        parents = cd.super_classes | cd.equivalent_classes
        for p in parents:
            if p in seen:
                continue
            if p in candidates:
                return p
            seen.add(p)
            frontier.append(p)
    return None


def is_string_label_pred(
    idx: SchemaIndex, type_curie: str, pred_curie: str
) -> Tuple[bool, Optional[str]]:
    """
    Check whether `pred_curie` can be used as a string label predicate for `type_curie`.

    Returns `(ok, resolved_type_iri)` where `resolved_type_iri` may differ from the
    requested type when the predicate domain implies an upcast/narrowing.
    """
    t_iri = curie_to_iri(type_curie, idx.namespaces)
    p_iri = curie_to_iri(pred_curie, idx.namespaces)

    if t_iri not in idx.classes:
        return False, None
    if p_iri not in idx.props:
        return False, None

    pd = idx.props[p_iri]
    domains = pd.domains or set()
    if not domains:
        return False, None

    if not pd.literal_datatypes or not any(
        _is_xsd(dt) and _xsd_local(dt).lower() == "string"
        for dt in pd.literal_datatypes
    ):
        return False, None

    # 1) Exact match: predicate domain includes the requested type.
    if t_iri in domains:
        return True, t_iri

    # 2) Upcast: predicate domain matches a superclass of the requested type.
    ancestors = _get_ancestors(idx, t_iri)
    match_anc = _choose_best_by_ancestor_distance(
        start=t_iri, candidates=ancestors & domains, idx=idx
    )
    if match_anc is not None:
        # Use the closest ancestor domain as the effective class for candidate queries.
        return True, match_anc

    # 3) Narrowing: predicate domain is a subclass of the requested type.
    sub_candidates = {d for d in domains if t_iri in _get_ancestors(idx, d)}
    if sub_candidates:
        # Pick a deterministic "closest" subclass by preferring direct subclasses first.
        chosen = sorted(sub_candidates)[0]
        return True, chosen

    return False, None


def render_prefixes(ctx, used_prefixes: Optional[Iterable[str]] = None) -> str:
    """
    Render PREFIX declarations from ctx.namespaces
    ctx.namespaces: Dict[str, str]  (prefix -> IRI)
    """
    items = ctx.namespaces.items()
    if used_prefixes is not None:
        used = set(used_prefixes)
        items = [(p, iri) for p, iri in items if p in used]
    return "\n".join(f"PREFIX {p}: <{iri}>" for p, iri in items)


PREFIX_RE = re.compile(r"\b([A-Za-z_][\w\-]*):")
DEFAULT_PREFIX_RE = re.compile(r"(^|[^\w\-]):[A-Za-z_][\w\-]*")


def render_prefixes_for_query(ctx, query: str) -> str:
    used = set()
    for match in PREFIX_RE.finditer(query):
        pfx = match.group(1)
        if pfx in ctx.namespaces:
            used.add(pfx)
    if "" in ctx.namespaces and DEFAULT_PREFIX_RE.search(query):
        used.add("")
    return render_prefixes(ctx, used_prefixes=used)
