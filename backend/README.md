# Wheel-n-Deal Backend

This is the backend service for the Wheel-n-Deal price tracking application. It provides a FastAPI-based REST API for tracking product prices and sending notifications when prices drop.

## Components

- **FastAPI API**: RESTful API for product tracking and management
- **Celery Worker**: Background task processing for price checking
- **Signal Integration**: Notifications via Signal messaging app
- **Prometheus Metrics**: Application monitoring

## Development

### Prerequisites

- Python 3.10+
- Poetry for dependency management
- Signal CLI for notifications
- Redis for Celery broker

### Setup

1. Install dependencies:
   ```bash
   poetry install
   ```

2. Run the API server:
   ```bash
   poetry run uvicorn main:app --reload
   ```

3. Run the Celery worker:
   ```bash
   poetry run celery -A celery_app worker --loglevel=info
   ```

## Testing

Run the tests with pytest:
```bash
poetry run pytest
```

## Deployment

See the main project README for deployment instructions. 