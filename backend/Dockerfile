FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install deps from pyproject.toml (optionally include dev deps for docker-compose).
ARG INSTALL_DEV=false

COPY pyproject.toml /app/pyproject.toml
COPY ./src /app/src

RUN if [ "$INSTALL_DEV" = "true" ]; then \
      pip install --no-cache-dir ".[dev]" ; \
    else \
      pip install --no-cache-dir . ; \
    fi

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
