# Mention Extraction Evaluation

This directory contains tools for manually evaluating the accuracy of the mention extraction module (`src.internal.mentions.extraction`).

## Directory Structure

- `eval_mention_extraction.py`: The main script to run evaluations.
- `data/`: Stores "Gold Standard" JSON files for different schemas.

## How to Run

You must run the script from the `backend/` directory.

### 1. Test Persons Schema (Development)

```bash
python evaluation/eval_mention_extraction.py \
  --schema tests/data/persons_schema.ttl \
  --gold evaluation/data/persons_gold.json
```

### 2. Test Other Schemas (e.g., Pokémon)

To test a new schema (like Pokémon), you must first create a matching gold standard file (e.g., `data/pokemon_gold.json`).

```bash
python evaluation/eval_mention_extraction.py \
  --schema ../fuseki/schema/pokemon/pokemon.ttl \
  --gold evaluation/data/pokemon_gold.json
```

## Gold Standard Format

The JSON file must be a list of objects with the following structure:

```json
[
  {
    "query": "Natural language query",
    "expected_mentions": [
      {
        "text": "Exact text substring",
        "type": "Full Class IRI (e.g., http://schema.org/Person)",
        "label_pred": "Full Property IRI (e.g., http://schema.org/givenName)"
      }
    ]
  }
]
```
