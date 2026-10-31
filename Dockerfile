FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV EUROPA_CACHE_DIR=/data \
    EUROPA_HOST=0.0.0.0 \
    PORT=8000

# Bake the find_data map into the image so the first request never waits.
# The server keeps it current at runtime.
RUN europa-mcp map

EXPOSE 8000
# Optional: EUROPA_API_KEYS=key1,key2 (require a bearer token), EUROPA_USAGE_LOG=/data/usage.jsonl
# (anonymous query log; summarise with `europa-mcp usage`), EUROPA_RATE_LIMIT_RPS (per client IP, default 5).
RUN useradd --create-home app && chown -R app /data
USER app
CMD ["europa-mcp", "--transport", "http"]
