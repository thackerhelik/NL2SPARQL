from collections import OrderedDict
import json
import os
from pathlib import Path
import re
from threading import Lock
import time
from typing import Any, Optional
import uuid

from pydantic import BaseModel, Field

from src.internal.schema_index import load_schema_bytes
from src.schemas.schema_index import SchemaIndex

_SCHEMA_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class SchemaCacheMeta(BaseModel):
    schema_id: str
    name: str
    endpoint: str
    description: str = ""
    examples: list[dict[str, str]] = Field(default_factory=list)
    created_at_unix_s: float
    last_access_unix_s: float


class _SchemaCacheEntry(BaseModel):
    meta: SchemaCacheMeta
    schema_index: SchemaIndex


class PinnedSchemaError(ValueError):
    pass


class SchemaCache:
    def __init__(
        self,
        *,
        max_items: int = 5,
        persist_dir: Optional[Path] = None,
        pinned_ids: Optional[set[str]] = None,
    ) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be >= 1")
        self._max_items = max_items
        self._lock = Lock()
        self._entries: OrderedDict[str, _SchemaCacheEntry] = OrderedDict()
        self._persist_dir = Path(persist_dir) if persist_dir else None
        self._pinned_ids: set[str] = set(pinned_ids or set())
        self._load_from_disk()

    @property
    def max_items(self) -> int:
        return self._max_items

    @property
    def pinned_ids(self) -> set[str]:
        return set(self._pinned_ids)

    def pin(self, schema_id: str) -> None:
        _validate_schema_id(schema_id)
        with self._lock:
            self._pinned_ids.add(schema_id)

    def put(
        self,
        data: bytes,
        *,
        schema_id: Optional[str] = None,
        name: str,
        endpoint: str,
        base_iri: Optional[str] = None,
        rdf_format: Optional[str] = None,
        description: Optional[str] = None,
        overwrite: bool = False,
    ) -> SchemaCacheMeta:
        """
        Insert a schema into the cache.

        - When `schema_id` is None, a random UUID is generated.
        - When `schema_id` is provided, it must match `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`.
          This enables "well-known" schemas like `DBLP`.
        - If `schema_id` already exists and `overwrite` is False, this is a no-op and the
          existing meta is returned (idempotent preload).
        """
        if schema_id is None:
            schema_id = str(uuid.uuid4())
        else:
            _validate_schema_id(schema_id)

        now = time.time()

        with self._lock:
            existing = self._entries.get(schema_id)
            if existing is not None and not overwrite:
                existing.meta = existing.meta.model_copy(
                    update={"last_access_unix_s": now}
                )
                self._entries.move_to_end(schema_id, last=True)
                self._save_to_disk(schema_id)
                return existing.meta

        # Parse the schema bytes into a SchemaIndex
        schema = load_schema_bytes(data, base_iri=base_iri, rdf_format=rdf_format)
        schema = schema.model_copy(update={"endpoint": endpoint})

        meta = SchemaCacheMeta(
            schema_id=schema_id,
            name=name,
            endpoint=endpoint,
            description=(description or ""),
            examples=[],
            created_at_unix_s=now,
            last_access_unix_s=now,
        )

        with self._lock:
            self._entries[schema_id] = _SchemaCacheEntry(meta=meta, schema_index=schema)
            self._entries.move_to_end(schema_id, last=True)
            while len(self._entries) > self._max_items:
                dropped_id = self._drop_one_lru_unpinned()
                if dropped_id is None:
                    break
            self._save_to_disk(schema_id)
        return meta

    def get(self, schema_id: str) -> Optional[SchemaIndex]:
        now = time.time()
        with self._lock:
            entry = self._entries.get(schema_id)
            if entry is None:
                return None
            entry.meta = entry.meta.model_copy(update={"last_access_unix_s": now})
            self._entries.move_to_end(schema_id, last=True)
            self._save_to_disk(schema_id)
            return entry.schema_index

    def get_meta(self, schema_id: str) -> Optional[SchemaCacheMeta]:
        with self._lock:
            entry = self._entries.get(schema_id)
            return entry.meta if entry else None

    def list_meta(self) -> list[SchemaCacheMeta]:
        with self._lock:
            return [e.meta for e in self._entries.values()]

    def update_meta(
        self,
        schema_id: str,
        *,
        name: Optional[str] = None,
        endpoint: Optional[str] = None,
        examples: Optional[list[dict[str, str]]] = None,
        description: Optional[str] = None,
    ) -> Optional[SchemaCacheMeta]:
        now = time.time()
        with self._lock:
            entry = self._entries.get(schema_id)
            if entry is None:
                return None

            updates: dict[str, Any] = {"last_access_unix_s": now}
            if name is not None:
                updates["name"] = name
            if endpoint is not None:
                updates["endpoint"] = endpoint
                entry.schema_index = entry.schema_index.model_copy(
                    update={"endpoint": endpoint}
                )
            if description is not None:
                updates["description"] = description
            if examples is not None:
                updates["examples"] = examples

            entry.meta = entry.meta.model_copy(update=updates)
            self._entries.move_to_end(schema_id, last=True)
            self._save_to_disk(schema_id)
            return entry.meta

    def delete(self, schema_id: str) -> bool:
        with self._lock:
            if schema_id in self._pinned_ids:
                raise PinnedSchemaError(f"Schema {schema_id} is pinned.")
            entry = self._entries.pop(schema_id, None)
            if entry is None:
                return False
            self._pinned_ids.discard(schema_id)
            self._delete_from_disk(schema_id)
            return True

    def _drop_one_lru_unpinned(self) -> Optional[str]:
        """
        Drop one least-recently-used schema that is not pinned.
        Returns dropped schema_id, or None if no unpinned entries exist.
        """
        for sid in list(self._entries.keys()):
            if sid in self._pinned_ids:
                continue
            self._entries.pop(sid, None)
            self._delete_from_disk(sid)
            return sid
        return None

    def _entry_path(self, schema_id: str) -> Optional[Path]:
        if self._persist_dir is None:
            return None
        return self._persist_dir / f"{schema_id}.json"

    def _save_to_disk(self, schema_id: str) -> None:
        path = self._entry_path(schema_id)
        if path is None:
            return
        entry = self._entries.get(schema_id)
        if entry is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry.model_dump_json())

    def _delete_from_disk(self, schema_id: str) -> None:
        path = self._entry_path(schema_id)
        if path is None:
            return
        try:
            path.unlink()
        except FileNotFoundError:
            return

    def _load_from_disk(self) -> None:
        if self._persist_dir is None or not self._persist_dir.exists():
            return
        entries: list[_SchemaCacheEntry] = []
        for path in self._persist_dir.glob("*.json"):
            try:
                data = path.read_text()
                entries.append(_SchemaCacheEntry.model_validate_json(data))
            except Exception:
                continue

        entries.sort(key=lambda e: e.meta.last_access_unix_s)
        for entry in entries[-self._max_items :]:
            self._entries[entry.meta.schema_id] = entry
            self._entries.move_to_end(entry.meta.schema_id, last=True)


