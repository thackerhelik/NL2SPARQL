from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Mention(BaseModel):
    text: str
    type: str
    label_pred: str = Field(
        description="The predicate label that indicates the type of this mention"
    )
    attrs: Dict[str, str] = Field(default_factory=dict)
    selected_candidate_iri: Optional[str] = None


class MentionList(BaseModel):
    mentions: List[Mention]


class CandidateVariant(BaseModel):
    uri: str
    pred: str
    label: Optional[str] = None
    role: Optional[str] = None
    match_exact: bool = False
    tokens_matched: int = 0
    degree: int = 0


class OneHopTriple(BaseModel):
    p: str
    value: str


class Candidate(BaseModel):
    score: Optional[float] = None
    uri: str
    degree: int = 0
    tokens_matched: int = 0
    match_exact: bool = False
    variants: List[CandidateVariant] = Field(default_factory=list)
    context: List[OneHopTriple] = Field(default_factory=list)


class DetailedMention(Mention):
    candidates: List[Candidate] = Field(default_factory=list)


class MentionStatusRow(BaseModel):
    mention_id: int
    text: str
    type: str
    label_pred: str
    candidate_count: int = 0
    reranked: bool = False
    top_candidate_iri: Optional[str] = None
    top_candidate_label: Optional[str] = None
    top_score: Optional[float] = None
    ambiguous: bool = False
    ready: bool = False


class MentionsAgentResult(BaseModel):
    mentions: List[DetailedMention] = Field(default_factory=list)
    assistant_message: Optional[str] = None
    status: List[MentionStatusRow] = Field(default_factory=list)


class RequestMentions(BaseModel):
    query: str
    schema_id: str
    model: str = "RWTH-GPT-gpt-oss:120b"
    limit: int = 30
