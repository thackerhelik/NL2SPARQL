from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.internal.schema_cache import SCHEMA_CACHE, preload_from_env
from src.internal.utils import LOGGER
from src.routers import (
    agent_chat,
    generation,
    mentions,
    models,
    ping,
    run_query,
    schema,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    metas = preload_from_env(SCHEMA_CACHE)
    if metas:
        LOGGER.info(
            "Preloaded schemas: %s",
            ", ".join(f"{m.schema_id}({m.name})" for m in metas),
        )
    yield


app = FastAPI(title="NL2SPARQL", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ping.router, prefix="/ping", tags=["Ping"])
app.include_router(schema.router, prefix="/schema", tags=["Schema"])
app.include_router(generation.router, prefix="/generation", tags=["Generation"])
app.include_router(mentions.router, prefix="/mentions", tags=["Mentions"])
app.include_router(run_query.router, prefix="/queries", tags=["SPARQL"])
app.include_router(agent_chat.router, prefix="/agent", tags=["AgentChat"])
app.include_router(models.router, prefix="/models", tags=["Models"])
