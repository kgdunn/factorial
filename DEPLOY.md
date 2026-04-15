# Deployment Guide: Agentic DOE App on Hetzner VPS

Deploy the monorepo (FastAPI + SvelteKit + PostgreSQL + Neo4j) to a Hetzner CX32 VPS (4 vCPU, 8GB RAM, Ubuntu 24.04). All services are containerized via `docker-compose.yml`.

**Architecture overview:**

```
Browser ──► Caddy (:80/:443) ──┬──► Frontend (nginx :3000) ──► SvelteKit SPA
                                └──► Backend (uvicorn :8000) ──► FastAPI
                                         │          │
                                    PostgreSQL    Neo4j
                                     (:5432)    (:7474/:7687)
```

---

## Phase 1: VPS Initial Setup

### 1.1 — SSH into the VPS

```bash
ssh root@<YOUR_HETZNER_IP>
```

Replace `<YOUR_HETZNER_IP>` with the IP from the Hetzner Cloud Console.

### 1.2 — Update the system

```bash
apt update && apt upgrade -y
```

### 1.3 — Create a non-root deploy user

```bash
adduser deploy
usermod -aG sudo deploy
```

### 1.4 — Set up SSH key access for the deploy user

```bash
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

Verify from your **local machine**:

```bash
ssh deploy@<YOUR_HETZNER_IP>
```

### 1.5 — Disable root SSH login

```bash
sudo sed -i 's/^PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/^#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd
```

### 1.6 — Configure the firewall

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp     # SSH
sudo ufw allow 80/tcp     # HTTP
sudo ufw allow 443/tcp    # HTTPS (for later)
sudo ufw enable
sudo ufw status
```

> **Note:** Database ports (5432, 7474, 7687) are NOT opened in UFW. The `docker-compose.yml` binds them to `127.0.0.1` so they are only accessible from the server itself.

---

## Phase 2: Install Docker

### 2.1 — Install Docker Engine

```bash
sudo apt install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 2.2 — Add deploy user to docker group

```bash
sudo usermod -aG docker deploy
```

**Log out and back in** for the group change to take effect:

```bash
exit
ssh deploy@<YOUR_HETZNER_IP>
```

### 2.3 — Verify

```bash
docker --version
docker compose version
docker run hello-world
```

Clean up:

```bash
docker rm $(docker ps -aq) 2>/dev/null
docker rmi hello-world 2>/dev/null
```

---

## Phase 3: Clone the Repository

### 3.1 — Clone and enter the repo

```bash
sudo apt install -y git
cd /home/deploy
git clone https://github.com/kgdunn/agentic-experimental-design-and-analysis.git
cd agentic-experimental-design-and-analysis
```

> If the repo is private, set up a GitHub deploy key or personal access token first.

### 3.2 — Checkout the target branch

```bash
git checkout main
```

---

## Phase 4: Create the Production `.env` File

### 4.1 — Copy the template

```bash
cp .env.example .env
```

### 4.2 — Generate strong passwords

```bash
openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32; echo
openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32; echo
```

### 4.3 — Edit with production values

```bash
nano .env
```

Set these values (replace placeholders):

```env
# Application
APP_ENV=production
APP_DEBUG=false
APP_HOST=0.0.0.0
APP_PORT=8000

# PostgreSQL
POSTGRES_USER=doe_user
POSTGRES_PASSWORD=<PASTE_FIRST_GENERATED_PASSWORD>
POSTGRES_DB=doe_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<PASTE_SECOND_GENERATED_PASSWORD>

# CORS — your server IP (update when you add a domain)
CORS_ORIGINS=http://<YOUR_HETZNER_IP>

# Frontend API URL
PUBLIC_API_URL=http://<YOUR_HETZNER_IP>
```

### 4.4 — Lock down permissions

```bash
chmod 600 .env
```

---

## Phase 5: Security — Port Bindings

The `docker-compose.yml` already binds database ports to `127.0.0.1` (localhost only), preventing direct internet access to PostgreSQL and Neo4j even if UFW is misconfigured.

Verify by checking `docker-compose.yml`:

```yaml
# These should all start with "127.0.0.1:"
postgres:
  ports:
    - "127.0.0.1:5432:5432"

