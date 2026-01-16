# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Interfaces                                 │
├─────────────────────────────────┬───────────────────────────────────────────┤
│         REST API                │           Signal Group Chat               │
│    (FastAPI on :8000)           │         (Signal CLI listener)             │
└───────────────┬─────────────────┴─────────────────┬─────────────────────────┘
                │                                   │
                ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Backend Services                                  │
├─────────────────────┬─────────────────────┬─────────────────────────────────┤
│   routers/          │   services/         │   tasks/                        │
│   tracker.py        │   scraper.py        │   price_check.py                │
│   (API endpoints)   │   listener.py       │   (Celery background tasks)     │
│                     │   notification.py   │                                 │
└─────────┬───────────┴─────────┬───────────┴───────────────┬─────────────────┘
          │                     │                           │
          ▼                     ▼                           ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────────────┐
│     Database        │ │   External Sites    │ │        Message Queue        │
│  SQLite / Postgres  │ │  (Amazon, Walmart,  │ │     (Redis via Celery)      │
│                     │ │   BestBuy, etc.)    │ │                             │
└─────────────────────┘ └─────────────────────┘ └─────────────────────────────┘
```

## Component Details

### Entry Point (`main.py`)

The FastAPI application initializes in this order:
1. Database tables via `init_db()`
2. Signal listener in daemon thread
3. Prometheus metrics server on port 8001

### API Layer (`routers/tracker.py`)

REST endpoints mounted at `/api/v1/tracker`:
- `POST /track` - Add product, scrape initial price, schedule price checks
- `GET /products` - List all tracked products with latest prices
- `GET /products/{id}` - Single product details
- `DELETE /products/{id}` - Remove product from tracking
- `POST /check-prices` - Manual price check trigger

### Services Layer

**scraper.py** - Web scraping with Selenium + BeautifulSoup
- Site-specific parsers: Amazon, Walmart, Best Buy, Target, eBay
- Generic fallback with regex price extraction
- Returns `{title, price, url}` dictionary

**listener.py** - Signal group chat command processor
- Commands: `track <url> [price]`, `list`, `stop <num>`, `status`, `help`
- Runs as daemon thread, polls for messages

**notification.py** - Signal message sender
- Sends price drop alerts via `signal-cli` subprocess

### Background Tasks (`tasks/price_check.py`)

Celery task `check_price(product_id)`:
1. Fetch product from database
2. Scrape current price
3. Compare to target price
4. Send notification if price dropped
5. Record price history
6. Reschedule self with random offset (±10 min from 1 hour interval)

### Data Layer

**models.py** - SQLAlchemy models (canonical source)
```
Product
├── id, title, url, description, image_url
├── target_price, created_at, updated_at
└── price_history (relationship)

PriceHistory
├── id, product_id, price, timestamp
└── product (relationship)
```

**models/database.py** - Database initialization with metrics (duplicate models - technical debt)

### Utilities

- **logging.py** - Loguru configuration with file rotation
- **monitoring.py** - Prometheus metrics and middleware
- **security.py** - JWT auth, rate limiting, IP blocking (partially wired)

### Configuration (`config.py`)

Pydantic settings loaded from environment variables and `.env`:
- Database URL, Signal credentials, secret key
- Rate limits, scraper timeouts, check intervals

## Data Flow: Price Tracking

```
1. User sends "track <url> $50" via Signal
         │
         ▼
2. listener.py parses command, calls tracker API
         │
         ▼
3. tracker.py invokes scraper.py
         │
         ▼
4. scraper.py launches headless Chrome, extracts price
         │
         ▼
5. Product + PriceHistory saved to database
         │
         ▼
6. Celery task scheduled for periodic price checks
         │
         ▼
7. On price drop: notification.py sends Signal alert
```

## Docker Services

| Service   | Image/Build     | Port  | Purpose                    |
|-----------|-----------------|-------|----------------------------|
| backend   | ./backend       | 8000  | FastAPI application        |
| worker    | ./backend       | -     | Celery worker              |
| broker    | redis:alpine    | 6379  | Celery message broker      |
| postgres  | postgres:14     | 5432  | Production database        |

## Key Technical Decisions

- **Selenium over requests**: Required for JavaScript-rendered prices
- **Celery over APScheduler**: Distributed task execution, Redis persistence
- **Signal over email/SMS**: Free, encrypted, group chat support
- **SQLite dev / Postgres prod**: Zero-config development, scalable production
