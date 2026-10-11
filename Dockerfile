FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV EUROPA_CACHE_DIR=/data \
    EUROPA_HOST=0.0.0.0 \
    PORT=8000

# Bake the CBS index and the find_data map into the image so the first request never waits.
# The server keeps both current at runtime.
RUN europa-mcp map

EXPOSE 8000
CMD ["europa-mcp", "--transport", "http"]
