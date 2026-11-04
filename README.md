# Europa: European open data for AI assistants

Europa is an [MCP](https://modelcontextprotocol.io) server that lets Claude, ChatGPT, Copilot,
Cursor and other AI apps find and fetch public data from European statistics offices and EU
sources. You ask in plain language; the assistant picks a dataset, gets the figures and names the source.

| | Sources |
|---|---|
| 🇪🇺 **EU** | Eurostat, European Commission, European Parliament, data.europa.eu |
| 🇩🇪 **Germany** | Destatis, GovData |

Example questions: *"Compare unemployment in Germany, France and the Netherlands"*,
*"What was German inflation last month?"*, *"How did Parliament vote on 8 July?"*

> Independent open-source project (EUPL-1.2), not affiliated with the EU or any statistics office.
> Data is passed on unchanged, with a `source:` link and licence in every answer.

---

## Connect it

There are two ways to connect:

- **Desktop apps** (Claude Desktop, Claude Code, VS Code, Cursor) run Europa on your own computer.
- **Web apps** (claude.ai, ChatGPT) need Europa running on a server, reachable at a URL ending in `/mcp`.
  See [Host it online](https://github.com/jadikar-arch/euro-data-mcp#host-it-online).

### Desktop apps

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first:

```bash
# Mac / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Claude Desktop**: open **Settings → Developer → Edit Config**, add the following, then restart Claude completely:

```json
{
  "mcpServers": {
    "europa": {
      "command": "uvx",
      "args": ["europa-mcp"]
    }
  }
}
```

**Cursor**: put the same JSON in `~/.cursor/mcp.json`.

**VS Code (Copilot)**: create `.vscode/mcp.json`, then click **Start** and use Copilot Chat in **Agent** mode:

```json
{
  "servers": {
    "europa": { "type": "stdio", "command": "uvx", "args": ["europa-mcp"] }
  }
}
```

**Claude Code**:

```bash
claude mcp add europa -- uvx europa-mcp
```

**Any other MCP app**: run the command `uvx europa-mcp` (stdio).

### Web apps

**claude.ai**: **Customize → Connectors → Add custom connector**. Name it *Europa*, paste your
`https://<your-server>/mcp` URL and click **Add**. In a chat, enable it under **+ → Connectors**.

**ChatGPT**: **Settings → Apps → Advanced settings**, turn on **Developer mode**, then **Create**
a connector with your `https://<your-server>/mcp` URL and authentication **None**. Enable it in a chat.
(Custom connectors are not available on every ChatGPT plan.)

### Host it online

```bash
docker build -t europa-mcp .
docker run -p 8000:8000 europa-mcp   # endpoint: http://<host>:8000/mcp
```

Put it behind HTTPS (Cloud Run, Fly.io, Railway or a reverse proxy) and use `https://<host>/mcp`.
For a quick test, run `uvx europa-mcp --transport http`
and expose it with `cloudflared tunnel --url http://localhost:8000`.

---

## Tips

- The first question can take up to a minute while the dataset index downloads. After that it's fast.
- If the assistant doesn't use the tools, add *"use the europa tools"* to your question.
- Mac: if the app can't find `uvx`, replace `"uvx"` with the full path from `which uvx`.

## Developers

Architecture, tools, configuration and tests: see [DEVELOPMENT.md](https://github.com/jadikar-arch/euro-data-mcp/blob/main/DEVELOPMENT.md).
Changes: [CHANGELOG.md](https://github.com/jadikar-arch/euro-data-mcp/blob/main/CHANGELOG.md).

## Licence

Code: [EUPL-1.2](https://github.com/jadikar-arch/euro-data-mcp/blob/main/LICENSE). Data: [Eurostat](https://ec.europa.eu/eurostat), the European Commission,
the [European Parliament](https://data.europarl.europa.eu), [data.europa.eu](https://data.europa.eu)
(CC BY 4.0 / Commission reuse policy), [Destatis](https://www.destatis.de) and
[GovData](https://www.govdata.de) (Datenlizenz Deutschland or per-dataset licence).
