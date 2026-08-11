from pydantic import BaseModel


class SchemaUploadResponse(BaseModel):
    schema_id: str
    name: str
    endpoint: str


class SchemaCacheItem(BaseModel):
    schema_id: str
    name: str
    endpoint: str
