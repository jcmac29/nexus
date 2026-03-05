# Deploying Nexus to DigitalOcean

## Quick Start (15 minutes)

### 1. Create a Droplet

**Recommended Specs:**
- **Size:** 2GB RAM / 1 vCPU ($18/month) for testing, 4GB RAM / 2 vCPU ($24/month) for production
- **Image:** Ubuntu 24.04 LTS
- **Region:** Choose closest to your users
- **Add SSH key:** Required for secure access

```bash
# Or use the CLI
doctl compute droplet create nexus \
  --size s-2vcpu-4gb \
  --image ubuntu-24-04-x64 \
  --region nyc3 \
  --ssh-keys YOUR_SSH_KEY_ID
```

### 2. Connect to Your Droplet

```bash
ssh root@YOUR_DROPLET_IP
```

### 3. Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose
apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

### 4. Clone and Configure Nexus

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/nexus.git
cd nexus

# Create environment file
cp .env.example .env

# Generate secure secrets
openssl rand -base64 32  # Use for SECRET_KEY
openssl rand -base64 32  # Use for ADMIN_JWT_SECRET
openssl rand -base64 24  # Use for DB_PASSWORD
openssl rand -base64 32  # Use for STORAGE_SECRET_KEY

# Edit the .env file with your values
nano .env
```

### 5. Deploy

```bash
# Run the deployment script
./deploy/deploy.sh init

# Or manually:
docker compose -f docker-compose.prod.yml up -d
```

### 6. Create Admin User

```bash
docker compose -f docker-compose.prod.yml exec api python -c "
from nexus.admin.service import AdminService
from nexus.database import get_sync_session
import asyncio

async def create_admin():
    async for db in get_sync_session():
        service = AdminService(db)
        admin = await service.create_admin(
            email='admin@yourdomain.com',
            password='your-secure-password',
            name='Admin'
        )
        print(f'Admin created: {admin.email}')
        await db.commit()

asyncio.run(create_admin())
"
```

### 7. Point Your Domain

1. In your DNS provider, create an A record:
   - `@` → YOUR_DROPLET_IP
   - `www` → YOUR_DROPLET_IP

2. Wait for DNS propagation (5-30 minutes)

### 8. Enable SSL (Optional but Recommended)

```bash
# Install Certbot
apt install certbot python3-certbot-nginx -y

# Stop nginx container temporarily
docker compose -f docker-compose.prod.yml stop nginx

# Get certificate
certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# Copy certificates to deploy directory
mkdir -p deploy/nginx/ssl
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem deploy/nginx/ssl/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem deploy/nginx/ssl/

# Restart nginx
docker compose -f docker-compose.prod.yml start nginx
```

---

## Service URLs

After deployment, your services will be available at:

| Service | URL |
|---------|-----|
| Landing Page | http://your-domain.com/ |
| User Dashboard | http://your-domain.com/dashboard |
| Admin Dashboard | http://your-domain.com/admin |
| API | http://your-domain.com/api/v1 |
| API Docs | http://your-domain.com/docs |
| Playground | http://your-domain.com/playground |
| Health Check | http://your-domain.com/health |

---

## Management Commands

```bash
# View logs
docker compose -f docker-compose.prod.yml logs -f

# View specific service logs
docker compose -f docker-compose.prod.yml logs -f api

# Restart a service
docker compose -f docker-compose.prod.yml restart api

# Stop all services
docker compose -f docker-compose.prod.yml down

# Update to latest version
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# Run database migrations
docker compose -f docker-compose.prod.yml exec api alembic upgrade head

# Access database
docker compose -f docker-compose.prod.yml exec db psql -U nexus
```

---

## Monitoring

### Check Service Health

```bash
# All services
docker compose -f docker-compose.prod.yml ps

# API health
curl http://localhost/health

# Detailed health
curl http://localhost/api/v1/health/detailed
```

### Resource Usage

```bash
# Container stats
docker stats

# Disk usage
df -h
docker system df
```

---

## Backups

### Database Backup

```bash
# Create backup
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U nexus nexus > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore backup
cat backup_XXXXXXXX_XXXXXX.sql | docker compose -f docker-compose.prod.yml exec -T db \
  psql -U nexus nexus
```

### Automated Backups (Cron)

```bash
# Edit crontab
crontab -e

# Add daily backup at 3am
0 3 * * * cd /root/nexus && docker compose -f docker-compose.prod.yml exec -T db pg_dump -U nexus nexus > /root/backups/nexus_$(date +\%Y\%m\%d).sql
```

---

## Scaling

### Vertical Scaling (Bigger Droplet)

```bash
# Resize via DigitalOcean dashboard or CLI
doctl compute droplet-action resize YOUR_DROPLET_ID --size s-4vcpu-8gb
```

### Horizontal Scaling (Multiple Droplets)

For high availability, consider:
1. **Load Balancer:** DigitalOcean Load Balancer ($12/month)
2. **Managed Database:** DigitalOcean Managed PostgreSQL ($15/month)
3. **Managed Redis:** DigitalOcean Managed Redis ($15/month)

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose -f docker-compose.prod.yml logs api

# Check if port is in use
netstat -tlnp | grep 80

# Rebuild
docker compose -f docker-compose.prod.yml build --no-cache
```

### Database Connection Issues

```bash
# Check if database is running
docker compose -f docker-compose.prod.yml ps db

# Check database logs
docker compose -f docker-compose.prod.yml logs db

# Test connection
docker compose -f docker-compose.prod.yml exec db pg_isready -U nexus
```

### Out of Memory

```bash
# Check memory usage
free -h

# Add swap (if needed)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

---

## Security Checklist

- [ ] SSH key authentication (disable password login)
- [ ] UFW firewall enabled (ports 22, 80, 443 only)
- [ ] SSL/TLS certificates installed
- [ ] Strong passwords in .env file
- [ ] Regular backups configured
- [ ] Fail2ban installed
- [ ] Automatic security updates enabled

```bash
# Enable firewall
ufw allow 22
ufw allow 80
ufw allow 443
ufw enable

# Enable automatic updates
apt install unattended-upgrades -y
dpkg-reconfigure -plow unattended-upgrades
```

---

## Cost Estimate

| Resource | Monthly Cost |
|----------|-------------|
| Droplet (4GB/2vCPU) | $24 |
| Backups (20%) | $4.80 |
| **Total** | **$28.80/month** |

Optional add-ons:
- Load Balancer: +$12/month
- Managed Database: +$15/month
- Spaces (S3 storage): +$5/month
