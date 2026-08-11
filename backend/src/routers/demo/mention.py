import json
from pathlib import Path
from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter()


class MentionExtractionRequest(BaseModel):
    text: str
    model: str


class MentionExtractionResponse(BaseModel):
    result: str
    model: str


@router.post("/mention", status_code=status.HTTP_200_OK)
async def extract_mentions(request: MentionExtractionRequest):
    """
    Demo endpoint: Extract mentions from text and return mention candidates.
    For demo purposes, returns data from dblp_publications.json

    Args:
        request: MentionExtractionRequest containing text and model selection

    Returns:
        The entities data (mention candidates) from dblp_publications.json
    """
    # Load demo data from mention_extraction_demo.json
    demo_data_path = (
        Path(__file__).parent.parent.parent.parent
        / "demo-data"
        / "mention_extraction_demo.json"
    )

    try:
        with open(demo_data_path, "r") as f:
            demo_data = json.load(f)

        return demo_data
    except FileNotFoundError:
        return {"error": "Demo data file not found"}
    except json.JSONDecodeError:
        return {"error": "Failed to parse demo data file"}
