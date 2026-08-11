from fastapi import APIRouter, HTTPException, status

from src.internal.schema_cache import SCHEMA_CACHE
from src.internal.sparql import DisallowedQueryTypeError, run, validate_query
from src.internal.utils import LOGGER
from src.schemas.run_query import (
    RequestRunQuery,
    RequestValidateQuery,
    RunQueryResponse,
    ValidateQueryResponse,
)

router = APIRouter()


@router.post(
    "/validate",
    response_model=ValidateQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate SPARQL Query",
    description="Checks SPARQL syntax and query type without executing it.",
)
async def validate_sparql_query(request: RequestValidateQuery):
    try:
        index = SCHEMA_CACHE.get(request.schema_id)
        if not index:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Schema with id {request.schema_id} not found",
            )

        cleaned = validate_query(request.query, ctx=index)
        return ValidateQueryResponse(valid=True, cleaned_query=cleaned)
    except DisallowedQueryTypeError as e:
        return ValidateQueryResponse(valid=False, error=str(e))
    except ValueError as e:
        return ValidateQueryResponse(valid=False, error=str(e))


@router.post(
    "/run",
    response_model=RunQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Run SPARQL Query",
    description="Validates and executes a SPARQL query against a remote endpoint.",
)
async def execute_query(request: RequestRunQuery):
    LOGGER.info(
        f"SPARQL request endpoint={request.endpoint_url} query={request.query[:50]}..."
    )

    index = SCHEMA_CACHE.get(request.schema_id)
    if not index:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema with id {request.schema_id} not found",
        )

    try:
        result = await run(
            endpoint=request.endpoint_url,
            query=request.query,
            validate=True,
            ctx=index,
        )

        LOGGER.info(f"SPARQL request completed for endpoint={request.endpoint_url}")
        return result

    except DisallowedQueryTypeError as ve:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(ve),
        ) from ve
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SPARQL Syntax Error: {str(ve)}",
        ) from ve

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to communicate with SPARQL endpoint: {str(e)}",
        ) from e
