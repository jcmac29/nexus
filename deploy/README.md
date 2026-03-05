# Nexus Deployment Guide

## Quick Start (Docker)

### 1. Clone and Configure

```bash
git clone https://github.com/your-repo/nexus.git
cd nexus

# Copy and edit environment variables
cp .env.production.example .env
nano .env  # Set secure values for all required secrets
```

### 2. Start Services

```bash
docker compose -f docker-compose.prod.yml up -d
```

### 3. Initialize Database

```bash
# Run migrations
docker compose exec api alembic upgrade head

# Create admin user
docker compose exec api python -m nexus.cli admin create \
  --email admin@yourdomain.com \
  --password "YourSecureP@ssw0rd!" \
  --name "Admin"
```

### 4. Access

- **Landing Page**: http://localhost
- **Admin Dashboard**: http://localhost/admin
- **API Docs**: http://localhost/docs

## SSL with Let's Encrypt

### Option A: Certbot (Recommended)

```bash
# Install certbot
apt install certbot python3-certbot-nginx

# Stop nginx temporarily
docker compose stop nginx

# Get certificate
certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# Update nginx config to use SSL
# Copy certs to deploy/nginx/ssl/
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem deploy/nginx/ssl/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem deploy/nginx/ssl/

# Restart nginx
docker compose up -d nginx
```

### Option B: Cloudflare (Zero config SSL)

Point your domain to Cloudflare and enable "Full (strict)" SSL mode.

## Scaling

### Horizontal Scaling (Multiple API Instances)

```yaml
# In docker-compose.prod.yml
api:
  deploy:
    replicas: 3
```

### Vertical Scaling

Increase container resources:
```yaml
api:
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 4G
```

## Monitoring

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
```

### Health Checks

```bash
# Check all service health
docker compose ps

# API health
curl http://localhost/health
```

## Backup

### Database

```bash
docker compose exec db pg_dump -U nexus nexus > backup.sql
```

### Restore

```bash
docker compose exec -T db psql -U nexus nexus < backup.sql
```

## Troubleshooting

### Services not starting

```bash
# Check logs
docker compose logs api

# Rebuild
docker compose build --no-cache api
docker compose up -d
```

### Database connection issues

```bash
# Check if db is healthy
docker compose exec db pg_isready -U nexus

# Reset database (WARNING: destroys data)
docker compose down -v
docker compose up -d
```
