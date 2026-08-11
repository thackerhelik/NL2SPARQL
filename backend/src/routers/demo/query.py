import json
from pathlib import Path
from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter()


class QueryRequest(BaseModel):
    sparql_query: str
    model: str


class QueryResponse(BaseModel):
    results: list
    model: str


@router.post("/query", status_code=status.HTTP_200_OK)
async def query(request: QueryRequest):
    """
    Demo endpoint: Execute SPARQL query and return results.
    For demo purposes, returns data from result-demo.json

    Args:
        request: ExecuteSPARQLRequest containing SPARQL query and model selection

    Returns:
        Query results from result-demo.json
    """
    # Load demo results from result-demo.json
    demo_results_path = (
        Path(__file__).parent.parent.parent.parent / "demo-data" / "result-demo.json"
    )

    try:
        with open(demo_results_path, "r") as f:
            demo_results = json.load(f)

        return {"results": demo_results.get("results", []), "model": request.model}
    except FileNotFoundError:
        return {"error": "Demo results file not found"}
    except json.JSONDecodeError:
        return {"error": "Failed to parse demo results file"}
