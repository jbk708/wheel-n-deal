# Wheel-n-Deal

A price tracking and deal notification service that monitors product prices across various e-commerce websites and sends notifications when prices drop to your target.

## Features

- **Product Tracking**: Track prices of products from Amazon, Walmart, Best Buy, Target, eBay, and other e-commerce sites
- **Price Alerts**: Get notified via Signal when prices drop to your target
- **Signal Integration**: Interact with the service through a Signal group chat
- **Structured Logging**: Comprehensive logging system using Loguru
- **Monitoring**: Prometheus metrics for application monitoring
- **Security**: Authentication and rate limiting to protect the API

## Architecture

The application consists of the following components:

- **FastAPI Backend**: RESTful API for product tracking and management
- **Signal Listener**: Service that listens for commands from a Signal group
- **Scraper**: Module that extracts product information from e-commerce websites
- **Price Checker**: Scheduled task that checks for price drops
- **Notification Service**: Sends alerts to Signal when prices drop
- **Monitoring**: Prometheus metrics server for observability

## Setup

### Prerequisites

- Python 3.9+
- Signal CLI (for Signal integration)
- PostgreSQL (optional, SQLite is used by default)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/wheel-n-deal.git
   cd wheel-n-deal
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your configuration:
   ```
   # Environment
   ENVIRONMENT=development
   LOG_LEVEL=INFO
   
   # Database
   DATABASE_URL=sqlite:///./wheel_n_deal.db
   
   # Signal
   SIGNAL_PHONE_NUMBER=your_signal_phone_number
   SIGNAL_GROUP_ID=your_signal_group_id
   
   # Security
   SECRET_KEY=your_secret_key
   ```

4. Initialize the database:
   ```bash
   python -m backend.models.database
   ```

### Running the Application

1. Start the FastAPI server:
   ```bash
   uvicorn backend.main:app --reload
   ```

2. Start the Signal listener in a separate terminal:
   ```bash
   python -m backend.services.listener
   ```

## Usage

### API Endpoints

- `POST /track`: Track a new product
- `GET /products`: List all tracked products
- `GET /products/{product_id}`: Get details of a specific product
- `DELETE /products/{product_id}`: Stop tracking a product
- `POST /check-prices`: Manually trigger a price check

### Signal Commands

- `track <url> [target_price]`: Track a product with an optional target price
- `list`: List all tracked products
- `stop <number>`: Stop tracking a product by its number in the list
- `status`: Check if the bot is running
- `help`: Show available commands

## Monitoring

The application exposes Prometheus metrics at `http://localhost:8001/metrics` for monitoring:

- HTTP request counts and latencies
- Database connections and errors
- Scraper performance and errors
- Number of tracked products
- Price alerts sent
- Signal messages sent and failed

## Logging

Logs are stored in the `logs` directory:

- `wheel_n_deal.log`: All application logs
- `errors.log`: Error logs only

## Security

The API includes:

- JWT authentication for protected endpoints
- Rate limiting to prevent abuse
- IP blocking for suspicious activity

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
