# Architecture

## Current System Overview

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
│   auth.py           │   listener.py       │   (Celery background tasks)     │
│   (API endpoints)   │   notification.py   │                                 │
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

**models/database.py** - Database initialization with connection pooling and metrics

### Utilities

- **logging.py** - Loguru configuration with file rotation
- **monitoring.py** - Prometheus metrics and middleware
- **security.py** - JWT auth, rate limiting, IP blocking

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

---

## Future Architecture

### Phase 1-2: Per-User Tracking

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Interfaces                                 │
├───────────────────┬─────────────────────────┬───────────────────────────────┤
│     REST API      │    React Web Frontend   │      Signal Group Chat        │
│  (FastAPI :8000)  │      (Vite :3000)       │    (! prefix commands)        │
└─────────┬─────────┴───────────┬─────────────┴─────────────┬─────────────────┘
          │                     │                           │
          │                     │                           ▼
          │                     │              ┌────────────────────────────┐
          │                     │              │  listener.py (enhanced)    │
          │                     │              │  - Parse sender phone      │
          │                     │              │  - !track, !list, !stop    │
          │                     │              │  - Per-user command scope  │
          │                     │              └─────────────┬──────────────┘
          │                     │                            │
          ▼                     ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Backend Services (user-aware)                        │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Database Schema                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  User                          Product                    PriceHistory      │
│  ├── id                        ├── id                     ├── id            │
│  ├── signal_phone (unique)     ├── user_id (FK) ────────► │                 │
│  ├── signal_username           ├── title, url             ├── product_id    │
│  ├── email (nullable)          ├── target_price           ├── price         │
│  ├── password_hash (nullable)  ├── created_at             └── timestamp     │
│  └── created_at                └── updated_at                               │
│                                                                             │
│  Note: Same URL can be tracked by multiple users (composite unique on       │
│        user_id + url instead of url alone)                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Changes:**
- `User` model links Signal phone numbers to accounts
- Products belong to users via `user_id` foreign key
- Signal listener parses sender info and auto-creates users
- Commands require `!` prefix: `!track`, `!list`, `!stop`, `!help`, `!status`
- Each user sees only their own tracked products

### Phase 3: React Web Interface

```
frontend/
├── src/
│   ├── components/
│   │   ├── ProductCard.tsx       # Product display with price info
│   │   ├── PriceChart.tsx        # Price history visualization
│   │   └── AddProductForm.tsx    # URL input with validation
│   ├── pages/
│   │   ├── Login.tsx             # JWT authentication
│   │   ├── Register.tsx          # New user signup
│   │   ├── Dashboard.tsx         # Product list overview
│   │   └── ProductDetail.tsx     # Single product view
│   ├── api/
│   │   └── client.ts             # Axios/fetch wrapper for backend
│   └── App.tsx                   # React Router setup
├── package.json
└── vite.config.ts
```

**Tech Stack:**
- React 18+ with TypeScript
- Vite for build tooling
- TailwindCSS for styling
- React Router for navigation
- Recharts or Chart.js for price history graphs

### Phase 4: Signal Bot Framework (Monorepo)

```
wheel-n-deal/
├── packages/
│   ├── signal-bot-core/              # Reusable Signal bot framework
│   │   ├── src/
│   │   │   ├── bot.py                # SignalBot base class
│   │   │   ├── message.py            # Message parsing utilities
│   │   │   ├── command.py            # Command registration interface
│   │   │   └── plugin.py             # Plugin base class
│   │   └── pyproject.toml
│   │
│   └── wheel-n-deal/                 # Price tracking plugin
│       ├── src/
│       │   ├── plugin.py             # WheelNDealPlugin(Plugin)
│       │   ├── commands/
│       │   │   ├── track.py          # !track command
│       │   │   ├── list.py           # !list command
│       │   │   └── stop.py           # !stop command
│       │   ├── services/
│       │   │   ├── scraper.py
│       │   │   └── notification.py
│       │   └── models.py
│       └── pyproject.toml
│
├── frontend/                         # React web UI
├── docker-compose.yml
└── pyproject.toml                    # Workspace root
```

**Plugin Interface:**
```python
# signal-bot-core/plugin.py
class Plugin(ABC):
    @abstractmethod
    def get_commands(self) -> list[Command]: ...

    @abstractmethod
    def on_load(self, bot: SignalBot) -> None: ...

# Command registration
class Command:
    name: str           # e.g., "track"
    prefix: str         # e.g., "!"
    handler: Callable   # async def handle(ctx: Context) -> str
    help_text: str      # Shown in !help
```

**Benefits:**
- Clean separation of bot infrastructure from domain logic
- Other plugins can be added (reminders, polls, etc.)
- Shared message parsing, user management, rate limiting
- wheel-n-deal becomes one of potentially many bot capabilities
