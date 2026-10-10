FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV CBS_INDEX_PATH=/data/index.db \
    CBS_HOST=0.0.0.0 \
    PORT=8000

# Bake the search index into the image (~1 min) so the first request never waits.
# The server keeps it current with incremental syncs at runtime.
RUN cbs-mcp sync

EXPOSE 8000
CMD ["cbs-mcp", "--transport", "http"]
