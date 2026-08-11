from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RequestRunQuery(BaseModel):
    query: str
    endpoint_url: str
    schema_id: str


class RequestValidateQuery(BaseModel):
    query: str
    schema_id: str


class ValidateQueryResponse(BaseModel):
    valid: bool
    cleaned_query: Optional[str] = None
    error: Optional[str] = None


class SparqlBindingValue(BaseModel):
    type: str
    value: str
    datatype: Optional[str] = None
    xml_lang: Optional[str] = Field(None, alias="xml:lang")


class SparqlResults(BaseModel):
    bindings: Optional[List[Dict[str, SparqlBindingValue]]] = None


class SparqlHead(BaseModel):
    vars: Optional[List[str]] = None


class RunQueryResponse(BaseModel):
    head: SparqlHead
    results: Optional[SparqlResults] = None
    boolean: Optional[bool] = None
