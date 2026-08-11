# Requirements

## Core Functionality

- Modular stages for mention extraction:
    1. Mention Extraction “Who wrote Attention Is All You Need?” -> [“Attention Is All You Need”]
    2. Candidate Generation [“Attention Is All You Need”] -> Search for matching entities in KG
    3. Candidate Ranking [List of candidate entities] -> Rank candidates based on context
    4. User Disambiguation (if needed) - ask user to select from top candidates

- Prompt construction with contex:
  - Examples, schema snippets, approved entities...
  - Create switchable context packs per domain (prefixes, schema, ShEx/SHACL if available, example queries,
templates) (Develop in a way that adding new context packs is easy)

- Static/semantic validation
  - Checkin entities
  - syntax, prefix resolution, existence checks for properties/classes
  - enforce a configurable allowed feature subset (decide on relevant features to ensure reliability)

- Execute SPARQL query

- Display results to user

## Delivery Checklist

- [ ] documented, containerized deployment
- [ ] configuration for models, endpoints, context packs
- [ ] language is group’s choice (Python + RDFLib recommended)
- [ ] minimal web UI (chat, entity approval, SPARQL preview/edit, model/context switch); aesthetics not the focus.
- [ ] tested and documented code

## ✅ Acceptance Criteria

### 🧠 Models and Architecture

- [x] **AC-1** Support at least two Ollama-hosted models (e.g., Llama 3, Mistral/Qwen) behind a single adapter; switching requires no code change.
  - Support models coming from ollama OR RWTHGPT (prefix-GPTmodels with "RWTHGPT-")
- [x] **AC-2** Active model can be changed via config/UI and takes effect on the next generation request (≤1 minute).
- [x] **AC-3** Clear module boundaries for: **mention extraction**, **entity linking**, prompt builder, generator, validator, executor; interfaces documented.
- [x] **AC-4** Configuration files define model(s), endpoint, context pack, and allowed SPARQL subset; reload via restart or hot-reload. Optional over the web interface.
- [x] **AC-5** Caches schema/context and entity lookups to avoid repeated network calls.

### 📚 KG Context and Data

- [x] **AC-6** Loads context data at startup or via admin UI containing prefixes, schema (RDFS/OWL), and at least 10 example queries and/or templates.
- [x] **AC-7** Context data influences generation (properties/classes from the pack are preferred and referenced).
- [x] **AC-8** Choose a KG focus (DBLP with CEUR-WS or Wikidata/Scholia) and provide a working SPARQL endpoint configuration.
- [x] **AC-9** Context data is swappable without code changes and viewable in the UI.
- [x] **AC-10** If DBLP is chosen: the pack includes IRIs for core scholarly concepts (author, publication, venue/workshop, year) and at least 10 DBLP-specific example queries.

### 🔗 Entity Linking Assurance Loop

- [x] **AC-11** Devise a feedback loop to fix possible errors in IRI entity linking.
  - you can choose another candidate
  - we can give a hint to re write the query if the results are poor
- [ ] **AC-12** Implement strategies for detection and adjustment of incorrect NEL results or used IRIs in the queries.
- [x] **AC-13** Auto-approval can be applied when a confidence/score threshold is met; users can override any auto choice.
- [x] **AC-14** All linking decisions (candidates, scores, approvals) are logged alongside the final query.

### 🧪 SPARQL Generation, Validation, and Safety

- [x] **AC-15** Generates syntactically valid SPARQL for at least SELECT queries; ASK optional.
- [x] **AC-16** Given a SPARQL query (text or .rq), returns “Valid SPARQL query” or a specific error within 3 seconds.
- [ ] **AC-17** Validates that prefixes resolve and that properties/classes in the query exist (via schema/context or endpoint introspection); reports actionable errors.
- [x] **AC-18** Enforces a configurable allowed SPARQL subset (forbidden features list decided in phase one); blocked features are reported to the user.
- [x] **AC-19** Executes queries against the configured endpoint and displays results; execution errors are caught and shown with guidance.

### 🖥️ UI, Evaluation, and Delivery

- [x] **AC-20** Web UI supports: question input, entity approval, SPARQL preview/edit, model switch, and context selection; results shown in a table with downloadable JSON.
- [ ] **AC-21** Define an evaluation set in phase one with ≥5 distinct query types, each with multiple paraphrases; include expected answers (query or result pattern).
- [ ] **AC-22** Provide an evaluation script reporting at least: syntax validity rate, entity linking precision, execution success rate, and answer correctness.
- [x] **AC-23** Logging/tracing includes a request/trace ID and records each pipeline step.
  - Optional send trace id in all calls to BE and add to logs for better traceability
- [ ] **AC-24** Reproducible delivery includes: README, architecture diagram, config schema, and Docker setup.

## Additional Resources

- Mention Extraction - [spaCy: Industrial-Strength Natural Language Processing](https://spacy.io/)

- [DBLPLink 2.0 - An Entity Linker for the DBLP Scholarly Knowledge Graph](https://arxiv.org/pdf/2507.22811)
- [Sorry, I don't speak SPARQL: translating SPARQL queries into natural language](https://doi.org/10.1145/2488388.2488473)
- [First International TEXT2SPARQL Challenge](https://text2sparql.aksw.org/program/)
- ASK-DBLP: Answering Questions over DBLP
    ASK-DBLP enables users to ask questions in natural language and
    automatically converts them into SPARQL queries to provide precise
    answers. The platform is designed to be robust and user-friendly, allowing
    refinement of ambiguous queries and selection or updating of entity links
    within the SPARQL query. This approach makes ASK-DBLP adaptable to the
    latest DBLP schema updates.

    Try the [demo](https://ask-dblp.nliwod.org)
- [DBLPLink 2.0 – An Entity Linker for the DBLP Scholarly Knowledge Graph](https://arxiv.org/abs/2507.22811)
    DBLPLink 2.0 introduces a novel zero-shot entity linking approach using
    LLMs. Candidate entities are re-ranked based on the log-probabilities of the
    'yes' token in the LLM's penultimate layer, resulting in more accurate and
    adaptive entity linking for the DBLP Knowledge Graph.

    Try the [demo](https://dblplink-2.skynet.coypu.org/)
- [SPARQL 1.1 Query Language](https://www.w3.org/TR/sparql11-query/)
- [RDF 1.1 Concepts](https://www.w3.org/TR/rdf11-concepts/)
