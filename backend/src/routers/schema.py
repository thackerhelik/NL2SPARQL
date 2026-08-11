from __future__ import annotations

from enum import Enum
import json
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, ValidationError

from src.internal.schema_cache import (
    SCHEMA_CACHE,
    PinnedSchemaError,
    SchemaCacheMeta,
    SchemaIndex,
)
from src.internal.utils import LOGGER
from src.schemas.schema_cache import SchemaUploadResponse

router = APIRouter()


class RDFFormat(str, Enum):
    xml = "xml"
    turtle = "turtle"
    n3 = "n3"
    nt = "nt"
    json_ld = "json-ld"
    trig = "trig"


class SchemaExample(BaseModel):
    question: str = Field(min_length=1)
    sparql: str = Field(min_length=1)


class SchemaSettingsResponse(BaseModel):
    schema_id: str
    name: str
    endpoint: str
    examples: list[SchemaExample] = Field(default_factory=list)
    description: str = ""


class SchemaPatchRequest(BaseModel):
    name: Optional[str] = None
    endpoint: Optional[str] = None
    examples: Optional[list[SchemaExample]] = None
    description: Optional[str] = None


def _to_settings_response(meta: SchemaCacheMeta) -> SchemaSettingsResponse:
    parsed_examples: list[SchemaExample] = []
    for item in meta.examples:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        sparql = str(item.get("sparql") or "").strip()
        if question and sparql:
            parsed_examples.append(SchemaExample(question=question, sparql=sparql))
    return SchemaSettingsResponse(
        schema_id=meta.schema_id,
        name=meta.name,
        endpoint=meta.endpoint,
        examples=parsed_examples,
        description=meta.description or "",
    )


def _serialize_examples(examples: list[SchemaExample]) -> list[dict[str, str]]:
    serialized: list[dict[str, str]] = []
    for example in examples:
        question = example.question.strip()
        sparql = example.sparql.strip()
        if not question or not sparql:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each example must include non-empty question and sparql.",
            )
        serialized.append({"question": question, "sparql": sparql})
    return serialized


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=SchemaUploadResponse,
)
async def upload_schema(
    schema_file: UploadFile = File(...),
    endpoint_url: str = Form(default="https://sparql.dblp.org/sparql"),
    name: Optional[str] = Form(None),
    base_iri: str = Form(default="https://dblp.org/rdf/schema#"),
    rdf_format: Optional[RDFFormat] = Form(None),
    examples_json: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
) -> SchemaUploadResponse:
    LOGGER.info(f"Schema upload started name={name or schema_file.filename}")
    data = await schema_file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded schema file is empty.",
        )

    parsed_examples: list[SchemaExample] = []
    if examples_json and examples_json.strip():
        try:
            raw_examples = json.loads(examples_json)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="examples_json must be valid JSON.",
            ) from e
        if not isinstance(raw_examples, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="examples_json must be a JSON array.",
            )
        for item in raw_examples:
            if not isinstance(item, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Each example must be an object with question and sparql.",
                )
            try:
                parsed_examples.append(
                    SchemaExample(
                        question=str(item.get("question") or ""),
                        sparql=str(item.get("sparql") or ""),
                    )
                )
            except ValidationError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid example payload: {e.errors()}",
                ) from e

    try:
        meta = SCHEMA_CACHE.put(
            data,
            name=(name or schema_file.filename or "schema.rdf"),
            endpoint=endpoint_url,
            base_iri=base_iri,
            rdf_format=rdf_format.value if rdf_format else None,
            description=(description or ""),
        )
        if parsed_examples:
            updated_meta = SCHEMA_CACHE.update_meta(
                meta.schema_id,
                examples=_serialize_examples(parsed_examples),
            )
            if updated_meta is not None:
                meta = updated_meta
    except ValueError as e:
        LOGGER.warning(f"Schema upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    LOGGER.info(f"Schema cached id={meta.schema_id} name={meta.name}")
    return SchemaUploadResponse(
        schema_id=meta.schema_id,
        name=meta.name,
        endpoint=meta.endpoint,
    )


@router.get(
    "", response_model=list[SchemaSettingsResponse], status_code=status.HTTP_200_OK
)
async def list_schemas() -> list[SchemaSettingsResponse]:
    LOGGER.info("Listing cached schemas")
    return [_to_settings_response(meta) for meta in SCHEMA_CACHE.list_meta()]


@router.get("/{schema_id}", response_model=SchemaSettingsResponse)
async def get_schema(schema_id: str) -> SchemaSettingsResponse:
    LOGGER.info(f"Fetching schema settings id={schema_id}")
    meta = SCHEMA_CACHE.get_meta(schema_id)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schema not found in cache.",
        )
    return _to_settings_response(meta)


@router.patch("/{schema_id}", response_model=SchemaSettingsResponse)
async def patch_schema(
    schema_id: str, payload: SchemaPatchRequest
) -> SchemaSettingsResponse:
    LOGGER.info(f"Patching schema settings id={schema_id}")
    name = payload.name.strip() if payload.name is not None else None
    endpoint = payload.endpoint.strip() if payload.endpoint is not None else None
    examples = (
        _serialize_examples(payload.examples) if payload.examples is not None else None
    )
    description = (
        payload.description.strip() if payload.description is not None else None
    )

    if payload.name is not None and not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Schema name cannot be empty.",
        )
    if payload.endpoint is not None and not endpoint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Schema endpoint cannot be empty.",
        )

    meta = SCHEMA_CACHE.update_meta(
        schema_id,
        name=name,
        endpoint=endpoint,
        examples=examples,
        description=description,
    )
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schema not found in cache.",
        )
    return _to_settings_response(meta)


@router.delete("/{schema_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schema(schema_id: str) -> None:
    LOGGER.info(f"Deleting schema id={schema_id}")
    try:
        deleted = SCHEMA_CACHE.delete(schema_id)
    except PinnedSchemaError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schema not found in cache.",
        )


@router.get("/{schema_id}/data", status_code=status.HTTP_200_OK)
async def get_schema_data(schema_id: str) -> SchemaIndex:
    LOGGER.info(f"Fetching parsed schema data id={schema_id}")
    index = SCHEMA_CACHE.get(schema_id)
    if index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schema not found in cache.",
        )
    return index
