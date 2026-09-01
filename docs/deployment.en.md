# mchat Deployment Guide

## Docker Deployment (Recommended)

### Prerequisites

- Docker >= 24.0
- Docker Compose >= 2.0
- At least 4GB of available memory (8GB+ if Milvus is enabled)

### 1. Clone the project

```bash
git clone https://github.com/your-org/mchat.git
cd mchat
```

### 2. Configure environment variables

```bash
cp ops/docker/.env.example ops/docker/.env
```

Edit `ops/docker/.env` and change at least the following values:

```bash
# Required
MYSQL_ROOT_PASSWORD=your_secure_password
MYSQL_PASSWORD=your_secure_password
JWT_SECRET=your_random_secret_at_least_32_chars
ADMIN_PASSWORD=your_admin_password

# Optional: disable the knowledge base if you do not need it
MILVUS_DISABLED=true
```

### 3. Start services

```bash
# Full stack start (MySQL + Milvus + Redis + Backend + Frontend)
docker compose -f ops/docker/docker-compose.yml up -d

# Or use the Makefile
make docker-up
```

### 4. Access

- Admin console: `http://localhost:5173/admin`
- API docs (Swagger): `http://localhost:3001/docs`
- Health check: `http://localhost:3001/api/health`

### 5. Initial administrator

Default administrator account (configured in `.env`):
- Username: `ADMIN_USERNAME` (default `admin`)
- Password: `ADMIN_PASSWORD` (the password you set)

**Change the password immediately after the first login.**

---

## Production Deployment

### Environment preparation

```bash
# Server requirements
- OS: Ubuntu 22.04+ / Debian 12+
- CPU: 4 cores+
- RAM: 8GB+ (with Milvus)
- Disk: 50GB+ SSD
```

### Docker Compose production configuration

```bash
# 1. Create production env file
cp ops/docker/.env.production.example ops/docker/.env.production
# Edit .env.production with production values

# 2. Start production services
docker compose -f ops/docker/docker-compose.prod.yml --env-file ops/docker/.env.production up -d
```

> **Security note for upgrades:** Older channel-rental versions may have copied
> platform or template AI keys into tenant configs. The first production startup
> removes copies it can identify, but an older API may already have returned the
> plaintext. Rotate every provider key that was previously used as a platform or
> template default after upgrading.

### Nginx reverse proxy (recommended)

```nginx
server {
    listen 80;
    server_name mchat.example.com;

    # Frontend
    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket
    location /ws {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Uploaded files
    location /uploads/ {
        proxy_pass http://127.0.0.1:3001;
    }
}
```

### HTTPS configuration

```bash
# Use certbot to obtain a free SSL certificate
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d mchat.example.com
```

---

## Manual Deployment (Development Environment)

### Prerequisites

- Python >= 3.12
- Node.js >= 20
- MySQL 8.0+
- Milvus (optional)

### 1. Backend

```bash
cd src/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env

# Initialize database
python -c "from app.core.database import engine, Base; import app.models; Base.metadata.create_all(bind=engine)"

# Start backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 3001
```

### 2. Frontend

```bash
cd src/frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

### 3. Start everything together

```bash
# Using Makefile
make install
make dev
```

---

## Environment Variable Reference

| Variable | Description | Default |
|------|------|--------|
| `DATABASE_URL` | MySQL connection string | `mysql://...` |
| `JWT_SECRET` | JWT signing secret | required |
| `JWT_EXPIRE_MINUTES` | Token expiration in minutes | `10080` (7 days) |
| `SERVER_HOST` | Listen address | `0.0.0.0` |
| `SERVER_PORT` | Listen port | `3001` |
| `ADMIN_USERNAME` | Default admin username | `admin` |
| `ADMIN_PASSWORD` | Default admin password | required |
| `MILVUS_HOST` | Milvus host | `localhost` |
| `MILVUS_PORT` | Milvus port | `19530` |
| `MILVUS_DISABLED` | Disable Milvus | `false` |
| `EMBEDDING_PROVIDER` | Embedding provider | `openai` |
| `EMBEDDING_MODEL` | Embedding model name | `text-embedding-3-small` |
| `REDIS_URL` | Redis connection | optional |

---

## Backup and Restore

### Database backup

```bash
# MySQL backup
docker exec mchat-mysql mysqldump -u mchat -p mchat > backup_$(date +%Y%m%d).sql

# Uploaded files backup
tar -czf uploads_backup_$(date +%Y%m%d).tar.gz src/backend/uploads/
```

### Restore

```bash
# MySQL restore
docker exec -i mchat-mysql mysql -u mchat -p mchat < backup.sql

# Uploaded files restore
tar -xzf uploads_backup.tar.gz -C src/backend/uploads/
```

---

## Monitoring

- API health check: `GET /api/health`
- Basic metrics: `GET /api/health/metrics`
- Docker container status: `docker compose -f ops/docker/docker-compose.yml ps`
- Logs: `docker compose -f ops/docker/docker-compose.yml logs -f backend`
