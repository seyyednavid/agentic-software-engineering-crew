FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    OUTPUT_DIR=/app/outputs \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

COPY src ./src
COPY templates ./templates
COPY knowledge ./knowledge
COPY web_app.py ./
COPY worker.py ./

RUN mkdir -p /app/outputs \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uv","run","gunicorn","--bind","0.0.0.0:8000","--workers","1","--threads","4","--timeout","120","--access-logfile","-","--error-logfile", "-","web_app:app"]