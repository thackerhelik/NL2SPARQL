from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from src.schemas.mentions import Mention

# also import linked entities
# user input


class Query(BaseModel):
    query: str
    # error: str = None


class UserPrompt(BaseModel):
    query: str


class SystemPrompt(BaseModel):
    query: str


class LinkedMention(Mention):
    iri: str
    label_pred: Optional[str] = None


class LinkedMentions(BaseModel):
    mentions: List[LinkedMention]


class Example(BaseModel):
    question: str
    mentions: LinkedMentions
    sparql: Query


class Examples(BaseModel):
    items: List[Example]


class PromptExample(BaseModel):
    question: str
    sparql: str


class Function(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]


class Tool(BaseModel):
    type: str = "function"
    function: Function


class RequestQueryGeneration(BaseModel):
    question: str
    mentions: LinkedMentions
    schema_id: str
    examples: Optional[List[PromptExample]] = None
    model: str = "RWTH-GPT-gpt-oss-120b"