def _validate_schema_id(schema_id: str) -> None:
    if not _SCHEMA_ID_RE.match(schema_id or ""):
        raise ValueError(
            "Invalid schema_id; use 1-64 chars: [A-Za-z0-9] then [A-Za-z0-9_-]*"
        )


def _truthy_env(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def _repo_root() -> Path:
    # backend/src/internal/schema_cache.py -> repo root is 3 levels up from backend/
    return Path(__file__).resolve().parents[3]


def _first_existing_path(*paths: Path) -> Path:
    for p in paths:
        if p.exists():
            return p
    return paths[0]


def _default_schema_path(schema_key: str) -> Path:
    """
    Pick a schema path without requiring extra env vars.

    In Docker Compose we mount:
      - ./fuseki/schema         -> /app/fuseki-schema (read-only)
      - ./backend/tests/data    -> /app/backend-test-data (read-only)

    For DBLP, we ship a local fallback under src/internal/data to keep preload
    self-contained for backend startup.
    """
    r = _repo_root()
    key = schema_key.upper()
    if key == "DBLP":
        return _first_existing_path(
            Path(__file__).resolve().with_name("data") / "dblp.rdf",
            Path("/app/fuseki-schema/dblp/dblp.rdf"),
            r / "fuseki" / "schema" / "dblp" / "dblp.rdf",
        )
    if key == "PERSONS":
        return _first_existing_path(
            Path("/app/backend-test-data/persons_schema.ttl"),
            r / "backend" / "tests" / "data" / "persons_schema.ttl",
        )
    return r / "unknown"


def _default_examples_path() -> Path:
    return Path(__file__).resolve().with_name("data") / "preloaded_schema_examples.json"


def _load_preloaded_examples() -> dict[str, list[dict[str, str]]]:
    """
    Load schema examples from a JSON file.

    Expected shape:
      {
        "DBLP": [{"question": "...", "sparql": "..."}],
        "PERSONS": [...]
      }
    """
    path = Path(os.getenv("PRELOAD_SCHEMA_EXAMPLES_PATH") or _default_examples_path())
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text())
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    examples_by_key: dict[str, list[dict[str, str]]] = {}
    for key, examples in raw.items():
        if not isinstance(key, str) or not isinstance(examples, list):
            continue
        normalized_examples: list[dict[str, str]] = []
        for item in examples:
            if not isinstance(item, dict):
                continue
            question = item.get("question")
            sparql = item.get("sparql")
            if not isinstance(question, str) or not isinstance(sparql, str):
                continue
            q = question.strip()
            s = sparql.strip()
            if not q or not s:
                continue
            normalized_examples.append({"question": q, "sparql": s})
        examples_by_key[key.strip().upper()] = normalized_examples

    return examples_by_key


