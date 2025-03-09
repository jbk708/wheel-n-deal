# Wheel-n-Deal

A Signal bot that receives product links from a Signal chat, tracks them, and reports when the price of the scraped item goes down by a certain amount.

## Project Overview

Wheel-n-Deal is designed to help users track product prices across various e-commerce websites. When a user sends a product URL to a Signal group, the bot:

1. Scrapes the product information (title, price)
2. Tracks the price over time
3. Sends a notification when the price drops below a specified threshold

## Current Status

The project has a functional structure in place with several key features implemented:

### What Works
- FastAPI backend structure with API endpoints
- Signal message listener for command processing
- Product URL scraping with Selenium (supports Amazon, Walmart, Best Buy, Target, eBay, and generic websites)
- Signal notification sending
- Celery task scheduling for price checks
- SQLite database integration for persistent storage
- Comprehensive unit and integration tests

### What Needs to be Done
- **Database Migration**: Upgrade from SQLite to PostgreSQL for production use
- **UI**: Add a simple web UI for managing tracked products
- **Monitoring**: Add monitoring and logging for production use
- **Security**: Improve security for Signal integration
- **Deployment**: Complete Docker setup for production deployment
- **CI/CD**: Set up continuous integration and deployment

## Project Structure

```
/wheel-n-deal
│
├── backend/                         # Backend with scraper and scheduler
│   ├── Dockerfile                   # Docker configuration for backend
│   ├── pyproject.toml               # Poetry project configuration
│   ├── poetry.lock                  # Poetry lockfile with dependency versions
│   ├── main.py                      # FastAPI entry point
│   ├── celery_app.py                # Celery configuration
│   ├── config.py                    # Configuration file (env variables, settings)
│   ├── models.py                    # Database models
│   ├── routers/                     # API routers
│   │   ├── __init__.py              # Router initialization
│   │   └── tracker.py               # Product tracking endpoints
│   ├── services/                    # Core services
│   │   ├── __init__.py              # Service initialization
│   │   ├── listener.py              # Signal message listener
│   │   ├── notification.py          # Signal notification sender
│   │   └── scraper.py               # Web scraper for product information
│   ├── tasks/                       # Celery tasks
│   │   ├── __init__.py              # Task initialization
│   │   └── price_check.py           # Price checking task
│   └── tests/                       # Test suite
│       ├── __init__.py              # Test initialization
│       ├── fixtures/                # Test fixtures
│       │   ├── __init__.py          # Fixture initialization
│       │   └── test_fixtures.py     # Database fixtures
│       ├── integration/             # Integration tests
│       │   ├── __init__.py          # Integration test initialization
│       │   ├── test_celery.py       # Celery task tests
│       │   └── test_endpoints.py    # API endpoint tests
│       ├── test_listener.py         # Listener service tests
│       ├── test_models.py           # Database model tests
│       ├── test_notification.py     # Notification service tests
│       ├── test_price_check.py      # Price check task tests
│       ├── test_scraper.py          # Scraper service tests
│       └── test_tracker.py          # Tracker router tests
│
├── signal-cli/                      # Signal CLI data directory
│   ├── data/                        # Signal data
│   ├── avatars/                     # Avatar images
│   └── stickers/                    # Sticker packs
│
├── docker-compose.yml               # Docker Compose configuration
├── .env                             # Environment variables
├── run_docker.sh                    # Script to manage Docker services
└── README.md                        # Documentation
```

## Setup and Installation

### Prerequisites
- Docker and Docker Compose
- Signal account with signal-cli configured

### Environment Variables
Create a `.env` file with the following variables:
```
SIGNAL_PHONE_NUMBER="your_signal_number"
SIGNAL_GROUP_ID="your_signal_group_id"
```

### Running the Application
```bash
# Start the services
./run_docker.sh start

# View logs
./run_docker.sh logs

# Stop the services
./run_docker.sh stop
```

## Usage

In your Signal group, you can use the following commands:

- `track <url> [target_price]` - Track a product URL with optional target price
- `status` - Check if the bot is running
- `list` - List all tracked products
- `stop <number>` - Stop tracking a product by its number in the list
- `help` - Show available commands

## API Endpoints

The application provides the following API endpoints:

- `GET /` - Root endpoint for checking API status
- `POST /api/v1/tracker/track` - Track a new product
- `GET /api/v1/tracker/products` - Get all tracked products

## Testing

The project includes comprehensive unit and integration tests. To run the tests:

```bash
cd backend
poetry run pytest
```

## Next Steps for Development

1. **Database Migration**
   - Implement PostgreSQL for production use
   - Create database migration scripts

2. **Web UI**
   - Create a simple web UI for managing tracked products
   - Implement authentication for the web UI

3. **Monitoring and Logging**
   - Add structured logging
   - Implement monitoring with Prometheus and Grafana

4. **Security Improvements**
   - Enhance Signal integration security
   - Implement rate limiting for API endpoints

5. **Production Deployment**
   - Complete Docker setup for production
   - Set up CI/CD pipeline with GitHub Actions

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
