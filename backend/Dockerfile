# Build context is the repo root (see docker-compose.yml) so we can pull in
# config/ and scripts/ alongside the backend app.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY config ./config
COPY scripts ./scripts

ENV VENDORLENS_CONFIG_DIR=/app/config \
    VENDORLENS_DB=/app/data/vendorlens.db \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Generate the deterministic demo DB on start (identical every run), then serve.
CMD ["sh", "-c", "python scripts/generate_data.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
