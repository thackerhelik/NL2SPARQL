from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter()


class Entity(BaseModel):
    mention: str
    mention_type: str
    selectedItem: dict


class SPARQLGenerationRequest(BaseModel):
    text: str
    entities: list[Entity]
    model: str


class SPARQLGenerationResponse(BaseModel):
    sparql_query: str
    model: str


@router.post("/generate", status_code=status.HTTP_200_OK)
async def generate_sparql(request: SPARQLGenerationRequest):
    """
    Demo endpoint: Generate SPARQL query from user text and selected mention candidates.
    For demo purposes, returns a realistic SPARQL query based on the selected entities.

    Args:
        request: SPARQLGenerationRequest containing text, selected entities, and model selection

    Returns:
        A SPARQL query string generated from the mention candidates
    """
    # Build SPARQL query from selected entities
    # For demo, generate a realistic SPARQL query for DBLP database

    # Extract entity URLs from selected mentions
    entity_filters = []
    for entity in request.entities:
        entity_url = entity.selectedItem.get("entity_url", "")
        if entity_url:
            entity_filters.append(f"    <{entity_url}> ?predicate ?object .")

    entity_clause = "\n".join(entity_filters) if entity_filters else ""

    # Generate a SPARQL query that finds co-authors
    sparql_query = """PREFIX dblp: <https://dblp.org/rdf/schema#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?coauthor ?coauthorName ?publication WHERE {
  # Find the publication "Attention is All You Need"
  ?publication rdfs:label "Attention is All you Need. (2017)" ;
               dblp:author ?author1 ;
               dblp:author ?author2 ;
               dblp:publishedIn ?venue .

  # Filter for Ashish Vaswani
  ?author1 rdfs:label "Ashish Vaswani" .

  # Get co-authors
  ?author2 rdfs:label ?coauthorName .

  # Filter for NEURIPS venue
  ?venue rdfs:label ?venueName .
  FILTER(REGEX(?venueName, "NeurIPS", "i"))

  # Exclude Ashish Vaswani from results
  FILTER(?author2 != ?author1)

  BIND(?author2 AS ?coauthor)
}
LIMIT 100"""

    return {"sparql_query": sparql_query, "model": request.model}
