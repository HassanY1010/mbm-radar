# MBM Radar - Production Deployment Guide

This guide explains how to deploy **MBM Radar** to a cloud VPS or dedicated server (e.g., DigitalOcean, AWS, Linode) running Ubuntu 22.04 LTS or newer.

---

## Prerequisites

Ensure the following tools are installed on your server:
- **Docker Engine** (version 24.0.0 or higher)
- **Docker Compose V2**
- **Git**

To install Docker on Ubuntu, run:
```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
```

---

## Step 1: Clone the Codebase and Configure Environment

1. Clone the project repository to your VPS:
   ```bash
   git clone <your-repository-url> /opt/mbm_radar
   cd /opt/mbm_radar
   ```

2. Create the production `.env` file from the template:
   ```bash
   cp .env.example .env
   ```

3. Open `.env` and fill in the values:
   - Make sure `DATABASE_URL` uses the container hostname: `postgresql+asyncpg://postgres:secure_db_pass@db:5432/mbm_radar`
   - Make sure `REDIS_URL` matches the container hostname: `redis://redis:6379/0`
   - Input your actual **Telegram Bot Token** and **Private Channel ID** (ID starts with `-100`).
   - Input your **FMP API Key**.
   - Input your **Admin Telegram Chat ID** to grant full access to the admin panel.

---

## Step 2: Deploy Containers

Start the stack in detached daemon mode:
```bash
docker compose up --build -d
```

This starts:
- **db (Postgres)**: Exposed locally on `5432` with persistent data.
- **redis**: Exposed locally on `6379` caching alert timestamps.
- **app (FastAPI + Bot + Scanner)**: Automatically runs migrations, initializes default plans, starts Telegram polling handlers, and bootstraps market scanners.
- **nginx (Proxy)**: Routes web requests and WebSockets securely.

Verify that all services are running:
```bash
docker compose ps
```

---

## Step 3: Configure SSL/HTTPS with Nginx

To secure connections and support HTTPS:
1. Update `docker-compose.yml` to map your local certificate directories to Nginx cert folders:
   ```yaml
   nginx:
     ...
     volumes:
       - ./docker/nginx.conf:/etc/nginx/nginx.conf:ro
       - /etc/letsencrypt:/etc/nginx/certs:ro
   ```
2. Modify `docker/nginx.conf` to enable SSL port 443 with your Let's Encrypt certificates.

---

## Step 4: Maintenance & Operational Management

### Database Backups (Manual & Scheduled)
To perform a manual database backup:
- Open the Telegram Bot, navigate to `👑 لوحة الإدارة` -> `💾 النسخ الاحتياطي`.
- If running PostgreSQL inside docker, you can run a dump command:
  ```bash
  docker exec -t mbm_radar_db pg_dumpall -c -U postgres > backup.sql
  ```

### Restore Database
To restore database states from a SQL backup dump:
```bash
cat backup.sql | docker exec -i mbm_radar_db psql -U postgres
```

### Viewing Logs
View active logging outputs of all containers:
```bash
docker compose logs -f
```

View application logs directly:
```bash
docker compose exec app tail -f /app/logs/app.log
```
