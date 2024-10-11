# wheel-n-deal

## project skeleton

```
/price-tracker
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── config.py
│   ├── utils/
│   │   ├── whatsapp_handler.py
│   │   └── notification.py
│   └── templates/
│
├── scraper/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── scraper.py
│   ├── utils/
│   │   ├── scraper_utils.py
│   │   └── parser.py
│
├── scheduler/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── celery.py
│   └── tasks/
│       └── price_check.py
│
├── database/
│   ├── init.sql
│   ├── Dockerfile
│   └── config.env
│
├── broker/
│   ├── Dockerfile
│
├── vpn/                          # VPN configuration for PIA
│   ├── Dockerfile
│   ├── openvpn/                  # OpenVPN configuration files
│   │   ├── credentials.conf
│   │   └── vpn-config.ovpn
│   └── cycle_ip.sh               # Script to cycle the IP address periodically
│
├── nginx/
│   ├── nginx.conf
│   ├── Dockerfile
│
├── docker-compose.yml
├── .env
├── requirements.txt
├── README.md
└── scripts/
    ├── start.sh
    ├── stop.sh
    └── restart.sh
```
