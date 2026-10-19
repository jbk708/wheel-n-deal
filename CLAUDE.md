# wheel-n-deal

Personal price tracker: a watch list in SQLite (seeded from `config.yaml`, edited through a loopback-only HTTP API) → polite fetch with browser headers (headless Chromium retry when blocked) → structured price extraction (MiMo fallback only when that fails) → SQLite history → ntfy alert when a price drops below target. One long-lived container with an internal asyncio scheduler. See `README.md`.

**This repo is PUBLIC.** Never commit secrets, `.env`, `*.db`, real phone numbers, hostnames of private services, or personal data.

## Stack

House pattern, same as `release-triage` / `crosspoint-sync`: Python 3.12+ + uv, `src/wheel_n_deal/`, httpx, Playwright (Chromium only, pinned), pydantic config loaded from YAML, SQLite in `/data`, pytest (+ respx), ruff check + format, `Dockerfile` + `compose.yaml`, `scripts/deploy.sh` (git-archive over ssh into `releases/<tag>` + `current` symlink + health wait), semver tags. The pre-rebuild stack (FastAPI + Celery + Redis + Postgres + signal-cli + Selenium) has been retired; its history remains in git.

Hard rules for this project:
- **Fetching**: shop requests look like desktop Chrome (Chrome UA plus matching `Accept*`, `sec-ch-ua*`, `sec-fetch-*` headers; keep `CHROME_MAJOR` in `fetch.py` in step with the Chromium bundled by the pinned Playwright). A blocked page (403/429/503/bot wall/empty) gets exactly one headless Chromium retry; if that is refused too, the check is `status=blocked` and waits for the next normal slot. No CAPTCHA solving or solver services. Our own services (MiMo, ntfy, heartbeat) get the app UA `wheel-n-deal/<version> (+personal price tracker)`.
- **Politeness**: per-site minimum interval (hours), jittered schedule, one request at a time per site.
- **MiMo is optional infrastructure**: it can be down for hours. Every MiMo call degrades gracefully (keep last known price, mark stale, alert anyway); nothing crashes because the LLM is unreachable.

## Principles

### KISS — Keep It Simple
- Write the smallest code that solves the problem.
- No speculative features, flags, abstractions, or fallbacks.
- Three similar lines beat a premature abstraction.
- Delete unused code; don't preserve it "just in case."

### CRUD — One Job Per Unit
- Each function does one thing: **C**reate, **R**ead, **U**pdate, or **D**elete.
- No mixed read+write side effects in a single path.
- Pure where possible; push I/O to the boundaries.
- State changes are explicit and localized.

### Style
- Code speaks for itself — no comments explaining *what*.
- Comment only non-obvious *why* (constraints, invariants, gotchas).
- Names carry meaning. If a comment is needed, try a better name first.

### Secrets
- **Never** paste auth tokens, API keys, passwords, private keys, session cookies, OAuth/JWT tokens, `.env` contents, or any post-auth credential into the chat.
- If a secret is needed, reference it by name (`LLM_API_KEY`, `NTFY_TOKEN`) and load it from the environment or a gitignored `.env` file.
- If a secret is accidentally shared, treat it as compromised: rotate immediately, then scrub history (history rewrites and force-pushes need the user's explicit approval).
- Do not commit secrets. `.env`, `*.pem`, `*.key`, `*.db`, `config.yaml`, and `data/` are gitignored.
- Never log the heartbeat URL or any token.

## Agents

A six-agent pipeline lives in `.claude/agents/` — see [`.claude/agents/README.md`](.claude/agents/README.md) for the roster, flow, and trigger threshold.

Start with `team-lead` for any change broader than a single-line fix. It dispatches Planner ⇄ SWE to reconcile a plan, blocks on your explicit go-ahead, then runs SWE → QA → Deployer.

The agents' placeholders are filled in for the rebuilt stack (uv, pytest, ruff, shellcheck, `scripts/deploy.sh` to duckling2 over Tailscale). Grow each agent's `## Memory` section as the project teaches you things.

## Commands

From the repo root:

```sh
uv sync                          # install
uv run pytest                    # tests
uv run ruff check .              # lint
uv run ruff format --check .     # format check (uv run ruff format . to fix)
shellcheck scripts/*.sh          # deploy script
uv run wheel-n-deal              # run the scheduler locally (needs config.yaml + .env)
```

## Workflow (One Ticket Per PR) — GitHub edition

Repo: `jbk708/wheel-n-deal` on GitHub. Default branch `main`; every PR targets `main` (the legacy `dev` branch is retired). **Auto-merge is disabled** on this repo — do not change repo settings.

Work in a separate worktree (e.g. `git worktree add ../wheel-n-deal-rebuild origin/main`), never in the user's primary checkout, which may hold uncommitted local changes.

1. **Branch** — `git checkout -b t{N}-short-description origin/main`
2. **Plan** — Read ticket, outline types/functions/tests, get approval.
3. **Tests** — Write failing tests first; define expected behavior.
4. **Implement** — Minimum code to pass tests.
5. **Simplify** — Lint, format, all tests green, no warnings.
6. **Done** — move the ticket to `## Done` in `TICKETS.md` in the same PR, deliverables checked.
7. **PR** — `git push -u origin t{N}-short-description`, then `gh pr create --base main --title "T{N}: {Title}" --body '...'`.
8. **CI** — `gh pr checks <n> --watch`; fix and push until green.
9. **Merge** — `gh pr merge <n> --squash --delete-branch` (only on green). Then `git checkout main && git pull --ff-only`.

Bookkeeping-only changes (ticket edits, workflow docs) go in `T0: …` PRs.

Releases: tag `main` with semver `vX.Y.Z` (`git tag -a vX.Y.Z -m vX.Y.Z && git push origin vX.Y.Z`), then `scripts/deploy.sh duckling2@100.77.39.5 vX.Y.Z`.

## Attribution

No AI attribution anywhere: no `Co-Authored-By: Claude…`, no `Claude-Session:` trailer, no "Generated with Claude Code" — not in commits, squash messages, PR titles or bodies.

## Formats

### Commit
```
T{N}: {verb} {what changed}
```

### PR Title
```
T{N}: {Ticket title}
```

### PR Body
Use **single quotes** around `gh pr create --body` content to avoid shell interpolation. Keep it short: what changed, how it was tested.
