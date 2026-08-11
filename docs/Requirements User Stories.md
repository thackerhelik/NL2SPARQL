## Requirements User Stories

### US 1

As a user, I want to enter a natural language question so that the system can translate it into a SPARQL query that I can execute.￼

Functional Requirements:

- Query is syntactically valid SPARQL.
- User can preview and edit the generated SPARQL
- Catch SPARQL endpoint errors and present clear guidance to the user.  ￼

Non-Functional Requirements:

### US 2

As a user, I want to see candidate entities for each extracted mention so I can confirm or override the system’s choice.

Functional Requirements:

- System proposes candidates with confidence scores
- Auto approve entity candidates when confidence (Off/On)
- System returns mentions and cadidates to client.
- IRIs need to be valid to the client.

Non-Functional Requirements:

-

### US 3

- As a user I view the logs of the whole pipeline.

Functional Requirements:

- Logs are stored with trace IDs locally
- Log all candidate lists, scores and decisions for traceability.  ￼

Non-Functional Requirements:

-

### US 4

As an user, I want to view/load a context pack.  ￼

Functional Requirements:

- Switch context packs does imply without code change.
- Have at least one context pack the user can use by default (In BE).

Non-Functional Requirements:

- Cache schema and prefix information to avoid repeated network calls.  ￼

### US 5

As a user, I can switch between different Ollama models.

Non-Functional Requirements:

- At least two models are supported.
- This happens quickly. (< 1 min)

### US 6

As a user, I want to be informed if the query cannot be executed due to disallowed SPARQL features.  ￼

### US 7

As a user, I want to execute validated queries against the configured SPARQL endpoint and see the structured results.  ￼

### US 8

As a user, I want to download query results as JSON.  ￼
