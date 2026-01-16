# Tickets

## Active

| Ticket | Description | Status | Branch |
|--------|-------------|--------|--------|
| | | | |

## Backlog

| Ticket | Description | Priority |
|--------|-------------|----------|
| WND-003 | Fix CORS to restrict allowed origins | High |
| WND-004 | Consolidate duplicate model definitions | Medium |
| WND-005 | Fix deprecated SQLAlchemy import in models/database.py | Medium |
| WND-006 | Replace print() with logger in price_check.py | Medium |
| WND-007 | Standardize price type handling (string vs float) | Medium |
| WND-008 | Re-enable and fix skipped integration tests | Medium |
| WND-009 | Use settings.METRICS_PORT instead of hardcoded 8001 | Low |
| WND-010 | Add database connection pooling configuration | Low |
| WND-014 | Fix type errors reported by ty (4 errors) | Medium |
| WND-015 | Replace deprecated datetime.utcnow() with timezone-aware | Low |
| WND-016 | Migrate to Python 3.12+ | Low |
| WND-017 | Consolidate duplicate test files (test_tracker.py, test_api_endpoints.py) | Low |
| WND-018 | Extract helper functions in tracker.py to reduce duplication | Low |
| WND-019 | Remove unused rate_limit wrapper function in security.py | Low |

## Completed

| Ticket | Description | Completed | PR |
|--------|-------------|-----------|-----|
| WND-002 | Wire security routes to API (auth, rate limiting) | 2026-01-16 | #8 |
| WND-001 | Set up Alembic migrations | 2026-01-16 | #7 |
| WND-013 | Add ty for type checking | 2026-01-16 | #6 |
| WND-012 | Configure ruff as sole linter/formatter (remove pylint) | 2026-01-16 | #5 |
| WND-011 | Migrate from Poetry to uv for package/env management | 2026-01-16 | #2 |