def preload_from_env(cache: "SchemaCache") -> list[SchemaCacheMeta]:
    """
    Preload well-known schemas into the cache (optional).

    Controlled by env var:
      - PRELOAD_SCHEMAS unset/empty -> load DBLP
            - PRELOAD_SCHEMAS=true/1/all  -> load DBLP, PERSONS
            - PRELOAD_SCHEMAS=PERSONS -> load PERSONS as well

    Each schema can be customized with:
      - <KEY>_SCHEMA_PATH
      - <KEY>_ENDPOINT_URL
    """
    raw = (os.getenv("PRELOAD_SCHEMAS") or "").strip()
    if not raw:
        return []

    keys = ["DBLP"]
    if raw.lower() in {"1", "true", "all", "yes", "on"}:
        keys.extend(["PERSONS"])
    else:
        keys.extend(k.strip().upper() for k in raw.split(",") if k.strip())

    defaults = {
        "DBLP": {
            "schema_id": "DBLP",
            "name": "DBLP",
            "schema_path": _default_schema_path("DBLP"),
            "endpoint": "https://sparql.dblp.org/sparql",
            "rdf_format": "xml",
            "base_iri": "https://dblp.org/rdf/schema#",
            "desc": "The DBLP computer science bibliography. Contains data about publications, authors, venues, etc.",
        },
        "PERSONS": {
            "schema_id": "PERSONS",
            "name": "Persons",
            "schema_path": _default_schema_path("PERSONS"),
            "endpoint": "http://example.org/sparql",
            "rdf_format": "turtle",
            "base_iri": None,
            "desc": "A simple persons ontology.",
        },
    }

    loaded: list[SchemaCacheMeta] = []
    examples_by_key = _load_preloaded_examples()

    for key in keys:
        spec = defaults.get(key)
        if spec is None:
            continue

        schema_path = Path(os.getenv(f"{key}_SCHEMA_PATH") or spec["schema_path"])
        endpoint = os.getenv(f"{key}_ENDPOINT_URL") or spec["endpoint"]
        if not schema_path.exists():
            # Best-effort: skip if files are not present (common in minimal docker images).
            continue

        cache.pin(spec["schema_id"])
        meta = cache.put(
            schema_path.read_bytes(),
            schema_id=spec["schema_id"],
            name=spec["name"],
            endpoint=endpoint,
            base_iri=spec["base_iri"],
            rdf_format=spec["rdf_format"],
            description=spec["desc"],
            overwrite=_truthy_env(f"{key}_OVERWRITE"),
        )
        preloaded_examples = examples_by_key.get(key)
        if preloaded_examples is not None:
            maybe_updated = cache.update_meta(
                spec["schema_id"], examples=preloaded_examples
            )
            if maybe_updated is not None:
                meta = maybe_updated
        loaded.append(meta)

    return loaded


_CACHE_DIR = os.getenv("SCHEMA_CACHE_DIR")
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "schema_cache"
SCHEMA_CACHE = SchemaCache(
    max_items=15,
    persist_dir=Path(_CACHE_DIR) if _CACHE_DIR else _DEFAULT_CACHE_DIR,
)
