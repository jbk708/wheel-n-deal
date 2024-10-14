# wheel-n-deal

## project skeleton

```
/price-tracker
│
├── backend/                         # Unified backend with scraper and scheduler
│   ├── Dockerfile                   # Single Docker configuration for backend, scraper, and scheduler
│   ├── pyproject.toml               # Poetry project configuration
│   ├── poetry.lock                  # Poetry lockfile with dependency versions
│   ├── main.py                      # FastAPI entry point
│   ├── celery.py                    # Celery configuration
│   ├── config.py                    # Configuration file (env variables, settings)
│   ├── routers/
│   │   ├── __init__.py              # API router setup
│   │   └── tracker.py               # Routes for product tracking
│   ├── services/
│   │   ├── scraper.py               # Scraper logic using Selenium
│   │   └── notification.py          # Signal notification logic
│   ├── tasks/
│   │   └── price_check.py           # Celery task for scheduled price checks
│   ├── utils/
│   │   └── helpers.py               # Helper functions
│   └── templates/                   # HTML templates (if any)
│
├── database/
│   ├── init.sql                     # SQL initialization script
│   ├── Dockerfile                   # Database Dockerfile
│   └── config.env                   # Database configuration
│
├── broker/
│   ├── Dockerfile                   # Message broker Dockerfile (e.g., Redis or RabbitMQ)
│
├── vpn/                             # VPN configuration for PIA
│   ├── Dockerfile                   # VPN Dockerfile
│   ├── openvpn/                     # OpenVPN configuration files
│   │   ├── credentials.conf
│   │   └── vpn-config.ovpn
│   └── cycle_ip.sh                  # IP cycling script for VPN
│
├── nginx/                           # Nginx proxy configuration
│   ├── nginx.conf                   # Nginx configuration
│   ├── Dockerfile                   # Nginx Dockerfile
│
├── docker-compose.yml               # Docker Compose configuration for all services
├── .env                             # Environment variables for the project
├── README.md                        # Documentation
└── scripts/                         # Scripts for controlling Docker services
    ├── start.sh                     # Script to start the services
    ├── stop.sh                      # Script to stop the services
    └── restart.sh                   # Script to restart the services

```
