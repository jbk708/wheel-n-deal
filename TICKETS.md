# Tickets

One ticket per PR. Move completed tickets to **## Done**.

**Legacy (pre-rebuild):** tickets WND-001 – WND-047 (Jan 2026) built the old FastAPI + Celery + Redis + Postgres + Signal + Selenium stack: uv/ruff/ty tooling, Alembic migrations, JWT auth, per-user tracking via Signal (`!track`, `!list`, `!stop`, `!me`), and scrapers for Amazon, Walmart, Best Buy, Target, eBay, Sephora, DedCool, Costco plus a generic fallback (WND-047 is on the legacy `dev` branch only). The open backlog (WND-048 Sephora JS prices, a React web UI, a Signal bot framework) is superseded by the rebuild below. The legacy code (`backend/`) and the old `docs/TICKETS.md` are retired; their history remains in git.

---

## Open

_None._

---

## Done

### T13: Verify MiMo prices against the page
**Description:** A MiMo price that cannot be found on the fetched page must not count as a real observation, so a hallucinated or wrong-product price can never fire a price-drop alert and disarm the item.

**Deliverables:**
- [x] `learned.price_on_page`: plain search of the raw page (text, attributes, JSON-LD, scripts) for the price
- [x] `check._read_with_mimo`: when neither the learned-selector check nor the plain search finds MiMo's price, record `stale` with the last known price (no alert)
- [x] Tests: unverified price is stale (with and without history), price only in a script is still `ok` without a saved selector, `price_on_page` cases
- [x] README troubleshooting updated

**Dependencies:** T7, T8

---

### T12: Retire legacy services
**Description:** Delete the old stack now that the rebuild is live.

**Deliverables:**
- [x] Remove `backend/` (FastAPI, Celery, Redis, Postgres, Alembic, Signal, JWT/REST API, Prometheus, Selenium), `docker-compose.yml`, `run_docker.sh`, `setup_dev.sh`, `.pre-commit-config.yaml` if unused
- [x] Remove legacy-only deps and ruff per-file ignores; CI still green
- [x] Note in `CLAUDE.md` that the rebuild is complete (drop the "Rebuild status" section)

**Dependencies:** T11

---

### T11: README and docs rewrite
**Description:** Document the rebuilt service for a new reader: what it does, config, run, deploy.

**Deliverables:**
- [x] `README.md`: purpose, politeness/no-evasion stance, config reference, local run, deploy and rollback, troubleshooting (blocked sites, MiMo down)
- [x] Remove stale `docs/ARCHITECTURE.md`, `docs/CONTRIBUTING.md`, `docs/DEPLOYMENT-DEBIAN.md`
- [x] Agent `## Memory` sections updated with deploy/health facts learned in T10

**Dependencies:** T10

---

### T10: Container and deploy script
**Description:** Package the service as one small container and deploy it to duckling2 with the house git-archive release script.

**Deliverables:**
- [x] `Dockerfile` (python:3.12-slim + uv, non-root uid 1000, no browser), healthcheck on a heartbeat file in `/data`
- [x] `compose.yaml`: host networking, no published ports, `mem_limit: 512m`, `env_file: .env`, `./config.yaml` and `./data` mounted, `restart: unless-stopped`
- [x] `scripts/deploy.sh <host> [<tag>]`: git archive over ssh into `~/wheel-n-deal/releases/<tag>`, `compose up --build --wait`, repoint `current` symlink on health; rollback = deploy an older tag; never touches remote `.env`/`config.yaml`/`data/`
- [x] shellcheck clean; CI runs shellcheck and a `docker build`

**Dependencies:** T9

---

### T9: Deal verdict
**Description:** On a new below-target alert, optionally ask MiMo once whether it is a real deal and include the verdict in the notification.

**Deliverables:**
- [x] One MiMo call per alert with the item's own price history, list price, condition, and variant: flags inflated list price, refurbished/used, membership-only pricing
- [x] Verdict appended to the ntfy message; MiMo down → alert sent without a verdict
- [x] Tests: verdict included, MiMo failure still alerts, called at most once per alert

**Dependencies:** T8

---

### T8: Learned-selector cache
**Description:** Remember where MiMo's evidence was found so later runs extract without calling MiMo until the page layout breaks.

**Deliverables:**
- [x] After a MiMo success, derive a CSS path or JSON-LD key that locates the `evidence` text and validate it against the live page before saving
- [x] Store selectors per item (or per site) in SQLite; try them right after structured extraction and before MiMo
- [x] Selector fails → drop it and fall back to MiMo once
- [x] Tests: derivation, validation rejects non-matching selectors, cache hit skips MiMo

**Dependencies:** T7

---

### T7: MiMo extraction fallback
**Description:** When structured extraction fails on a non-blocked page, ask MiMo to extract the price from a trimmed page view.

**Deliverables:**
- [x] `llm.py`: POST `{llm.base_url}/chat/completions`, model `mimo-v2.6-flash`, `Authorization: Bearer $LLM_API_KEY`, custom `User-Agent` (not `OpenAI/…`, which Cloudflare 403s), ≤90 s timeout, one request at a time
- [x] Page trimmer: title + H1 always kept, JSON-LD, product meta, main text, capped at 12k chars
- [x] Strict JSON output `{price, currency, in_stock, variant, condition, list_price, blocked, evidence}` validated with pydantic; invalid → treated as failure
- [x] MiMo unreachable/invalid → keep last known price, mark observation `stale`, never crash
- [x] Tests with respx (success, timeout, bad JSON, trimming keeps title/H1)

**Dependencies:** T6

---

### T6: ntfy alerts and heartbeat
**Description:** Send one ntfy alert per drop below target and ping an optional heartbeat after each successful run.

