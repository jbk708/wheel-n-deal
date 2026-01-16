# Deploying Wheel-n-Deal on Debian (Proxmox)

This guide covers deploying Wheel-n-Deal on a Debian VM or LXC container inside Proxmox.

## Prerequisites

- Proxmox VE 7.0+
- Debian 12 (Bookworm) VM or LXC container
- At least 2GB RAM, 2 vCPUs, 20GB storage
- Network access to the internet

## 1. Create Debian Container/VM in Proxmox

### Option A: LXC Container (Recommended)
```bash
# In Proxmox shell
pveam update
pveam download local debian-12-standard_12.2-1_amd64.tar.zst

# Create container
pct create 100 local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst \
  --hostname wheel-n-deal \
  --memory 2048 \
  --cores 2 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1

pct start 100
pct enter 100
```

### Option B: VM
Create a Debian 12 VM through the Proxmox web UI with similar specs.

## 2. Initial System Setup

```bash
# Update system
apt update && apt upgrade -y

# Install essential packages
apt install -y curl git build-essential libffi-dev libssl-dev \
  libpq-dev python3-dev wget gnupg2 software-properties-common
```

## 3. Install Python 3.12

```bash
# Add deadsnakes PPA alternative for Debian - build from source
apt install -y build-essential zlib1g-dev libncurses5-dev \
  libgdbm-dev libnss3-dev libreadline-dev libsqlite3-dev libbz2-dev

cd /tmp
wget https://www.python.org/ftp/python/3.12.0/Python-3.12.0.tgz
tar -xf Python-3.12.0.tgz
cd Python-3.12.0
./configure --enable-optimizations
make -j $(nproc)
make altinstall

# Verify
python3.12 --version
```

## 4. Install uv Package Manager

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

## 5. Install Redis

```bash
apt install -y redis-server
systemctl enable redis-server
systemctl start redis-server

# Verify
redis-cli ping  # Should return PONG
```

## 6. Install PostgreSQL

```bash
apt install -y postgresql postgresql-contrib
systemctl enable postgresql
systemctl start postgresql

# Create database and user
sudo -u postgres psql <<EOF
CREATE USER wheelnDeal WITH PASSWORD 'your-secure-password';
CREATE DATABASE wheel_n_deal OWNER wheelnDeal;
GRANT ALL PRIVILEGES ON DATABASE wheel_n_deal TO wheelnDeal;
EOF
```

## 7. Install Signal CLI

```bash
# Install Java (required by Signal CLI)
apt install -y default-jre

# Download Signal CLI
SIGNAL_CLI_VERSION="0.13.2"
cd /opt
wget https://github.com/AsamK/signal-cli/releases/download/v${SIGNAL_CLI_VERSION}/signal-cli-${SIGNAL_CLI_VERSION}.tar.gz
tar -xf signal-cli-${SIGNAL_CLI_VERSION}.tar.gz
ln -s /opt/signal-cli-${SIGNAL_CLI_VERSION}/bin/signal-cli /usr/local/bin/signal-cli

# Verify
signal-cli --version

# Register or link Signal account
signal-cli -u +1234567890 register
signal-cli -u +1234567890 verify CODE

# Or link to existing device
signal-cli link -n "wheel-n-deal-server"
```

## 8. Clone and Configure Application

```bash
# Create app user
useradd -m -s /bin/bash wheelnDeal
su - wheelnDeal

# Clone repository
git clone https://github.com/jbk708/wheel-n-deal.git
cd wheel-n-deal/backend

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
```

Edit `.env` with production settings:
```bash
nano .env
```

```env
ENVIRONMENT=production
SECRET_KEY=<generate with: openssl rand -hex 32>
DATABASE_URL=postgresql://wheelnDeal:your-secure-password@localhost:5432/wheel_n_deal
REDIS_URL=redis://localhost:6379/0

SIGNAL_PHONE_NUMBER=+1234567890
SIGNAL_GROUP_ID=your-group-id

LOG_LEVEL=INFO
```

## 9. Run Database Migrations

```bash
cd /home/wheelnDeal/wheel-n-deal/backend
uv run alembic upgrade head
```

## 10. Create Systemd Services

### API Service
```bash
sudo tee /etc/systemd/system/wheel-n-deal-api.service <<EOF
[Unit]
Description=Wheel-n-Deal API
After=network.target postgresql.service redis-server.service

[Service]
User=wheelnDeal
WorkingDirectory=/home/wheelnDeal/wheel-n-deal/backend
ExecStart=/home/wheelnDeal/.local/bin/uv run uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
Environment=PATH=/home/wheelnDeal/.local/bin:/usr/local/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOF
```

### Celery Worker Service
```bash
sudo tee /etc/systemd/system/wheel-n-deal-worker.service <<EOF
[Unit]
Description=Wheel-n-Deal Celery Worker
After=network.target redis-server.service

[Service]
User=wheelnDeal
WorkingDirectory=/home/wheelnDeal/wheel-n-deal/backend
ExecStart=/home/wheelnDeal/.local/bin/uv run celery -A celery_app worker --loglevel=info
Restart=always
RestartSec=5
Environment=PATH=/home/wheelnDeal/.local/bin:/usr/local/bin:/usr/bin

[Install]
WantedBy=multi-user.target
EOF
```

### Enable and Start Services
```bash
sudo systemctl daemon-reload
sudo systemctl enable wheel-n-deal-api wheel-n-deal-worker
sudo systemctl start wheel-n-deal-api wheel-n-deal-worker

# Check status
sudo systemctl status wheel-n-deal-api
sudo systemctl status wheel-n-deal-worker
```

## 11. Configure Nginx Reverse Proxy (Optional)

```bash
apt install -y nginx

sudo tee /etc/nginx/sites-available/wheel-n-deal <<EOF
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -s /etc/nginx/sites-available/wheel-n-deal /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx
```

## 12. Configure Firewall

```bash
apt install -y ufw
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

## 13. SSL with Let's Encrypt (Optional)

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

## Verification

```bash
# Check API is running
curl http://localhost:8000/docs

# Check services
systemctl status wheel-n-deal-api
systemctl status wheel-n-deal-worker
systemctl status redis-server
systemctl status postgresql

# View logs
journalctl -u wheel-n-deal-api -f
journalctl -u wheel-n-deal-worker -f
```

## Troubleshooting

### Service won't start
```bash
journalctl -u wheel-n-deal-api -n 50
```

### Database connection issues
```bash
sudo -u postgres psql -c "\l"  # List databases
sudo -u postgres psql -c "\du" # List users
```

### Redis connection issues
```bash
redis-cli ping
systemctl status redis-server
```

### Signal CLI issues
```bash
signal-cli -u +1234567890 listGroups
```
