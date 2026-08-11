import functools
import logging
import time
from typing import Any, Awaitable, Callable, TypeVar, cast

LOGGER = logging.getLogger("app")
LOGGER.setLevel(logging.DEBUG)
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    LOGGER.addHandler(handler)

# Silence noisy libraries
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("grpc").setLevel(logging.WARNING)
logging.getLogger("grpc._cpython").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("faker").setLevel(logging.WARNING)
logging.getLogger("python_multipart").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("uvicorn.asgi").setLevel(logging.INFO)


F = TypeVar("F", bound=Callable[..., Any])
AF = TypeVar("AF", bound=Callable[..., Awaitable[Any]])


import unicodedata


def normalize_text(text: str) -> str:
    """Normalize text by removing accents, invisible characters, and converting to lowercase."""
    if not text:
        return ""
    # Remove soft hyphens and other common invisible separators
    text = (
        str(text)
        .replace("\u00ad", "")
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
    )
    # Normalize unicode characters and remove non-spacing marks (accents)
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def fix_encoding(text: str) -> str:
    """Fix mojibake and double-escaped unicode sequences safely."""
    # 1. Fix Mojibake
    try:
        text = text.encode("latin1").decode("utf8")
    except Exception:
        pass

    # 2. Fix Double-Escapes safely
    import re

    if r"\u" in text or r"\U" in text:
        try:
            # Decode the actual escaped sequences, leaving surrounding valid UTF-8 text untouched
            text = re.sub(
                r"\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})",
                lambda m: chr(int(m.group(1) or m.group(2), 16)),
                text,
            )
            # Re-encode and decode via UTF-16 to safely recombine lone surrogates (e.g. emojis)
            text = text.encode("utf-16", "surrogatepass").decode("utf-16")
        except Exception:
            pass
    return text


def timed(label: str | None = None) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        name = label or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            start = time.perf_counter()
            LOGGER.debug(f"{name} start")
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                LOGGER.debug(f"{name} end ({elapsed:.3f}s)")

        return cast(F, wrapper)

    return decorator


def timed_async(label: str | None = None) -> Callable[[AF], AF]:
    def decorator(func: AF) -> AF:
        name = label or func.__name__

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            start = time.perf_counter()
            LOGGER.debug(f"{name} start")
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                LOGGER.debug(f"{name} end ({elapsed:.3f}s)")

        return cast(AF, wrapper)

    return decorator
