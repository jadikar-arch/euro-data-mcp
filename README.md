# cbs-mcp

An MCP server for [CBS](https://www.cbs.nl) (Statistics Netherlands) open data. It is built on the
OData v4 API at `https://datasets.cbs.nl/odata/v1` and keeps its responses small to save tokens.

Ask *"What's the population of Amsterdam?"* and the model resolves it in about 4 tool calls. Each
response is compact text, usually under 400 tokens.

## Tools

| Tool | Use it to |
|---|---|
| `search_datasets(query, catalog="CBS", include_discontinued=False, limit=10)` | Find tables by topic. Dutch keywords work best, and common English terms are translated. |
| `describe_dataset(dataset_id)` | See a table's measures and its dimensions, with code counts and the latest period. |
| `list_codes(dataset_id, dimension, query=None, limit=50)` | Look up codes, e.g. `Amsterdam → GM0363`. Use `"Measures"` for measure codes. |
| `get_observations(dataset_id, measures, filters, latest=False, limit=500)` | Fetch values. `latest=true` returns the newest period with data. |
| `upcoming_releases(days=14, limit=30)` | List tables that get new data soon. |

Example flow:

```
search_datasets("bevolking regio")                         → 37230ned Bevolkingsontwikkeling; regio per maand
list_codes("37230ned", "RegioS", "Amsterdam")              → GM0363|Amsterdam|Gemeenten per provincie
get_observations("37230ned", ["M000098"], {"RegioS": ["GM0363"]}, latest=true)
  → fixed: Regio's=Amsterdam; Perioden=2026 augustus; measure=Bevolking aan het begin van de periode
    value
    944322
```

## How search works

The CBS API has no real search: `$search` is ignored, and the catalog is Dutch-only. The server
therefore keeps a local **SQLite FTS5 index** of all ~4,900 tables. It indexes titles, descriptions,
and the measure and dimension names of active tables. Results are ranked by title matches, then
BM25, then status and recency.

- **First run:** search is ready after a few seconds, once the catalog is in. Measure and dimension
  names are then indexed in the background (about 45 s total). The other tools never wait.
- **Staying current:** every 6 hours the server compares each table's `Version` with CBS and
  refetches only the tables that changed (about 1 s when nothing changed). Tables CBS has removed
  are deleted from the index. Cached metadata for changed tables is invalidated.
- **New tables:** they work right away in the other tools; search finds them after the next sync.
- **Location:** the user cache dir (e.g. `~/Library/Caches/cbs-mcp/index.db`), or `CBS_INDEX_PATH`.

Manual sync: `cbs-mcp sync` (add `--full` to rebuild, or `--no-details` to skip measure names).

## Install & run

Requires [uv](https://docs.astral.sh/uv/).

```bash
uvx --from git+https://github.com/<you>/cbs-mcp cbs-mcp   # stdio (default)
uvx --from . cbs-mcp                                      # from a local checkout
cbs-mcp --transport http --port 8000                      # Streamable HTTP at /mcp
```

Once the package is published to PyPI, `uvx cbs-mcp` works as written below. Until then, replace
`uvx cbs-mcp` with `uvx --from /absolute/path/to/checkout cbs-mcp` (or the `git+` URL above).

| Env var | Default | |
|---|---|---|
| `CBS_INDEX_PATH` | user cache dir | SQLite index location |
| `CBS_INDEX_REFRESH_HOURS` | `6` | Sync interval |
| `CBS_RATE_LIMIT_RPS` | `5` | HTTP mode: sustained requests per second (burst 20) |
| `CBS_HOST` / `PORT` | `127.0.0.1` / `8000` | HTTP bind address |
| `CBS_LOG_LEVEL` | `INFO` | Logs go to stderr only |

## Connect a client

### Local clients (stdio)

**Claude Code**

```bash
claude mcp add --transport stdio cbs -- uvx cbs-mcp
```

**VS Code** (Copilot agent mode): `.vscode/mcp.json`

```json
{
  "servers": {
    "cbs": { "type": "stdio", "command": "uvx", "args": ["cbs-mcp"] }
  }
}
```

**Cursor**: `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global)

```json
{
  "mcpServers": {
    "cbs": { "type": "stdio", "command": "uvx", "args": ["cbs-mcp"] }
  }
}
```

**OpenCode**: `opencode.json`

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "cbs": { "type": "local", "command": ["uvx", "cbs-mcp"], "enabled": true }
  }
}
```

**Claude Desktop**: `claude_desktop_config.json`

```json
{
  "mcpServers": {
    "cbs": { "command": "uvx", "args": ["cbs-mcp"] }
  }
}
```

### Web chat apps (remote HTTP)

ChatGPT and claude.ai connect from their own cloud, so the server must be reachable at a
**public HTTPS URL**. Deploy it (see Docker below), or for a quick test run it locally and expose it
with `cloudflared tunnel --url http://localhost:8000` or `ngrok http 8000`. The MCP endpoint is
`https://<host>/mcp`. No authentication is needed because CBS data is public; HTTP mode has rate
limiting.

- **claude.ai** (Pro/Max): Customize → Connectors → **+** → *Add custom connector* → paste the URL.
  Then enable it per chat under **+** → Connectors. On Team/Enterprise plans, an owner adds it first.
- **ChatGPT**: enable *Developer mode* (Settings → Apps → Advanced), then create a connector with the
  URL and set authentication to *none*. Plan availability and menu locations have changed during 2026,
  so check OpenAI's help center.
- **VS Code / Cursor / Claude Code**, using a deployed server instead of a local one:
  `{"type": "http", "url": "https://<host>/mcp"}` or `claude mcp add --transport http cbs https://<host>/mcp`.

## Docker

```bash
docker build -t cbs-mcp .     # bakes the search index into the image (~1 min)
docker run -p 8000:8000 cbs-mcp
```

The baked index means a restarted container serves search immediately and only syncs the changes
since the build. On hosts that wipe the disk (Cloud Run, Fly.io, etc.) that's a few seconds at most.

## Development

```bash
uv sync
uv run pytest            # mocked HTTP (respx)
uv run pytest -m live    # end-to-end smoke test against the real API
npx @modelcontextprotocol/inspector uv run cbs-mcp
```

Put the server command first. The Inspector parses flags such as `uvx --from .` as its own options.
API findings are in [NOTES.md](NOTES.md).
