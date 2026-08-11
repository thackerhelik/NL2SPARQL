# Acceptance Criteria Prioritisation Table

Priotity: Very High, High, Medium, Low
Difficulty: Very High, High, Medium, Low
Status: Not Started, In Progress, Completed

| Number | Title                      | Priority | Difficulty | Status | Owner  | Description |
|--------|----------------------------|----------|------------|--------|--------|-------------|
| AC-1   | Multiple Ollama Models     |          |            |        |        | Support at least two local Ollama models via one adapter |
| AC-2   | Hot Model Switching        |          |            |        |        | Change active model via config or UI with effect under one minute |
| AC-3   | Modular Pipeline           |          |            |        |        | Defined modules for extraction, linking, prompt building, generation, validation, execution |
| AC-4   | Config Driven Architecture |          |            |        |        | Models, endpoint, context pack, and SPARQL subset defined in config; reloadable |
| AC-5   | Context Caching            |          |            |        |        | Cache schema and entity lookups to reduce network calls |
| AC-6   | Load Context Packs         |          |            |        |        | Load prefixes, schema, examples at startup or through admin UI |
| AC-7   | Context Guided Generation  |          |            |        |        | Use context data to prefer classes and properties during generation |
| AC-8   | Choose KG Focus            |          |            |        |        | DBLP or Wikidata setup with a functional SPARQL endpoint |
| AC-9   | Swappable Context          |          |            |        |        | Replace context packs without code changes; show in UI |
| AC-10  | DBLP Core IRIs             |          |            |        |        | Include IRIs for author, publication, venue, year, plus at least ten DBLP examples |
| AC-11  | Linking Feedback Loop      |          |            |        |        | Mechanism to correct wrong entity linking through user interaction |
| AC-12  | Linking Error Detection    |          |            |        |        | Detect and adjust incorrect NEL results or IRIs |
| AC-13  | Auto Approval              |          |            |        |        | Auto approve links above confidence threshold; manual override allowed |
| AC-14  | Linking Logs               |          |            |        |        | Log candidates, scores, and approved choices with final query |
| AC-15  | Valid SPARQL Generation    |          |            |        |        | Generate valid SPARQL for SELECT queries; ASK optional |
| AC-16  | SPARQL Syntax Check        |          |            |        |        | Validate input SPARQL within three seconds; give specific errors |
| AC-17  | Prefix and Schema Check    |          |            |        |        | Ensure prefixes resolve and referenced classes and properties exist |
| AC-18  | Enforce SPARQL Subset      |          |            |        |        | Block disallowed SPARQL features and report violations |
| AC-19  | Execute Queries            |          |            |        |        | Run queries and display results; handle endpoint errors gracefully |
| AC-20  | Web UI                     |          |            |        |        | UI for question input, entity approval, SPARQL preview, model switch, context selection, result table, JSON download |
| AC-21  | Evaluation Set             |          |            |        |        | Provide evaluation set with at least five query types and paraphrases |
| AC-22  | Evaluation Script          |          |            |        |        | Evaluate syntax validity, linking precision, execution success, correctness |
| AC-23  | Full Tracing               |          |            |        |        | Include request ID and trace events for every pipeline step |
| AC-24  | Reproducible Delivery      |          |            |        |        | Include README, architecture, config schema, Docker setup, tests |
