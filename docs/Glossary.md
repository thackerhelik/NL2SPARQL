# Glossary

The goal of this is glossary is to provide definitions for key terms and concepts used throughout the project documentation. This will help ensure that all team members and stakeholders have a common understanding of important terminology.

## Terms and Definitions

- **NEL**: Named Entity Linking, the task of identifying and linking named entities in text to their corresponding entries in a knowledge base.
- **Entity linking loop**: Iteratively detecting, proposing, and confirming entity links between a user’s question and the knowledge graph, before generating the final SPARQL query.
- **Knowledge graph**: A structured representation of knowledge that captures entities, their attributes, and the relationships between them. Knowledge is represented as triples, consisting of a subject, predicate, and object.
- **SPARQL**: A query language used to retrieve and manipulate data stored in a knowledge graph or RDF (Resource Description Framework) format.
- **RDFS / OWL**: RDF Schema (RDFS) and Web Ontology Language (OWL) describe the vocabulary and structure of the knowledge graph.
- **ShEx / SHACL**: Shape Expressions (ShEx) and Shapes Constraint Language (SHACL) are used to define and validate the structure and constraints of data in the knowledge graph.
- **IRI**: Internationalized Resource Identifier, a unique identifier used to identify resources in the knowledge graph.
- **Prefixes**: Shortened forms of IRIs used in SPARQL queries to improve readability and reduce verbosity.


## Domain-Specific Knowledge Graphs

- **DBLP**: A computer science bibliography dataset providing structured metadata on research papers, authors, and venues through a public SPARQL endpoint. It offers a clean and predictable schema, making it easy to query and build against, but has limited domain coverage and sparse metadata compared to Wikidata.

- **CEUR-WS**: An open-access collection of workshop proceedings that extends DBLP with more granular information about workshops and sessions. It enriches academic context but introduces additional complexity and less consistent linking quality.

- **Wikidata**: A large, community-maintained knowledge graph covering all domains, including scholarly works. It provides rich metadata, multilingual labels, and stable APIs with integrated search through Elasticsearch. Its scale and openness make it powerful but also harder to link entities reliably and more prone to query timeouts and inconsistent data quality.

- **Scholia**: A service built on top of Wikidata that provides scholarly profiles, timelines, and analytics through pre-built SPARQL queries. It accelerates development by offering ready-to-use patterns but depends entirely on the completeness and quality of Wikidata’s data.

## Comparison of Knowledge Graphs

| Aspect                 | DBLP + CEUR-WS                                                                                       | Wikidata + Scholia                                                                                                                |
|-------------------------|------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| Schema complexity       | Simple and predictable, easy for LLMs to learn and use.                                              | Rich, fragmented, and harder for LLMs to use without strong prior context.                                                         |
| Entity linking          | Low ambiguity, literal or regex matching usually works.                                             | High ambiguity, requires robust lookup or MWAPI integration.                                                                       |
| Query performance       | Fast and stable for typical queries.                                                                | More prone to timeouts and slower response times for broad queries.                                                                |
| Search capabilities     | Minimal, basic literal or regex search.                                                             | Powerful full-text search through MWAPI.                                                                                           |
| Search robustness       | Brittle for LLM-generated queries, sensitive to small differences in wording or punctuation.         | Robust via MWAPI, tolerant to casing, punctuation, and partial matches, but requires a separate search step.                        |
| Query complexity        | Simple patterns, short queries, low cognitive load for the model.                                   | Complex patterns with multiple properties and qualifiers, more brittle without structured prompting.                               |
| LLM usability           | Easy to prompt for usable queries out of the box, minimal infrastructure needed.                    | Difficult without additional engineering; requires schema context packs, MWAPI integration, and stricter query control.            |
| Development complexity  | Low — fast to implement and get working reliably.                                                  | High — requires careful design, query templating, guardrails, and timeout handling to be reliable.                                 |
