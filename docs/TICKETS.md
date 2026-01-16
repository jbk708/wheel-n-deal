# Tickets

## Active

| Ticket | Description | Status | Branch |
|--------|-------------|--------|--------|

## Backlog

| Ticket | Description | Priority |
|--------|-------------|----------|
| **Phase 1: User Identity Foundation** | | |
| WND-027 | Update tracker API to filter products by authenticated user | High |
| **Phase 2: Command Prefix & Per-User Tracking** | | |
| WND-028 | Parse sender phone/username from signal-cli JSON output | High |
| WND-029 | Auto-create User record for new Signal senders | High |
| WND-030 | Require `!` prefix for commands (!track, !list, !stop, !help, !status) | High |
| WND-031 | Scope all commands to sender's own product list | High |
| WND-032 | Add !me command to show user's Signal identity/stats | Medium |
| **Phase 3: React Web Interface** | | |
| WND-033 | Initialize React frontend with Vite, TailwindCSS, React Router | Medium |
| WND-034 | Auth pages - login, register, password reset | Medium |
| WND-035 | Dashboard - list tracked products with current/target prices | Medium |
| WND-036 | Add product form with URL validation and retailer detection | Medium |
| WND-037 | Price history chart per product (recharts or chart.js) | Medium |
| WND-038 | Product detail page with edit target price, delete | Medium |
| WND-039 | Settings page - notification preferences, account management | Low |
| **Phase 4: Signal Bot Framework (Monorepo)** | | |
| WND-040 | Restructure repo: packages/signal-bot-core, packages/wheel-n-deal | Low |
| WND-041 | Extract SignalBot base class with message parsing, routing | Low |
| WND-042 | Define command plugin interface (register, execute, help text) | Low |
| WND-043 | Refactor wheel-n-deal as signal-bot-core plugin | Low |
| WND-044 | Add example plugin template for new bot functionality | Low |

## Completed

| Ticket | Description | Completed | PR |
|--------|-------------|-----------|-----|
| WND-026 | Implement user registration/login endpoints (replace fake_users_db) | 2026-01-16 | #30 |
| WND-025 | Add user_id FK to Product, enable per-user tracking | 2026-01-16 | #29 |
| WND-024 | Add User model with Signal phone, username, created_at | 2026-01-16 | #28 |
| WND-023 | Top-level file cleanup and setup script updates | 2026-01-16 | #25 |
| WND-021 | Codebase consolidation and simplification review | 2026-01-16 | #23 |
| WND-020 | Update setup instructions | 2026-01-16 | #22 |
| WND-019 | Remove unused rate_limit wrapper function | 2026-01-16 | #21 |
| WND-018 | Extract helper functions in tracker.py | 2026-01-16 | #20 |
| WND-017 | Consolidate duplicate test files | 2026-01-16 | #19 |
| WND-016 | Migrate to Python 3.12+ | 2026-01-16 | #18 |
| WND-010 | Add database connection pooling configuration | 2026-01-16 | #17 |
| WND-009 | Use settings.METRICS_PORT instead of hardcoded 8001 | 2026-01-16 | #16 |
| WND-022 | Review and fix deprecation warnings for all packages | 2026-01-16 | #15 |
| WND-015 | Replace deprecated datetime.utcnow() with timezone-aware | 2026-01-16 | #15 |
| WND-014 | Fix type errors reported by ty (4 errors) | 2026-01-16 | #14 |
| WND-008 | Re-enable and fix skipped integration tests | 2026-01-16 | #13 |
| WND-007 | Standardize price type handling (string vs float) | 2026-01-16 | #12 |
| WND-006 | Replace print() with logger in price_check.py | 2026-01-16 | #11 |
| WND-004 | Consolidate duplicate model definitions | 2026-01-16 | #10 |
| WND-003 | Fix CORS to restrict allowed origins | 2026-01-16 | #9 |
| WND-002 | Wire security routes to API (auth, rate limiting) | 2026-01-16 | #8 |
| WND-001 | Set up Alembic migrations | 2026-01-16 | #7 |
| WND-013 | Add ty for type checking | 2026-01-16 | #6 |
| WND-012 | Configure ruff as sole linter/formatter (remove pylint) | 2026-01-16 | #5 |
| WND-011 | Migrate from Poetry to uv for package/env management | 2026-01-16 | #2 |
