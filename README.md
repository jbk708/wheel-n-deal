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

## Deployment

### Prerequisites for Deployment

- Python 3.10+ (required by the backend)
- Docker and Docker Compose (for containerized deployment)
- Poetry (for Python package management)
- Signal CLI setup with a registered phone number

### Local Deployment with Poetry

1. Install Poetry if you haven't already:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. Navigate to the backend directory and install dependencies:
   ```bash
   cd backend
   poetry install
   ```

3. Run the FastAPI server:
   ```bash
   poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. In a separate terminal, start the Celery worker:
   ```bash
   cd backend
   poetry run celery -A celery_app worker --loglevel=info
   ```

### Docker Deployment (Recommended for Production)

1. Make sure your `.env` file is properly configured with production settings:
   ```
   # Environment
   ENVIRONMENT=production
   LOG_LEVEL=INFO
   
   # Database
   DATABASE_URL=postgresql://user:password@postgres:5432/wheel_n_deal
   
   # Signal
   SIGNAL_PHONE_NUMBER=your_signal_phone_number
   SIGNAL_GROUP_ID=your_signal_group_id
   
   # Security
   SECRET_KEY=your_secure_secret_key
   ```

2. Set up Signal CLI:
   
   The application uses Signal for notifications. You need to set up Signal CLI with your phone number:
   
   ```bash
   # Create a directory for Signal data
   mkdir -p signal-cli
   
   # Register your phone number with Signal (you'll receive a verification code)
   docker run --rm -v $(pwd)/signal-cli:/root/.local/share/signal-cli \
     -it registry.gitlab.com/signald/signald-docker signal-cli \
     -a YOUR_PHONE_NUMBER register
   
   # Verify your phone number with the code you received
   docker run --rm -v $(pwd)/signal-cli:/root/.local/share/signal-cli \
     -it registry.gitlab.com/signald/signald-docker signal-cli \
     -a YOUR_PHONE_NUMBER verify CODE_YOU_RECEIVED
   
   # Get your Signal group ID (if you want to use a group for notifications)
   docker run --rm -v $(pwd)/signal-cli:/root/.local/share/signal-cli \
     -it registry.gitlab.com/signald/signald-docker signal-cli \
     -a YOUR_PHONE_NUMBER listGroups
   ```
   
   Update your `.env` file with the phone number and group ID.

3. Build and start the Docker containers:
   ```bash
   ./run_docker.sh start
   ```

   This script provides several commands:
   - `./run_docker.sh start`: Start all services
   - `./run_docker.sh stop`: Stop all services
   - `./run_docker.sh restart`: Restart all services
   - `./run_docker.sh logs`: View logs from all services

4. The application will be available at:
   - API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - Prometheus Metrics: http://localhost:8000/metrics

5. Verify the deployment:
   ```bash
   # Check if all containers are running
   docker ps
   
   # Check the logs
   ./run_docker.sh logs
   ```

### Deployment to a Cloud Provider

For deploying to cloud providers like AWS, GCP, or Azure:

1. Build the Docker image:
   ```bash
   docker build -t wheel-n-deal:latest ./backend
   ```

2. Push the image to your container registry:
   ```bash
   docker tag wheel-n-deal:latest your-registry/wheel-n-deal:latest
   docker push your-registry/wheel-n-deal:latest
   ```

3. Deploy using your cloud provider's container service (AWS ECS, GCP Cloud Run, Azure Container Instances, etc.)

4. Make sure to configure environment variables in your cloud provider's dashboard or through infrastructure as code.

### Continuous Integration/Deployment

For CI/CD setup:

1. Run tests before deployment:
   ```bash
   cd backend
   poetry run pytest
   ```

2. Ensure all tests pass before deploying to production.

3. Consider setting up a CI/CD pipeline using GitHub Actions, GitLab CI, or Jenkins.

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
