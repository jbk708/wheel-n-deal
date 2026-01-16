# Deploying Wheel-n-Deal on Debian (Proxmox + Docker)

This guide covers deploying Wheel-n-Deal using Docker Compose on a Debian VM/LXC in Proxmox, with Nginx Proxy Manager for reverse proxy and SSL.

## Prerequisites

- Proxmox VE 7.0+
- Debian 12 (Bookworm) VM or LXC container
- At least 2GB RAM, 2 vCPUs, 20GB storage
- Nginx Proxy Manager running on your network
- Domain name pointed to your server

## 1. Create Debian Container/VM in Proxmox

### Option A: LXC Container
```bash
# In Proxmox shell
pveam update
pveam download local debian-12-standard_12.2-1_amd64.tar.zst

# Create container (use privileged for Docker)
pct create 100 local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst \
  --hostname wheel-n-deal \
  --memory 2048 \
  --cores 2 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --features nesting=1

pct start 100
pct enter 100
```

### Option B: VM
Create a Debian 12 VM through the Proxmox web UI with similar specs.

## 2. Install Docker

```bash
# Update system
apt update && apt upgrade -y

# Install prerequisites
apt install -y ca-certificates curl gnupg

# Add Docker GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

## 3. Clone and Configure Application

```bash
# Clone repository
cd /opt
git clone https://github.com/jbk708/wheel-n-deal.git
cd wheel-n-deal

# Create environment file
cp .env.example .env
```

Edit `.env` with your settings:
```bash
nano .env
```

```env
# Application
ENVIRONMENT=production
LOG_LEVEL=INFO

# Security - generate with: openssl rand -hex 32
SECRET_KEY=your-generated-secret-key

# Database (uses internal Docker network)
DATABASE_URL=postgresql://postgres:your-secure-db-password@postgres:5432/wheel_n_deal

# Signal
SIGNAL_PHONE_NUMBER=+1234567890
SIGNAL_GROUP_ID=your-group-id
```

Update `docker-compose.yml` postgres password to match:
```bash
nano docker-compose.yml
```

Change the postgres environment section:
```yaml
environment:
  - POSTGRES_USER=postgres
  - POSTGRES_PASSWORD=your-secure-db-password  # Match DATABASE_URL
  - POSTGRES_DB=wheel_n_deal
