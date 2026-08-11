import logging
import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
import rdflib

from src.internal import sparql as sparql_mod
from src.internal.schema_cache import SCHEMA_CACHE
from src.main import app
from src.schemas.run_query import RunQueryResponse, SparqlHead, SparqlResults

OLLAMA_MODEL = "gpt-oss:120b"


def setup_test_env():
    os.environ["LLM_MOCK"] = "1"
    # Avoid startup-time schema preloading interfering with tests (if user has it set).
    os.environ.pop("PRELOAD_SCHEMAS", None)


def set_log_levels():
    # set root logging level
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Silence noisy libraries unless you want their DEBUG logs
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("grpc").setLevel(logging.WARNING)
    logging.getLogger("grpc._cpython").setLevel(logging.WARNING)
    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    uvicorn_error_logger.setLevel(logging.DEBUG)
    uvicorn_error_logger.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("faker").setLevel(logging.WARNING)
    logging.getLogger("python_multipart").setLevel(logging.WARNING)
    root_logger.handlers.clear()


setup_test_env()
set_log_levels()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def kg_graph():
    graph = rdflib.Graph()
    persons_path = Path(__file__).parent / "data" / "persons.ttl"
    graph.parse(persons_path, format="turtle")
    return graph


@pytest.fixture(scope="session", autouse=True)
def patch_sparql_run(kg_graph):
    patcher = pytest.MonkeyPatch()

    async def _run(_endpoint: str, query: str, **kwargs):
        results = kg_graph.query(query)
        rows = []
        vars_set = set()
        for row in results:
            row_map = {}
            for var, val in row.asdict().items():
                vars_set.add(str(var))
                if val is None:
                    continue
                val_str = str(val)
                binding_type = (
                    "uri"
                    if val_str.startswith("http://") or val_str.startswith("https://")
                    else "literal"
                )
                row_map[str(var)] = {"value": val_str, "type": binding_type}
            rows.append(row_map)
        return RunQueryResponse(
            head=SparqlHead(vars=sorted(vars_set)), results=SparqlResults(bindings=rows)
        )

    patcher.setattr(sparql_mod, "run", _run)
    yield
    patcher.undo()


@pytest.fixture(scope="session")
def schema_id():
    schema_path = Path(__file__).parent / "data" / "dblp_schema.xml"
    data = schema_path.read_bytes()
    with SCHEMA_CACHE._lock:
        SCHEMA_CACHE._entries.clear()
    meta = SCHEMA_CACHE.put(
        data,
        name="DBLP",
        endpoint="https://sparql.dblp.org/sparql",
        base_iri="https://dblp.org/rdf/schema#",
        rdf_format="xml",
    )
    return meta.schema_id


@pytest.fixture(scope="session")
def persons_schema_id(schema_id):
    schema_path = Path(__file__).parent / "data" / "persons_schema.ttl"
    data = schema_path.read_bytes()
    meta = SCHEMA_CACHE.put(
        data,
        name="Persons",
        endpoint="http://example.org/sparql",
        base_iri="http://mydb.org/",
        rdf_format="turtle",
    )
    return meta.schema_id
