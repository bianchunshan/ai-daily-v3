# AGENTS.md

## Cursor Cloud specific instructions

This repo is `ai-daily-v3` ("前沿科技日报 / AI Daily"): a static news website plus two
Vercel serverless functions and Python data-pipeline scripts. See `README.md` for the
full product/architecture overview and the list of files.

### Key facts (non-obvious)

- **No dependency manifests exist.** There is no `package.json`, `requirements.txt`,
  lockfile, Dockerfile, or Makefile. The Python scripts use the **standard library only**
  and the Node serverless functions have **no npm dependencies**. There is nothing to
  `npm install` / `pip install` and there is no build step, no linter, and no test suite.
- Node and Python 3 are already available in the environment; that is all the app needs.

### Running the app (dev)

- **Frontend (static site) — always works, no auth/keys:** from the repo root run
  `python3 -m http.server 8000`, then open `http://localhost:8000/index.html`.
  News content is loaded from the committed `news_data_latest.js`, so the site renders
  real data offline.
- **Full app including `/api/*` — intended tool is `vercel dev`, but it requires auth.**
  `vercel dev` / `npx vercel dev` fails headless with "No existing credentials found"
  unless a `VERCEL_TOKEN` is provided. In non-interactive mode it also needs an explicit
  team scope, otherwise it aborts with `missing_scope`. Working invocation:
  `npx vercel dev --listen 3000 --token "$VERCEL_TOKEN" --scope <team-slug> --yes`
  (first run auto-creates/links a Vercel project and writes a gitignored `.vercel/`).
  The frontend calls **relative** `/api/...` paths, so pages and functions must be served
  from the **same origin**.
- **Running `/api/*` locally without a Vercel token:** the functions are plain Node
  CommonJS `(req, res)` handlers (`api/quote.js`, `api/chat.js`). You can mount them in a
  tiny local Node HTTP server (parse the query string into `req.query`, add
  `res.status().json()`) and, if you want the browser flow, also serve the repo's static
  files from that same server so `/api/*` and the pages share one origin.

### Serverless function notes

- `api/quote.js` (live stock quotes, proxies Sina Finance `hq.sinajs.cn`): **needs no key**
  and works as long as outbound HTTPS is available. Test:
  `curl 'http://localhost:<port>/api/quote?symbol=NVDA,0700.HK,600519.SH'`.
- `api/chat.js` ("Ask AI"): requires an LLM key. With no key it intentionally returns
  HTTP 500 `{"error":"server missing QWEN_KEY"}` (or `MOONSHOT_API_KEY` when
  `CHAT_PROVIDER=kimi`). Set `QWEN_KEY`, or `KIMI_KEY`/`MOONSHOT_API_KEY`, to enable it.

### Data pipeline (optional, batch job — not a server)

- `python3 enrich_news.py` scrapes RSS then calls an LLM to regenerate
  `news_data_latest.js`. It requires an LLM key (`KIMI_KEY` or `QWEN_KEY`). The site
  already ships with committed data, so you do **not** need to run this to view/dev the app.
