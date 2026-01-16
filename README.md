# Wheel-n-Deal

A price tracking service that monitors products across e-commerce sites and sends Signal notifications when prices drop.

## Features

- **Multi-site scraping**: Amazon, Walmart, Best Buy, Target, eBay, and generic sites
- **Signal integration**: Track products and receive alerts via Signal group chat
- **REST API**: Full CRUD operations with JWT authentication and rate limiting
- **Background processing**: Celery workers for scheduled price checks
- **Monitoring**: Prometheus metrics and structured Loguru logging
- **Database migrations**: Alembic for schema management

## Requirements

- Python 3.12+
- Redis (Celery broker)
- PostgreSQL (production) or SQLite (development)
- Signal CLI (for notifications)

### Installing External Dependencies

**macOS (Homebrew):**
```bash
brew install redis postgresql signal-cli
brew services start redis
brew services start postgresql
```

**Ubuntu/Debian:**
```bash
# Redis
sudo apt install redis-server
sudo systemctl enable redis-server

# PostgreSQL
sudo apt install postgresql postgresql-contrib
sudo systemctl enable postgresql

# Signal CLI (download from GitHub releases)
# https://github.com/AsamK/signal-cli/releases
```

**Signal CLI Setup:**
```bash
# Register or link to existing Signal account
signal-cli -u +1234567890 register
signal-cli -u +1234567890 verify CODE

# Or link to existing device
signal-cli link -n "wheel-n-deal"
```

## Quick Start

```bash
# Clone and enter directory
git clone https://github.com/jbk708/wheel-n-deal.git
cd wheel-n-deal/backend

# Install dependencies
uv sync

# Configure environment
cp .env.example .env  # Edit with your settings

# Run database migrations
uv run alembic upgrade head

# Start the API server
uv run uvicorn main:app --reload

# Start Celery worker (separate terminal)
uv run celery -A celery_app worker --loglevel=info
```

## Docker Deployment

```bash
# Configure environment
cp .env.example .env  # Edit with production settings

# Start all services
./run_docker.sh start

# Other commands
./run_docker.sh stop     # Stop services
./run_docker.sh restart  # Restart services
./run_docker.sh logs     # View logs
```

Services:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **Metrics**: http://localhost:8001

## Configuration

Create a `.env` file in the project root:

```env
# Required
SECRET_KEY=your-secure-secret-key
SIGNAL_PHONE_NUMBER=+1234567890
SIGNAL_GROUP_ID=your-group-id

# Optional (defaults shown)
ENVIRONMENT=development
DATABASE_URL=sqlite:///./wheel_n_deal.db
LOG_LEVEL=INFO
```

Generate a secure `SECRET_KEY` for JWT signing:
```bash
openssl rand -hex 32
```

For production, use PostgreSQL:
```env
DATABASE_URL=postgresql://user:password@localhost:5432/wheel_n_deal
```

## API Endpoints

All endpoints are prefixed with `/api/v1/tracker`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/track` | Track a new product |
| GET | `/products` | List all tracked products |
| GET | `/products/{id}` | Get product details |
| DELETE | `/products/{id}` | Stop tracking a product |
| POST | `/check-prices` | Trigger manual price check |

Authentication endpoints at `/api/v1/auth`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/token` | Get access token |
| POST | `/refresh` | Refresh token |

## Signal Commands

Send these commands in your Signal group:

| Command | Description |
|---------|-------------|
| `track <url> [price]` | Track product with optional target price |
| `list` | Show all tracked products |
| `stop <number>` | Stop tracking by list number |
| `status` | Check bot status |
| `help` | Show commands |

## Development

```bash
cd backend

# Run tests
uv run pytest

# Linting and formatting
uv run ruff check . --fix
uv run ruff format .

# Type checking
uv run ty check

# Database migrations
uv run alembic upgrade head          # Apply migrations
uv run alembic revision --autogenerate -m "Description"  # Create migration
```

## License

GPL-3.0