```

## 4. Configure Docker Network for Nginx Proxy Manager

Create a shared network that NPM can access:

```bash
docker network create proxy-network
```

Update `docker-compose.yml` to use the external network and remove external port bindings:

```yaml
services:
  backend:
    build: ./backend
    expose:
      - "8000"
    volumes:
      - ./signal-cli:/root/.local/share/signal-cli
    environment:
      - ENVIRONMENT=${ENVIRONMENT:-production}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - DATABASE_URL=${DATABASE_URL:-postgresql://postgres:postgres@postgres:5432/wheel_n_deal}
      - SIGNAL_PHONE_NUMBER=${SIGNAL_PHONE_NUMBER}
      - SIGNAL_GROUP_ID=${SIGNAL_GROUP_ID}
      - SECRET_KEY=${SECRET_KEY:-your_secure_secret_key}
    depends_on:
      - broker
      - postgres
    restart: always
    command: uv run uvicorn main:app --host 0.0.0.0 --port 8000
    networks:
      - internal
      - proxy-network

  worker:
    build: ./backend
    volumes:
      - ./signal-cli:/root/.local/share/signal-cli
    environment:
      - ENVIRONMENT=${ENVIRONMENT:-production}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - DATABASE_URL=${DATABASE_URL:-postgresql://postgres:postgres@postgres:5432/wheel_n_deal}
      - SIGNAL_PHONE_NUMBER=${SIGNAL_PHONE_NUMBER}
      - SIGNAL_GROUP_ID=${SIGNAL_GROUP_ID}
      - SECRET_KEY=${SECRET_KEY:-your_secure_secret_key}
    depends_on:
      - broker
      - postgres
      - backend
    restart: always
    command: uv run celery -A celery_app worker --loglevel=info
    networks:
      - internal

  broker:
    image: redis:alpine
    restart: always
    volumes:
      - redis-data:/data
    networks:
      - internal

  postgres:
    image: postgres:14-alpine
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=your-secure-db-password
      - POSTGRES_DB=wheel_n_deal
    volumes:
      - postgres-data:/var/lib/postgresql/data
    restart: always
    networks:
      - internal

networks:
  internal:
    driver: bridge
  proxy-network:
    external: true

volumes:
  redis-data:
  postgres-data:
```

## 5. Set Up Signal CLI

Signal CLI needs to be configured before the containers can send notifications:

```bash
# Create signal-cli directory
mkdir -p /opt/wheel-n-deal/signal-cli

# Run signal-cli in a temporary container to register
docker run --rm -it \
  -v /opt/wheel-n-deal/signal-cli:/root/.local/share/signal-cli \
  registry.gitlab.com/packaging/signal-cli/signal-cli-native:latest \
  signal-cli -u +1234567890 register

# Verify with the code you receive
docker run --rm -it \
  -v /opt/wheel-n-deal/signal-cli:/root/.local/share/signal-cli \
  registry.gitlab.com/packaging/signal-cli/signal-cli-native:latest \
  signal-cli -u +1234567890 verify CODE

# Or link to existing Signal account
docker run --rm -it \
  -v /opt/wheel-n-deal/signal-cli:/root/.local/share/signal-cli \
  registry.gitlab.com/packaging/signal-cli/signal-cli-native:latest \
  signal-cli link -n "wheel-n-deal"
```

## 6. Start the Application

```bash
cd /opt/wheel-n-deal

# Build and start all services
docker compose up -d --build

# Check status
docker compose ps

# View logs
docker compose logs -f
```

## 7. Configure Nginx Proxy Manager

### If NPM is on the same host

Ensure NPM is connected to the `proxy-network`:

```bash
# Connect NPM container to the network
docker network connect proxy-network <npm-container-name>
```

### Add Proxy Host in NPM

1. Log into Nginx Proxy Manager web UI
2. Go to **Hosts** → **Proxy Hosts** → **Add Proxy Host**
3. Configure the **Details** tab:
   - **Domain Names**: `deals.yourdomain.com`
   - **Scheme**: `http`
   - **Forward Hostname/IP**: `backend` (Docker service name)
   - **Forward Port**: `8000`
   - **Block Common Exploits**: ✓
   - **Websockets Support**: ✓

4. Configure the **SSL** tab:
   - **SSL Certificate**: Request a new SSL certificate
   - **Force SSL**: ✓
   - **HTTP/2 Support**: ✓
   - **HSTS Enabled**: ✓

5. Click **Save**

### If NPM is on a different host

Use the Debian host's IP address instead of Docker service name:

1. Update `docker-compose.yml` to expose port 8000:
   ```yaml
   backend:
     ports:
       - "8000:8000"
   ```

2. In NPM, set:
   - **Forward Hostname/IP**: `<debian-host-ip>`
   - **Forward Port**: `8000`

## 8. Verify Deployment

```bash
# Check all containers are running
docker compose ps

# Test API locally
curl http://localhost:8000/docs

# Test through NPM (after configuration)
curl https://deals.yourdomain.com/docs
```

## Management Commands

```bash
cd /opt/wheel-n-deal

# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f backend
docker compose logs -f worker

# Restart a specific service
docker compose restart backend

# Rebuild after code changes
git pull
docker compose up -d --build

# Run database migrations
docker compose exec backend uv run alembic upgrade head

# Access postgres
docker compose exec postgres psql -U postgres -d wheel_n_deal
```

## Troubleshooting

### Container won't start
```bash
docker compose logs backend
docker compose logs worker
```

### Database connection issues
```bash
# Check postgres is running
docker compose ps postgres

# Test connection
docker compose exec postgres psql -U postgres -d wheel_n_deal -c "SELECT 1"
```

### NPM can't reach backend
```bash
# Verify network connectivity
docker network inspect proxy-network

# Check backend is on the network
docker inspect wheel-n-deal-backend-1 | grep -A 20 Networks
```

### Signal not sending messages
```bash
# Check signal-cli configuration
docker compose exec backend ls -la /root/.local/share/signal-cli

# Test signal-cli manually
docker run --rm -it \
  -v /opt/wheel-n-deal/signal-cli:/root/.local/share/signal-cli \
  registry.gitlab.com/packaging/signal-cli/signal-cli-native:latest \
  signal-cli -u +1234567890 listGroups
```

## Updating

```bash
cd /opt/wheel-n-deal
git pull
docker compose down
docker compose up -d --build
docker compose exec backend uv run alembic upgrade head
```