neo4j:
  ports:
    - "127.0.0.1:7474:7474"
    - "127.0.0.1:7687:7687"
```

The backend (`app`) and frontend services also bind to `127.0.0.1` — all external traffic goes through Caddy (set up in Phase 9).

> **Do NOT use `docker-compose.override.yml`** for port changes. Docker Compose *merges* (concatenates) list fields like `ports` from overrides, creating duplicate bindings that cause "address already in use" errors.

---

## Phase 6: Build & Start All Services

### 6.0 — Check for port conflicts

```bash
sudo ss -tlnp | grep -E ':(8000|3000|5432|7474|7687)\b'
```

If anything is listening, stop it:

| Cause | Fix |
|-------|-----|
| Standalone Neo4j | `sudo systemctl stop neo4j && sudo systemctl disable neo4j` |
| Standalone PostgreSQL | `sudo systemctl stop postgresql && sudo systemctl disable postgresql` |
| Previous Docker attempt | `docker compose down --remove-orphans` |
| Ghost Docker state (ss shows nothing but Docker says "in use") | See 6.0a below |

### 6.0a — Fix ghost Docker state

If `ss` shows nothing but Docker still reports port conflicts:

```bash
docker compose down --remove-orphans
docker container prune -f
docker network prune -f
sudo systemctl restart docker
sleep 5
```

### 6.1 — Build and launch

```bash
docker compose up --build -d
```

First build takes **3-8 minutes** (downloading base images + installing dependencies).

### 6.2 — Verify all containers are running

```bash
docker compose ps
```

All 4 services should show **Up** (databases should show **healthy**).

### 6.3 — Check logs

```bash
docker compose logs app        # Backend
docker compose logs postgres   # PostgreSQL
docker compose logs neo4j      # Neo4j
docker compose logs frontend   # Frontend/nginx
```

**Expected:**
- postgres: "database system is ready to accept connections"
- neo4j: "Started." or "Bolt enabled"
- app: "Uvicorn running on http://0.0.0.0:8000"
- frontend: nginx startup (no errors)

### 6.4 — If backend crashes on startup

Databases may need more time. Wait 30-60s, then:

```bash
docker compose restart app
```

---

## Phase 7: Run Database Migrations

```bash
docker compose exec app uv run alembic upgrade head
```

> Currently the `alembic/versions/` directory is empty. This command succeeds but does nothing. Re-run after each deployment when migrations are added.

---

## Phase 8: Verify the Deployment

### 8.1 — Backend API

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
curl -s http://localhost:8000/docs | head -20
```

### 8.2 — Databases

```bash
docker compose exec postgres psql -U doe_user -d doe_db -c "SELECT version();"
docker compose exec neo4j cypher-shell -u neo4j -p '<YOUR_NEO4J_PASSWORD>' "RETURN 1"
```

---

## Phase 9: Set Up Caddy Reverse Proxy

Caddy provides a single entry point (port 80) for both frontend and API, and automatic HTTPS when you add a domain.

### 9.1 — Install Caddy

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

### 9.2 — Configure Caddy (HTTP, by IP address)

```bash
sudo tee /etc/caddy/Caddyfile << 'EOF'
:80 {
    handle /api/* {
        reverse_proxy localhost:8000
    }
    handle /docs* {
        reverse_proxy localhost:8000
    }
    handle /openapi.json {
        reverse_proxy localhost:8000
    }
    handle {
        reverse_proxy localhost:3000
    }
}
EOF
```

### 9.3 — Start Caddy

```bash
sudo systemctl restart caddy
sudo systemctl enable caddy
sudo systemctl status caddy
```

### 9.4 — Update .env for Caddy

Now everything is on port 80. Edit `.env`:

```env
CORS_ORIGINS=http://<YOUR_HETZNER_IP>
PUBLIC_API_URL=http://<YOUR_HETZNER_IP>
```

```bash
docker compose restart app
```

### 9.5 — Test

From your browser:

- **Frontend:** `http://<YOUR_HETZNER_IP>/`
- **API docs:** `http://<YOUR_HETZNER_IP>/docs`
- **API health:** `http://<YOUR_HETZNER_IP>/api/v1/health`

---

## Phase 10: Enable HTTPS (When You Have a Domain)

