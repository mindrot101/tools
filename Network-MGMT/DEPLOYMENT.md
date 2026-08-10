# Deployment Guide

## Production Deployment

### Prerequisites
- Docker and Docker Compose installed
- Domain name and SSL certificate
- Production-grade PostgreSQL (optional, can use the included one)
- Reverse proxy (Nginx, Apache, or cloud load balancer)

### Step 1: Environment Configuration

Create a production `.env` file:

```bash
# Database
POSTGRES_PASSWORD=<strong-random-password>
POSTGRES_DB=network_mgmt
POSTGRES_USER=network_user

# JWT
JWT_SECRET=<strong-random-secret-minimum-32-characters>

# Network Discovery
DISCOVERY_NETWORK=192.168.1.0/24

# Application
NODE_ENV=production
PORT=3000
```

### Step 2: Security Hardening

1. **Change default admin password**
   ```bash
   docker compose exec backend node -e "
     const bcrypt = require('bcryptjs');
     const { User } = require('./models');
     bcrypt.hash('new-secure-password', 10).then(hash => 
       User.update({ password_hash: hash }, { where: { username: 'admin' } })
     )
   "
   ```

2. **Enable HTTPS** (using Nginx as reverse proxy)

   Create `/etc/nginx/sites-available/network-mgmt`:
   ```nginx
   server {
       listen 80;
       server_name network.yourdomain.com;
       return 301 https://$server_name$request_uri;
   }

   server {
       listen 443 ssl http2;
       server_name network.yourdomain.com;

       ssl_certificate /etc/letsencrypt/live/network.yourdomain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/network.yourdomain.com/privkey.pem;

       location / {
           proxy_pass http://localhost:80;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

3. **Firewall Configuration**
   ```bash
   # Only expose necessary ports
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw deny 5432/tcp  # Block direct database access
   ufw deny 6379/tcp  # Block direct Redis access
   ```

### Step 3: Docker Compose Production Configuration

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: network_mgmt
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/init:/docker-entrypoint-initdb.d
    networks:
      - network-mgmt-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    networks:
      - network-mgmt-net
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      - NODE_ENV=production
      - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/network_mgmt
      - REDIS_URL=redis://redis:6379
      - DISCOVERY_NETWORK=${DISCOVERY_NETWORK}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - network-mgmt-net
    command: ["node", "worker.js"]

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    restart: unless-stopped
    depends_on:
      - backend
    networks:
      - network-mgmt-net

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/prod.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - frontend
      - backend
    networks:
      - network-mgmt-net

networks:
  network-mgmt-net:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
```

### Step 4: Deploy

```bash
# Build and start all services
docker compose -f docker-compose.prod.yml up -d --build

# Check status
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f
```

### Step 5: SSL Certificate (Let's Encrypt)

```bash
# Install certbot
apt-get update
apt-get install certbot python3-certbot-nginx

# Obtain certificate
certbot --nginx -d network.yourdomain.com

# Auto-renewal is set up automatically
```

## Monitoring and Logging

### Application Logs
```bash
# View all logs
docker compose logs -f

# View specific service logs
docker compose logs -f backend
docker compose logs -f frontend
```

### System Monitoring
```bash
# Check resource usage
docker stats

# Check container health
docker inspect --format='{{.State.Health.Status}}' network-mgmt-backend
```

### Database Backup
```bash
# Backup database
docker compose exec postgres pg_dump -U network_user network_mgmt > backup_$(date +%Y%m%d).sql

# Restore database
docker compose exec -T postgres psql -U network_user network_mgmt < backup_20240806.sql
```

## Scaling

### Horizontal Scaling

For high availability, you can run multiple backend instances:

```yaml
backend:
  image: your-registry/network-mgmt-backend:latest
  deploy:
    replicas: 3
  environment:
    - NODE_ENV=production
  # ... other config
```

Note: You'll need a load balancer (Nginx, HAProxy, or cloud LB) to distribute traffic.

## Updates

### Zero-Downtime Updates

```bash
# Pull latest images
docker compose -f docker-compose.prod.yml pull

# Update services
docker compose -f docker-compose.prod.yml up -d

# Remove old containers
docker compose -f docker-compose.prod.yml down
```

## Troubleshooting

### Common Issues

1. **Database connection failed**
   ```bash
   docker compose exec postgres pg_isready -U network_user
   ```

2. **Backend not starting**
   ```bash
   docker compose logs backend
   docker compose exec backend node -e "console.log('Test')"
   ```

3. **Frontend not loading**
   ```bash
   docker compose logs frontend
   docker compose exec frontend ls -la /usr/share/nginx/html
   ```

4. **Discovery not working**
   - Check firewall rules
   - Verify SNMP community strings
   - Test network connectivity

### Debug Mode

```bash
# Enable debug logging
export DEBUG=network-mgmt:*
docker compose logs -f
```

## Performance Tuning

### Database Optimization
```sql
-- Create indexes
CREATE INDEX idx_devices_ip ON devices(ip_address);
CREATE INDEX idx_devices_status ON devices(status);
CREATE INDEX idx_devices_vendor ON devices(vendor);
CREATE INDEX idx_monitoring_timestamp ON monitoring_results(timestamp);
```

### Redis Configuration
```bash
# Increase maxmemory
docker compose exec redis redis-cli CONFIG SET maxmemory 256mb
docker compose exec redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

## Security Checklist

- [ ] Changed default admin password
- [ ] Enabled HTTPS with valid SSL certificate
- [ ] Configured firewall rules
- [ ] Set strong JWT_SECRET
- [ ] Regular security updates
- [ ] Database backups configured
- [ ] Monitor logs for suspicious activity
- [ ] Use secrets management for production
- [ ] Enable rate limiting on API endpoints
- [ ] Configure CORS properly

## Support

For production support and enterprise features, contact: support@network-mgmt.example.com