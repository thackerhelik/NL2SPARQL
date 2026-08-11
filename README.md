# Context-Aware NL2SPARQL with Interactive Linking

> ** Academic Project Archive**
> This repository is a mirror of a collaborative university project developed for the **Knowledge Graph Lab** at RWTH Aachen University. 
>
> **Authors & Team Members:**
> * Helik Thacker
> * Wensheng Zhang
> * Julius Kaltwasser
> * Mauricio Kaupp Garcia
> * Jeffry Cacho Aboukhalil

## Repository layout

- `backend/`: FastAPI services for NL2SPARQL pipeline components.
  - `routers`: API endpoints for different pipeline stages.
  - `internal`: Python modules for processing logic.
  - `prompts/`: LLM prompt templates used by the backend.
  - `schemas/`: Pydantic models for request/response validation.
- `frontend/`: Next.js application for the chat + approval UI.
- `notebooks/`: Jupyter notebooks for prototyping queries and components.
- `docs/`: Documentation, requirements, glossary, and research notes.

## Getting started

### Prereqs

- Docker (for compose-based dev)

### Required files

Create an environment variable file in the folder where docker compose file locates.

You can copy the `.env.example`

```
cp .env.example .env
```

or

```
OLLAMA_API_KEY=your_key_here
RWTHGPT_API_KEY=your_key_here
```

### Run with Docker (for local development)

From repo root:

1. `docker compose up --build`
2. Backend docs: <http://localhost:8080/docs>

When running via Docker Compose, the schema files are mounted into the backend container
automatically, so you don’t need to configure paths.

### Deploy

For deployment use `docker-compose-deploy.yml` which is optimized for production (no dev dependencies, no hot reload, etc.).

### Tooling notes (why these exist)

- `pyproject.toml`: single source of truth for dependencies and tooling config.
- `ruff`: fast Python linting/formatting for consistent style.
- `pre-commit`: runs lightweight checks before commits to keep main clean.
- Docker Compose: standardizes local runtime for the backend.

## Pre-commit hooks

To make sure our code style is consistent, we use pre-commit hooks. To set them up, run:

1. `pip install pre-commit`
2. `pre-commit install`
3. Run manually with `pre-commit run --all-files` when needed.
