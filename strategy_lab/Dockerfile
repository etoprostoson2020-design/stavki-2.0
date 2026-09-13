FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .[dev]

COPY src ./src
COPY scripts ./scripts
COPY config ./config
COPY migrations ./migrations
COPY alembic.ini Makefile ./

ENV PYTHONPATH=/app/src
RUN useradd -m -u 10001 fsl && chown -R fsl:fsl /app
USER fsl

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/system/health || exit 1

CMD ["uvicorn", "fsl.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