### 10.1 — Set DNS

At your domain registrar, create an A record:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | `@` or subdomain | `<YOUR_HETZNER_IP>` | 300 |

Verify: `dig yourdomain.com`

### 10.2 — Update the Caddyfile

```bash
sudo tee /etc/caddy/Caddyfile << 'EOF'
yourdomain.com {
    handle /api/* {
        reverse_proxy localhost:8000
    }
    handle /docs* {
        reverse_proxy localhost:8000
    }
    handle /openapi.json {
        reverse_proxy localhost:8000
    }
    handle {
        reverse_proxy localhost:3000
    }
}
EOF

sudo systemctl restart caddy
```

Caddy **automatically** obtains and renews Let's Encrypt certificates.

### 10.3 — Update .env

```env
CORS_ORIGINS=https://yourdomain.com
PUBLIC_API_URL=https://yourdomain.com
```

```bash
docker compose restart app
```

---

## Phase 11: Auto-Restart & Monitoring

### 11.1 — Enable Docker on boot

```bash
sudo systemctl enable docker
```

### 11.2 — Container restart policies

The `docker-compose.yml` already includes `restart: unless-stopped` on all services. Containers will auto-restart after server reboots.

### 11.3 — Docker log rotation

```bash
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF

sudo systemctl restart docker
cd /home/deploy/agentic-experimental-design-and-analysis
docker compose up -d
```

### 11.4 — Automatic security updates

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## Phase 12: Redeployment

When updating the running server with new code:

```bash
ssh deploy@<YOUR_HETZNER_IP>
cd /home/deploy/agentic-experimental-design-and-analysis

git pull origin main
docker compose up --build -d
docker compose exec app uv run alembic upgrade head

docker compose ps
docker compose logs -f app --tail=50
```

---

## Phase 13: Backups

### PostgreSQL

```bash
# Backup:
docker compose exec postgres pg_dump -U doe_user doe_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore:
cat backup_YYYYMMDD_HHMMSS.sql | docker compose exec -T postgres psql -U doe_user doe_db
```

### Neo4j

```bash
docker compose stop neo4j
docker run --rm \
  -v agentic-experimental-design-and-analysis_neo4j_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/neo4j_backup_$(date +%Y%m%d).tar.gz /data
docker compose start neo4j
```

### Automated daily backup (cron)

```bash
mkdir -p /home/deploy/backups
crontab -e
```

Add:

```cron
0 3 * * * cd /home/deploy/agentic-experimental-design-and-analysis && docker compose exec -T postgres pg_dump -U doe_user doe_db | gzip > /home/deploy/backups/pg_$(date +\%Y\%m\%d).sql.gz 2>/dev/null
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Start all services | `docker compose up -d` |
| Stop all services | `docker compose down` |
| Rebuild and restart | `docker compose up --build -d` |
| View all logs | `docker compose logs` |
| Follow backend logs | `docker compose logs -f app` |
| Check service health | `docker compose ps` |
| Run migrations | `docker compose exec app uv run alembic upgrade head` |
| Restart one service | `docker compose restart app` |
| Shell into backend | `docker compose exec app bash` |
| Shell into postgres | `docker compose exec postgres psql -U doe_user doe_db` |
| Disk usage | `docker system df` |
| Clean unused images | `docker image prune -f` |
| Full cleanup (DANGER) | `docker compose down -v --remove-orphans` |

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Backend crashes on startup | Database not ready | `docker compose restart app` after 30s |
| "Connection refused" to API | Backend not running | `docker compose ps` + `docker compose logs app` |
| Frontend shows blank page | SvelteKit build failed | `docker compose logs frontend` |
| Neo4j "unhealthy" | Slow startup (30s+) | Wait, check `docker compose logs neo4j` |
| Can't connect from browser | UFW blocking port | `sudo ufw status` — port 80 must be open |
| "CORS error" in browser | CORS_ORIGINS mismatch | Update `.env`, then `docker compose restart app` |
| "address already in use" | Ghost Docker state | `docker compose down --remove-orphans && sudo systemctl restart docker` |
| Docker build OOM | Not enough RAM | `free -h` — CX32 (8GB) should be fine |
| Disk full | Docker images/logs | `docker system prune -f` |
