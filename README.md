# wheel-n-deal

A personal price tracker. You list products in `config.yaml` with a target price. One long-lived container checks each product every few hours over plain HTTP, records the price in SQLite, and sends an [ntfy](https://ntfy.sh) notification when a price drops below your target.

```
config.yaml watch list
  → polite fetch (httpx, honest User-Agent, one request at a time per site)
  → structured extraction (JSON-LD, Shopify .js, meta tags, per-site selectors)
  → learned selector (saved from an earlier LLM answer)
  → LLM fallback (only when everything above found no price)
  → SQLite history in /data/state.db
  → ntfy alert (once per drop below target), optional deal verdict, heartbeat ping
```

## Politeness, and no bot evasion

wheel-n-deal behaves like a well-mannered visitor and does not try to get past a site that refuses it.

- Every request sends the User-Agent `wheel-n-deal/<version> (+personal price tracker)`. It is never rotated or spoofed.
- Each site (registrable domain) is checked at most once per `politeness.min_interval_hours` (default 6), with random jitter, and only one request runs at a time per site.
- There are no stealth plugins, headless browsers, CAPTCHA solvers, or proxies.
- When a site answers with 403, 429 or 503, serves a bot-wall or CAPTCHA page, or returns an empty body, the check is recorded as `status=blocked` and retried at the next normal slot, not sooner. Newly blocked items are reported in one ntfy summary.

Some large retailers will block it. That is expected, and the troubleshooting section below covers it.

## How a price is found

1. **Fetch.** Amazon short links (`a.co`, `amzn.to`) are resolved to the canonical `/dp/<ASIN>` URL first. Redirects are followed.
2. **Structured data.** JSON-LD `Product` offers, JSON-LD `ProductGroup` / `hasVariant` (the variant is chosen from `skuId`, `sku` or `variant` in the URL), the Shopify `/products/<handle>.js` endpoint, and price meta tags (`product:price:amount`, `og:price:amount`, `itemprop="price"`).
3. **Per-site selectors** for Amazon, Walmart, Best Buy, Target, eBay, Sephora and Costco.
4. **Learned selector.** A CSS path or JSON-LD key saved from an earlier LLM answer. It is checked against the live page before it is saved. If it stops matching, it is dropped and the LLM is asked once more.
5. **LLM fallback.** If nothing above worked, a trimmed view of the page is sent to an OpenAI-compatible endpoint (default model `mimo-v2.6-flash`). The view keeps the title and H1, JSON-LD, product meta tags and main text, up to 12k characters. The model must return strict JSON (`price`, `currency`, `in_stock`, `variant`, `condition`, `list_price`, `blocked`, `evidence`), and any other answer is treated as a failure. Requests are made one at a time, with a 90 s timeout.

When a price falls below target, the LLM is asked once, optionally, whether the deal is real. It checks the item's own price history and looks for an inflated list price, refurbished or used stock, and membership-only pricing. The verdict is added to the notification. If the LLM is unavailable, the alert is sent without a verdict.

Alerts fire **once** per drop below target. They re-arm only after the price goes back above target. If ntfy cannot be reached, the alert stays armed and is retried at the next check.

## Configuration

Two files sit next to the container. Neither is committed.

**`config.yaml`** holds settings that are not secret. Copy it from [`config.example.yaml`](config.example.yaml):

| Key | Required | Default | Meaning |
|---|---|---|---|
| `watch[].url` | yes | | Product page URL (`http(s)://`). URLs must be unique. |
| `watch[].name` | yes | | Name used in logs and notifications. |
| `watch[].target_price` | yes | | Alert when the price drops below this (> 0). |
| `watch[].notes` | no | | Free text, passed to the deal verdict (e.g. "any colour is fine"). |
| `ntfy.url` | yes | | ntfy server base URL. |
| `ntfy.topic` | no | `deals` | Topic to publish to. |
| `llm.base_url` | yes | | OpenAI-compatible base URL. `/chat/completions` is appended. |
| `llm.model` | no | `mimo-v2.6-flash` | Model name. |
| `politeness.min_interval_hours` | no | `6` | Minimum time between checks of the same site. |
| `politeness.jitter_minutes` | no | `30` | Random delay added to each site's next check. |
| `data_dir` | no | `/data` | Holds `state.db` and the `heartbeat` file. Keep `/data` in the container. |
| `heartbeat_url` | no | | Uptime Kuma push URL, fetched with GET after each successful run. It is never logged. |

Unknown keys are rejected.

**`.env`** holds secrets. Copy it from [`.env.example`](.env.example):

| Variable | Used for |
|---|---|
| `LLM_API_KEY` | `Authorization: Bearer` for the LLM endpoint. If it is unset, the LLM steps are skipped. |
| `NTFY_TOKEN` | `Authorization: Bearer` for ntfy. |

## Run locally

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
cp config.example.yaml config.yaml   # edit; set data_dir: ./data for a local run
cp .env.example .env                 # fill in
mkdir -p data
set -a; . ./.env; set +a
uv run wheel-n-deal --config config.yaml
```

Development gates (CI runs the same ones):

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
shellcheck scripts/*.sh
```

## Deploy

The service runs as one container (`compose.yaml`). It uses host networking with no published ports, `mem_limit: 512m`, runs as uid 1000, and has `./config.yaml` (read-only) and `./data` bind-mounted.

One-time setup on the host, under `~/wheel-n-deal/`: create `config.yaml`, `.env`, and `data/`, all owned by uid 1000. If they are missing, Docker creates the bind mounts as root, and a missing `config.yaml` becomes a directory.

Release and deploy from a clean checkout of `main`:

```sh
git tag -a v2.0.0 -m v2.0.0 && git push origin v2.0.0
scripts/deploy.sh <ssh-host> v2.0.0
```

`deploy.sh` streams `git archive` of the tag into `~/wheel-n-deal/releases/<tag>/` and links in the shared `config.yaml`, `.env` and `data/`. It then runs `docker compose -p wheel-n-deal up -d --build --wait` and repoints the `current` symlink only after the container reports healthy within 60 s. It never writes `.env`, `config.yaml` or `data/`.

**Roll back** by deploying an older tag: `scripts/deploy.sh <ssh-host> v1.9.0`. The SQLite state in `data/` is shared by all releases.

**Health.** The app touches `/data/heartbeat` every 30 s. The Docker `HEALTHCHECK` fails if that file is more than 3 minutes old. This shows the event loop is alive even during the hours between checks.

```sh
ssh <ssh-host> 'cd ~/wheel-n-deal/current && docker compose -p wheel-n-deal ps'
ssh <ssh-host> 'cd ~/wheel-n-deal/current && docker compose -p wheel-n-deal logs --tail 100'
```

Each run logs one summary line (`checked / ok / blocked / failed`), plus one line per item.

## Troubleshooting

**A site shows `blocked`.** The site refused a polite request. It may have returned 403, 429 or 503, or served a bot wall or CAPTCHA page. This is by design: wheel-n-deal will not evade it. Your options are:
- Check whether the product is also sold on a store that serves structured data, such as a brand's own Shopify store, and watch that URL instead.
- Remove the item, or accept that it updates only when the site lets it through.

Do not lower `min_interval_hours` to "try harder". Checking more often makes blocks more likely.

**Observations are `stale`.** The page was fetched, but structured extraction failed and the LLM could not be reached, gave an invalid answer, or reported a price that does not appear anywhere on the page (no alert is sent for an unverified price). The last known price is kept and marked `stale`, and nothing crashes. The LLM endpoint can be down for hours. Checks resume normally once it is back. If an item is stale on every run, look for `MiMo skipped: LLM_API_KEY is not set`, `not on page`, or LLM HTTP errors in the logs.

**Status is `error`.** The fetch failed (DNS, timeout, connection), or the page loaded but no price was found anywhere. If that happens on every run for one item, the URL is probably wrong or the product is gone.

**No notifications arrive.** Check that `ntfy.url` and `ntfy.topic` are correct, that `NTFY_TOKEN` is set in `.env`, and look for `ntfy publish failed` in the logs. A price that is already below target when you add an item alerts once. Later checks stay quiet until the price recovers above target and drops again.

**Container unhealthy.** The heartbeat file is not being touched. Usually `data/` is not writable by uid 1000, or `data_dir` in `config.yaml` is not `/data`.

**Inspecting state.**

```sh
sqlite3 -readonly ~/wheel-n-deal/data/state.db \
  "SELECT i.name, o.checked_at, o.status, o.price FROM observations o JOIN items i ON i.id = o.item_id ORDER BY o.checked_at DESC LIMIT 20"
```

## License

GPL-3.0
