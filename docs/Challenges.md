# Entity Linking Challenges

## High priority

### Missing instance labels / label predicate not in schema

Some graphs use `rdfs:label` (or other label predicates) on instance data, but the schema/context pack doesn’t reliably declare which predicate(s) to treat as labels. This makes it hard to pick the “best” candidate URI when labels aren’t available in the schema layer.

Related: This seems common for KG where "classes" are likely to have labels but there are no "instances" (Dogs -> named dogs vs Different Pokemon species)

**Potential solutions**:

- Add a per-schema `label_predicates` config (ordered list) and use it during candidate enrichment.
- Add a fallback discovery step that samples the KG for common label predicates used on candidate IRIs.
- Store “best label predicate” per class/property when building the context pack (when discoverable).

### Reranker is too weak / not calibrated

The current reranker is basic, so it likely fails on ambiguous mentions (names, titles, short strings) and near-duplicates. Poor reranking dominates end-to-end EL quality even if candidate generation is decent.

**Potential solutions**:

- Upgrade to a cross-encoder reranker (or lightweight LLM scoring) for top-k candidates.
- Add feature-based scoring (type match, property match, popularity, exact/normalized match) with learned weights.
- Calibrate scores and expose confidence so downstream steps can trigger a confirmation loop when uncertain.

**Status**:

- First we need to assess the current performance!

### No EL confirmation/repair loop

After producing candidate URIs, we don’t have an LLM or user-facing confirmation step to catch and correct wrong links. This makes failures silent and cascades errors into query generation.

**Potential solutions**:

- Add an LLM confirmation step for low-confidence links (or for top ambiguous mentions only) that leverages the OTHER extracted mentions and IRIS.
- Convert the EL step into llm loop with tool calls to allow llm to iteratively refine candidates. Perhapas:
  - We make a first pass to generate candidates and scores.
  - We pass the results to the llm with tools to allow it to fetch additional context and refine the linked entity results.
  - Either choose the right candidate (boost score +1000k e.g.) or adjust the candidate list (different query.)

### Exact match search is too strict

When user input includes abbreviations like E. in person names we often fail to retrieve the correct candidate or fail all together
Examples : "E. W. Dijkstra" should match "Serviere, C." -> "Christine Serviere"

**Potential solutions**:

- If we dont get any candidates (or detect punctuation?) split on space, and try longest match or use different query pattern.
- Could be combined with an LLM repair loop

### No explicit clarification/fallback when matching confidence is low

Right now the system does not have a clear mechanism to tell the user that we likely did not find the correct entity and ask for clarification. This causes silent failures when linking confidence is low or candidate retrieval fails.

**Potential solutions**:

- Trigger clarification when no candidates are found for a mention.
- Trigger clarification when top candidate score is below a confidence threshold (or score gap is too small).

## Medium priority

### No gold dataset for DBLP / other KGs

We don’t have a reliable evaluation set with expected URIs and clear metrics (mention detection, linking precision@k, end-to-end success). Without this, improvements are hard to validate and compare.

**Potential solutions**:

- Build a small curated gold set per KG/domain (hand-labeled or semi-assisted) and freeze it in-repo.
- Report metrics per stage (mention extraction F1, precision@k for linking, end-to-end query success proxy).
- Add regression tests around known tricky ambiguities and schema edge cases.

**Status**:

- Script to evaluat on DBLP Quad
- Script to get some 50% of the venue entities matched BUT all are in non SELECT queries...
- TODO: add some curated examples that include dblp:Stream

### OWL Restrictions not translated into practical constraints

Even when restrictions exist, we don’t currently turn them into “usable hints” like “instances of Class C typically have property P with range T.” This leaves potential signal on the floor for both candidate generation and reranking.

**Potential solutions**:

- Convert restrictions into soft constraints (“expected properties”) used during candidate enrichment/reranking.
- Use restriction-derived constraints to penalize candidates that violate obvious type/property expectations.
- Cache computed constraints per schema and include a compact form in the context pack.

### Schema/context too large for model context window

Large schemas can’t be fully printed into prompts, so naive “dump the schema” approaches won’t scale. We need context selection (task-aware filtering) or retrieval-based schema packs.

**Potential solutions**:

- Introduce schema retrieval: rank relevant classes/properties per query and print only top-N.
- Use tool-calling to fetch schema slices on demand (iterative context expansion).
- Maintain precomputed “views” (root nodes + neighborhood) per schema and choose based on mention types.

### Weak context selection for schema subsets

We don’t yet have a robust method to pick only the relevant classes/properties for a given query and mention type. This leads to either missing needed context or wasting tokens on irrelevant parts.

**Potential solutions**:

- Add a deterministic selector: start from root nodes, expand via property graph, stop by token budget.
- Add embedding/BM25 retrieval over schema docs (labels/comments) to select likely relevant predicates/classes.
- Add a small LLM “schema router” step that chooses which schema slice to request via tools.

### Properties without usable range information

Some schemas don’t provide `rdfs:range` (or provide ranges that aren’t helpful for linking), so we can’t reliably type-check candidate values or know whether a mention should map to a literal vs an IRI. This reduces candidate quality and makes reranking brittle.

**Potential solutions**:

- Infer “effective range” heuristically from observed instance triples (sampled data-driven typing).
- Treat range as a soft signal (not a hard constraint) and fall back to lexical/semantic scoring when missing.
- Add per-schema overrides for important predicates (range kind: literal vs IRI, expected class).

## Low priority

## One hop context retrieval

Check if we should ignore contex that has equal labels. To gain visibility and be efficient.

## Handled

### Type inheritance not applied during `label_pred` validation

Mention extraction can choose a reasonable `label_pred` (e.g., `dblp:creatorName`) but get dropped if the validator only checks predicates declared directly on the predicted type (e.g., `dblp:Person`) rather than inherited from superclasses (e.g., `dblp:Creator`). This creates “silent” failures where the model responds correctly but we return zero mentions.

**Potential solutions**:

- When validating `label_pred`, allow predicates from the type’s superclass chain (transitive `subClassOf`) and/or equivalent classes.
- As a fallback, if `label_pred` is valid for a superclass or subclass, auto-cast the mention type to that class instead of dropping the mention.
- Precompute and store “effective predicates for type” (closure over domains + inheritance) in the `SchemaIndex` for fast validation. (Overkill for now)