**Deliverables:**
- [x] `notify.py`: POST `{ntfy.url}/` JSON (`topic`, `title`, `message`, `click` = product URL, `actions` `[{"action":"view","label":"Open","url":…}]`, `tags`, `priority`), header `Authorization: Bearer $NTFY_TOKEN`
- [x] Alert state machine: fire once when price goes below target; re-arm only after price recovers above target; no repeats
- [x] Optional summary notice for items newly `blocked`
- [x] `heartbeat.py`: GET `heartbeat_url` (Uptime Kuma push) after each successful run; warn and continue on failure; never log the URL
- [x] Tests with respx for payload shape, auth header, single-fire/re-arm, heartbeat failure tolerance

**Dependencies:** T5

---

### T5: Scheduler and run loop with per-site politeness
**Description:** Run a long-lived asyncio scheduler that checks each watched item on a jittered per-site schedule and records results.

**Deliverables:**
- [x] `main.py`: load config, open store, loop forever; `wheel-n-deal` entrypoint
- [x] Per-site (registrable domain) minimum interval of several hours, random jitter, one in-flight request per site
- [x] Each check: fetch → extract → store observation; blocked → `status=blocked`, logged, backed off to the next normal slot
- [x] Log one summary line per run (checked / ok / blocked / failed)
- [x] Tests for due-item selection, per-site serialization, and jitter bounds (fake clock)

**Dependencies:** T4

---

### T4: Structured price extraction
**Description:** Extract price, currency, and stock from structured data before anything else, porting the useful legacy helpers.

**Deliverables:**
- [x] `extract.py` (pure functions on HTML/JSON): JSON-LD `Product` with `offers`, JSON-LD `ProductGroup` / `hasVariant` (Sephora), product meta tags (`og:price:amount`, `product:price:amount`, itemprop)
- [x] Shopify: detect store and read the `/products/<handle>.js` endpoint
- [x] Port still-useful per-site parsers from legacy `origin/dev` `backend/services/scraper.py` (Amazon, Costco, etc.) as pure helpers (BeautifulSoup is fine; no Selenium)
- [x] Result records which path found the price (JSON-LD key / meta name / selector) for the later selector cache
- [x] Saved HTML fixtures (scrubbed of personal data) and tests per extraction path

**Dependencies:** T3

---

### T3: Polite HTTP fetch layer
**Description:** Fetch product pages with plain httpx and an honest User-Agent, resolve short links, and classify blocked responses.

**Deliverables:**
- [x] `fetch.py`: one shared `httpx.AsyncClient`, UA `wheel-n-deal/<version> (+personal price tracker)` (version from package metadata), sane timeout, follows redirects
- [x] Amazon short links (`a.co`, `amzn.to`) resolved to the canonical product URL before parsing
- [x] Costco new `/p/` URLs accepted
- [x] Block detection: 403/429/503, bot-wall / CAPTCHA markers, or empty body → `blocked` result (no retry loop)
- [x] No bot evasion: no stealth, rotating UAs, proxies, or CAPTCHA solving; no headless browser
- [x] Tests with respx (redirect resolution, blocked classification)

**Dependencies:** T2

---

### T2: Scaffold package, YAML config, and SQLite state
**Description:** Create the root `src/wheel_n_deal/` package with pydantic config loaded from YAML and a SQLite store for price history and alert state.

**Deliverables:**
- [x] Root `pyproject.toml` replaced by the house layout (hatchling, `src/wheel_n_deal`, pinned httpx/pydantic/pyyaml, dev: pytest, pytest-asyncio, respx, ruff; script `wheel-n-deal`); `uv.lock` regenerated
- [x] `config.py`: watch list (`url`, `name`, `target_price`, optional `notes`), `ntfy` (`url`, `topic`), `llm` (`base_url`, `model`), optional `heartbeat_url`, politeness settings (per-site min interval hours, jitter); secrets only from env (`LLM_API_KEY`, `NTFY_TOKEN`)
- [x] `config.example.yaml` with placeholder URLs only; `.env.example` rewritten to just `LLM_API_KEY=` / `NTFY_TOKEN=`
- [x] `store.py` (sqlite3, path `/data/state.db` by default): items, price observations (price, currency, in_stock, status `ok|blocked|stale|error`, checked_at), per-item alert state (armed/fired)
- [x] Tests for config validation and store CRUD
- [x] CI switched to root gates (`uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest`); legacy `backend/` excluded from ruff/pytest

**Dependencies:** T1

---

### T1: Fix CI and repo hygiene
**Description:** Make CI run on Python 3.12 so PRs can go green, and stop tracking databases and other private files in this public repo.

**Deliverables:**
- [x] `.github/workflows/ci.yml`: Python 3.12, triggers on `push`/`pull_request` to `main` only, drop the Docker build job (legacy 2 GB image)
- [x] `.gitignore`: add `*.db`, `*.sqlite*`, `data/`, `config.yaml`, `.env*` (keep `!.env.example`), secrets patterns from the template
- [x] `.dockerignore`: `.git`, `.venv`, `.env*`, `*.db`, `data/`, `config.yaml`, caches, `tests/`
- [x] `git rm --cached backend/wheel_n_deal.db` (normal commit; no history rewrite or force-push — that needs separate user approval)
- [x] CI green on the PR

**Dependencies:** none

---

### T0: Migrate agent workflow and write rebuild backlog
**Description:** Adopt the new-project-template workflow and plan the rebuild.

**Deliverables:**
- [x] Root `CLAUDE.md` merging template principles/workflow with project specifics
- [x] Root `TICKETS.md` with legacy summary and rebuild backlog T1–T12
- [x] `.claude/agents/` from the template with placeholders filled
- [x] Retire `docs/TICKETS.md`
