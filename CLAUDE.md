# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Branch Strategy

- **main**: Production-ready code only
- **dev**: Integration branch for active development (permanent)
- **feature branches**: Created from `dev`, merged back to `dev`

## Ticket Development Workflow

Follow this workflow for all ticket development:

1. **Branch**: Create a feature branch from `dev`
2. **Stub**: Create function/class stubs with signatures and docstrings
3. **Write Tests**: Write tests against the stubs (tests will fail initially)
4. **Implement**: Fill in the implementation
5. **Verify**: Run tests to confirm implementation is correct
6. **Pre-PR Checks**: Before creating a PR, run these commands from `backend/`:
   ```bash
   uv run ruff check . --fix   # Fix linting issues
   uv run ruff format .        # Format code
   uv run ty check             # Type check
   uv run pytest               # Run tests
   ```
7. **Simplify**: Run code simplifier to clean up implementation
8. **Update Ticket**: Mark ticket complete in `TICKETS.md`

### Conventions

**Branch naming**: `{prefix}-{ticket}-{name}`
- Prefixes: `feat`, `fix`, `refactor`, `docs`, `test`
- Example: `feat-WND-001-price-alerts`

**Commit messages**: `{PREFIX}-{ticket}: {description}`
- Example: `FEAT-WND-001: Stub out PriceAlertService`
- Example: `FEAT-WND-001: Add tests for price threshold logic`
- Example: `FEAT-WND-001: Implement price alert notifications`

### Principles

- **Test-driven**: Write tests before implementation
- **Self-documenting**: Use clear naming and type hints; code should explain itself
- **Minimal inline comments**: Only comment non-obvious logic; prefer better naming over comments

### Ticket Tracking

See `TICKETS.md` for active and completed tickets.

## Project Overview

Wheel-n-Deal is a price tracking and deal notification service that monitors product prices across e-commerce websites (Amazon, Walmart, Best Buy, Target, eBay) and sends notifications via Signal when prices drop.

## Development Commands

All commands should be run from the `backend/` directory:

```bash
# Install dependencies
uv sync

# Run API server (development)
uv run uvicorn main:app --reload

# Run Celery worker (requires Redis)
uv run celery -A celery_app worker --loglevel=info

# Run tests with coverage
uv run pytest

# Run a single test file
uv run pytest tests/test_scraper.py

# Run a single test
uv run pytest tests/test_scraper.py::test_function_name -v

# Linting and formatting
uv run ruff check .
uv run ruff check . --fix
uv run ruff format .

# Type checking
uv run ty check

# Database migrations
uv run alembic upgrade head        # Apply all migrations
uv run alembic downgrade -1        # Rollback one migration
uv run alembic revision --autogenerate -m "Description"  # Create new migration

# Add a dependency
uv add <package>

# Add a dev dependency
uv add --group dev <package>
```

## Docker Commands

From the project root:

```bash
./run_docker.sh start    # Start all services
./run_docker.sh stop     # Stop all services
./run_docker.sh restart  # Restart all services
./run_docker.sh logs     # View logs
```

## Architecture

### Backend Components (`backend/`)

- **main.py**: FastAPI application entry point. Initializes database, starts Signal listener thread, and Prometheus metrics server on port 8001.

- **celery_app.py**: Celery configuration using Redis as broker. Tasks are auto-discovered from `tasks/` directory.

- **config.py**: Pydantic settings class (`Settings`) that loads configuration from environment variables and `.env` file.

- **models.py** + **models/database.py**: SQLAlchemy models and database initialization. Uses SQLite by default, PostgreSQL in production.

### Services (`backend/services/`)

- **scraper.py**: Extracts product info (price, title) from e-commerce sites using BeautifulSoup and Selenium
- **listener.py**: Signal group chat listener that processes user commands
- **notification.py**: Sends price drop alerts via Signal

### Tasks (`backend/tasks/`)

- **price_check.py**: Celery task for scheduled price checking

### Routers (`backend/routers/`)

- **auth.py**: Authentication endpoints - login, token refresh (mounted at `/api/v1/auth`)
- **tracker.py**: API endpoints for product tracking (mounted at `/api/v1/tracker`)

### Utils (`backend/utils/`)

- **logging.py**: Loguru-based logging configuration
- **monitoring.py**: Prometheus metrics middleware
- **security.py**: JWT authentication, rate limiting, IP blocking

## Repository State (as of Jan 2026)

### Working Features
- REST API for product tracking (CRUD operations)
- JWT authentication with OAuth2 password flow
- Rate limiting on all API endpoints
- Web scraping for Amazon, Walmart, Best Buy, Target, eBay + generic sites
- Signal integration (listener and notifications)
- Celery background tasks for price checking
- Prometheus metrics and Loguru logging
- Docker deployment with all services
- Database migrations with Alembic

### Known Issues

**Medium Priority**:
- `tasks/price_check.py` uses `print()` instead of logger
- Price type inconsistency: sometimes string (`"$80"`), sometimes float
- Integration tests in `tests/integration/` are skipped

**Low Priority**:
- Hardcoded metrics port 8001 in `main.py` (should use `settings.METRICS_PORT`)
- Static user agent in scraper (easily detected)
- No database connection pooling configuration

### Technical Debt Backlog

| Issue | Location | Fix |
|-------|----------|-----|
| Replace print with logger | `tasks/price_check.py` | Use `get_logger()` |
| Re-enable integration tests | `tests/integration/` | Debug and fix skipped tests |

See `ARCHITECTURE.md` for system design details.

## Key Configuration

- Environment variables: See `.env.example` for required settings
- Ruff config: Root `pyproject.toml` defines linting rules (line length 100)
- Pytest config: `backend/pyproject.toml` sets `pythonpath = "."` and `testpaths = ["tests"]`

## Docker Services

The `docker-compose.yml` runs:
- **backend**: FastAPI on port 8000
- **worker**: Celery worker
- **broker**: Redis on port 6379
- **postgres**: PostgreSQL on port 5432
