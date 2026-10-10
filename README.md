# CBS Statistics for your AI assistant

**Ask questions about the Netherlands in plain language, and get answers from official government
statistics.**

This tool connects AI assistants such as **Claude**, **ChatGPT**, **VS Code Copilot** and **Cursor**
to [CBS](https://www.cbs.nl/en-gb) (Statistics Netherlands). CBS is the Dutch national statistics
office, and it publishes thousands of tables on population, housing, income, jobs, prices, health
and more.

Without this tool, your assistant has to guess or rely on old knowledge. With it, the assistant
looks up the **latest official figures** itself and tells you which CBS table it used.

---

## What can I ask?

Write the way you'd ask a colleague. You can ask in any language.

| You ask | The assistant finds |
|---|---|
| *"How many people live in Amsterdam?"* | **944,322** (August 2026), from the table *Bevolkingsontwikkeling; regio per maand* |
| *"What did an average house cost in Utrecht last year?"* | **€549,113** (2025), from *Bestaande koopwoningen; gemiddelde verkoopprijzen* |
| *"Compare unemployment in Rotterdam and The Hague over the last 5 years"* | A small table, year by year |
| *"How has inflation developed since 2020?"* | Monthly consumer price figures (CPI) |
| *"Which new CBS figures come out this week?"* | The CBS release calendar |

Other topics you can ask about: births and deaths, migration, household income, energy use, crime,
tourism, education, healthcare, traffic, bankruptcies, and regional figures down to municipality
and neighbourhood level.

> **Good to know:** CBS publishes its tables in Dutch. Your assistant translates them, so you can
> ask and get answers in English (or any other language).

---

## How to set it up

Choose the app you use. Each setup takes about 5 minutes and only has to be done once.

### Step 1: install the helper program "uv" (needed for options A–C)

This small program downloads and runs the tool for you. You need it for Claude Desktop, VS Code and
Cursor. If you use **ChatGPT or Claude in the browser**, skip to [Option D](#option-d-chatgpt-or-claude-in-your-web-browser).

**Mac:** open the **Terminal** app (press `⌘ + Space`, type *Terminal*, press Enter), paste this
line and press Enter:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:** open **PowerShell** (Start menu → type *PowerShell*), paste this line and press Enter:

```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

When it says it's done, **close the window**.

### Option A: Claude Desktop app

1. Open Claude Desktop and go to **Settings → Developer → Edit Config**.
   This opens a file called `claude_desktop_config.json`.
2. Replace everything in the file with the text below (if the file already has other servers in
   it, add only the `"cbs"` part):

   ```json
   {
     "mcpServers": {
       "cbs": {
         "command": "uvx",
         "args": ["cbs-mcp"]
       }
     }
   }
   ```

3. Save the file and **quit Claude completely**, then reopen it. On a Mac, use Claude → Quit;
   closing the window isn't enough.
4. Start a new chat and ask: *"How many people live in Amsterdam? Use the CBS tools."*

The first time, Claude asks for permission to use the CBS tools. Click **Allow**.

### Option B: VS Code (with GitHub Copilot)

1. Open your project folder in VS Code.
2. Create a folder named `.vscode` (if it doesn't exist) with a file named `mcp.json` inside it.
3. Paste this into the file and save:

   ```json
   {
     "servers": {
       "cbs": { "type": "stdio", "command": "uvx", "args": ["cbs-mcp"] }
     }
   }
   ```

4. A small **Start** button appears above the `"cbs"` line. Click it.
5. Open Copilot Chat, switch it to **Agent** mode, and ask your question.

### Option C: Cursor

1. Go to **Cursor Settings → MCP → Add new MCP server**. Or create a file
   `~/.cursor/mcp.json` (for all projects) or `.cursor/mcp.json` (for this project only).
2. Paste this and save:

   ```json
   {
     "mcpServers": {
       "cbs": { "type": "stdio", "command": "uvx", "args": ["cbs-mcp"] }
     }
   }
   ```

3. Check that **cbs** shows a green dot in the MCP settings, then ask your question in the chat.

### Option D: ChatGPT or Claude in your web browser

Websites can't start programs on your computer, so for this option the tool has to run on a
**server on the internet**. Someone technical (a colleague or your IT team) does that once; see
[Hosting it online](#hosting-it-online). They give you a web address that ends in `/mcp`, for
example `https://cbs.example.com/mcp`.

**Claude (claude.ai):**
1. Go to **Customize → Connectors**, click **+**, and choose **Add custom connector**.
2. Give it a name (*CBS*), paste the web address, and click **Add**.
3. In a chat, click **+** → **Connectors** and switch **CBS** on.

**ChatGPT:**
1. Go to **Settings → Apps → Advanced settings** and turn on **Developer mode**.
2. Click **Create** to add a connector. Name it *CBS*, paste the web address, and set
   authentication to **None**.
3. In a chat, enable the CBS connector and ask your question.

> OpenAI moves these menus around from time to time, and custom connectors aren't available on
> every ChatGPT plan. If you can't find the option, search the OpenAI help center for
> *"developer mode connectors"*.

<details>
<summary><b>Other apps (Claude Code, OpenCode, …)</b></summary>

**Claude Code** (terminal):

```
claude mcp add --transport stdio cbs -- uvx cbs-mcp
```

**OpenCode**: add to `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "cbs": { "type": "local", "command": ["uvx", "cbs-mcp"], "enabled": true }
  }
}
```

**Any app that supports MCP:** run the command `uvx cbs-mcp` (local), or connect to the web
address `https://<your-server>/mcp` (online).

</details>

---

## Tips for better answers

- **Mention the place and the time:** *"in Eindhoven"*, *"in 2024"*, *"the latest figures"*.
- **Ask for the source** if you want to check it: *"Which CBS table did you use?"* You can look it
  up on [opendata.cbs.nl](https://opendata.cbs.nl) or [cbs.nl](https://www.cbs.nl).
- **Ask for a comparison or a table:** *"Show this per province as a table"*.
- **Mind the definitions.** CBS measures things precisely: *"population on 1 January"* differs from
  *"average population over the year"*. Ask the assistant to explain the definition if it matters.

## Common questions

**The very first question is a bit slow.**
The first time, the tool downloads a list of all ~4,900 CBS tables so it can search them, which
takes a few seconds. Later questions are fast.

**The assistant says it can't find the CBS tools.**
- Restart the app completely after changing the settings.
- Make sure Step 1 finished. On a Mac, open Terminal and type `uvx --version`; it should print a
  version number.
- **Mac:** if it still doesn't work, the app may not find `uvx`. In Terminal, type `which uvx` and
  copy the result (something like `/Users/yourname/.local/bin/uvx`). Paste that full path in the
  settings file instead of just `"uvx"`.

**The assistant gives an answer, but not from CBS.**
Add *"use the CBS tools"* to your question.

**Are new CBS figures included?**
Yes. The tool always fetches figures directly from CBS. Its list of tables updates itself
every 6 hours, so brand-new tables become searchable the same day.

**Does this cost anything? Is my data shared?**
The tool is free, and CBS data is public ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)).
The tool sends only data requests to CBS. Your conversation stays between you and your AI
app, as usual.

**What can't it do?**
It only knows what CBS publishes, and doesn't cover other countries or other sources. Figures
are as recent as CBS has published them, usually a few weeks to months behind.

---

## Hosting it online

*For the technical person setting up Option D.*

```bash
docker build -t cbs-mcp .        # ~1 minute; includes the search index
docker run -p 8000:8000 cbs-mcp  # MCP endpoint: http://<host>:8000/mcp
```

Put it behind HTTPS (any cloud host such as Cloud Run, Fly.io or Railway, or a reverse proxy) and
share `https://<host>/mcp`. No login is needed because the data is public. Requests are rate-limited
(`CBS_RATE_LIMIT_RPS`, default 5 per second). To try it quickly without deploying, run
`uvx cbs-mcp --transport http` and expose it with `cloudflared tunnel --url http://localhost:8000`.

---

## For developers

<details>
<summary><b>Tools, architecture and configuration</b></summary>

### Tools

| Tool | Purpose |
|---|---|
| `search_datasets(query, catalog="CBS", include_discontinued=False, limit=10)` | Find tables by topic. Dutch keywords work best, and common English terms are translated. |
| `describe_dataset(dataset_id)` | A table's measures and dimensions, with code counts and the latest period. |
| `list_codes(dataset_id, dimension, query=None, limit=50)` | Code lookup, e.g. `Amsterdam → GM0363`. Use `"Measures"` for measure codes. |
| `get_observations(dataset_id, measures, filters, latest=False, limit=500)` | Values. `latest=true` returns the newest period with data. |
| `upcoming_releases(days=14, limit=30)` | The CBS release calendar. |

The output is compact text with `|` separators, and values that are the same in every row are
printed once under `fixed:`. A typical answer takes 3–4 calls of under 400 tokens each:

```
search_datasets("bevolking regio")                         → 37230ned Bevolkingsontwikkeling; regio per maand
list_codes("37230ned", "RegioS", "Amsterdam")              → GM0363|Amsterdam|Gemeenten per provincie
get_observations("37230ned", ["M000098"], {"RegioS": ["GM0363"]}, latest=true)
```

### Search index

The CBS OData API (`https://datasets.cbs.nl/odata/v1`) has no ranked search: `$search` is ignored,
and the catalog is Dutch-only. The server therefore keeps a **SQLite FTS5 index** of titles,
descriptions, and the measure and dimension names of active tables. Results are ranked by title
matches, then BM25, then status and recency.

- **First run:** search works after ~3 s, once the catalog is in. Measure and dimension names are
  indexed in the background (~45 s).
- **Sync every 6 h:** the server diffs each table's `Version` with CBS and refetches only the
  changes (~1 s when nothing changed). It removes deleted tables, invalidates cached metadata, and
  won't delete more than 20% of the catalog in one sync.
- **Manual sync:** `cbs-mcp sync [--full] [--no-details]`.

### Configuration

| Env var | Default | |
|---|---|---|
| `CBS_INDEX_PATH` | user cache dir | SQLite index location |
| `CBS_INDEX_REFRESH_HOURS` | `6` | Sync interval |
| `CBS_RATE_LIMIT_RPS` | `5` | HTTP mode: sustained requests per second (burst 20) |
| `CBS_HOST` / `PORT` | `127.0.0.1` / `8000` | HTTP bind address |
| `CBS_BASE_URL` | CBS OData v1 | API base URL |
| `CBS_LOG_LEVEL` | `INFO` | Logs go to stderr only |

### Development

```bash
uv sync
uv run pytest            # mocked HTTP (respx)
uv run pytest -m live    # end-to-end smoke test against the real API
npx @modelcontextprotocol/inspector uv run cbs-mcp
```

Put the server command first. The Inspector parses flags such as `uvx --from .` as its own options.
API findings are in [NOTES.md](NOTES.md).

**Before the PyPI release**, the `uvx cbs-mcp` commands above won't work yet. Use
`uvx --from git+https://github.com/<you>/cbs-mcp cbs-mcp`, or `uvx --from /path/to/checkout cbs-mcp`.

</details>

---

*Data: [CBS Statistics Netherlands](https://www.cbs.nl), licensed CC BY 4.0. This project is not
affiliated with CBS.*
