# Deployment Guide: Agentic DOE App

The production instance of this application runs at **[factori.al](https://factori.al)**. The instructions below are written generically so you can deploy to your own domain.

Deploy the monorepo (FastAPI + SvelteKit + PostgreSQL + Neo4j) to any Linux VPS or cloud server running Ubuntu 24.04. Recommended minimum: 4 vCPU, 8GB RAM. All services are containerized via `docker-compose.yml`.

**Architecture overview:**

```
Browser ──► Caddy (:80/:443) ──┬──► Frontend (nginx :3000) ──► SvelteKit SPA
                               └──► Backend (uvicorn :8000) ──► FastAPI
                                        │          │
                                   PostgreSQL    Neo4j
                                    (:5432)    (:7474/:7687)
```

---

## Phase 1: Server Initial Setup

### 1.1 — SSH into the server

```bash
ssh root@<YOUR_SERVER_IP>
```

Replace `<YOUR_SERVER_IP>` with the public IP address of your server.

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
ssh deploy@<YOUR_SERVER_IP>
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
ssh deploy@<YOUR_SERVER_IP>
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
sudo apt install -y git make
cd /home/deploy
git clone https://github.com/kgdunn/agentic-doe.git
cd agentic-doe
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

# Security — API key for machine-to-machine authentication
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
API_SECRET_KEY=<GENERATE_A_RANDOM_SECRET>

# JWT Authentication
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(64))"
JWT_SECRET_KEY=<GENERATE_A_RANDOM_SECRET>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS — your server IP or domain (update when you add a domain)
CORS_ORIGINS=http://<YOUR_SERVER_IP>

# Admin / Signup approval
# ADMIN_EMAILS: comma-separated emails of users who can approve signups and receive
# notifications of pending requests. If empty, nobody can approve new signups.
ADMIN_EMAILS=you@example.com

# How long an invite link (emailed to an approved user to finish registration) stays valid.
INVITE_TOKEN_EXPIRE_HOURS=72

# FRONTEND_URL: public origin users load in their browser. Embedded in outgoing
# emails (approval links, invite links, share links) — if wrong, those links break.
# Behind Caddy, use the same origin as PUBLIC_API_URL below (no port).
# Swap to https://yourdomain.com once a domain is set up in Phase 10.
FRONTEND_URL=http://<YOUR_SERVER_IP>

# PUBLIC_API_URL: public origin the browser uses to reach the API. Caddy fronts
# both frontend and backend on port 80/443 and routes /api to the backend — so
# no port here. Swap to https://yourdomain.com once a domain is set up in Phase 10.
# (Leave as http://localhost:8000 only for local dev without Caddy.)
PUBLIC_API_URL=http://<YOUR_SERVER_IP>
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

> **Note:** PostgreSQL and Neo4j run **inside Docker containers**, not on the VPS host. There is no `psql` or `cypher-shell` binary on the VPS itself — running `psql` directly at the shell will fail with `command not found`. Always invoke them via `docker compose exec <service> ...` as shown below. This also means you don't need to install the `postgresql-client` or `cypher-shell` packages on the host.

```bash
docker compose exec postgres psql -U doe_user -d doe_db -c "SELECT version();"
docker compose exec neo4j cypher-shell -u neo4j -p '<YOUR_NEO4J_PASSWORD>' "RETURN 1"
```

To open an interactive `psql` session, drop the `-c "..."`:

```bash
docker compose exec postgres psql -U doe_user -d doe_db
# at the postgres=# prompt, \q to exit
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

This is an HTTP-only setup for use **before you have a domain**. Caddy will listen on port 80 only; port 443 (HTTPS) stays closed until you complete Phase 10 with a real domain name, at which point Caddy auto-provisions a Let's Encrypt certificate.

Use `127.0.0.1` (not `localhost`) in the `reverse_proxy` targets. Caddy resolves `localhost` to IPv6 `::1` first, but the Docker services bind to IPv4 `127.0.0.1` only — the mismatch produces `dial tcp [::1]:3000: connect: connection refused` errors in the Caddy log.

```bash
sudo tee /etc/caddy/Caddyfile << 'EOF'
:80 {
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /docs* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /openapi.json {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        reverse_proxy 127.0.0.1:3000
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
CORS_ORIGINS=http://<YOUR_SERVER_IP>
FRONTEND_URL=http://<YOUR_SERVER_IP>
PUBLIC_API_URL=http://<YOUR_SERVER_IP>
```

```bash
docker compose restart app
```

### 9.5 — Test

From your browser:

- **Frontend:** `http://<YOUR_SERVER_IP>/`
- **API docs:** `http://<YOUR_SERVER_IP>/docs`
- **API health:** `http://<YOUR_SERVER_IP>/api/v1/health`

---

## Phase 10: Enable HTTPS (When You Have a Domain)

### 10.1 — Set DNS

At your domain registrar, create an A record:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | `@` or subdomain | `<YOUR_SERVER_IP>` | 300 |

Verify: `dig yourdomain.com` (for the canonical deployment, the domain is `factori.al`)

### 10.2 — Update the Caddyfile

Replace `yourdomain.com` with your real domain (e.g. `factori.al`). As soon as Caddy sees a domain name as the site address, it will obtain a Let's Encrypt certificate and start listening on port 443.

```bash
sudo tee /etc/caddy/Caddyfile << 'EOF'
yourdomain.com {
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /docs* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /openapi.json {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
EOF

sudo systemctl reload caddy
sudo journalctl -u caddy -f   # watch for "certificate obtained successfully"
```

Caddy **automatically** obtains and renews Let's Encrypt certificates. Verify both ports are now listening:

```bash
sudo ss -tlnp | grep -E ':(80|443)\b'   # should show both
curl -I https://yourdomain.com          # should return 200
```

If cert provisioning fails, the most common causes are: port 80 not reachable from the public internet (check UFW / cloud firewall), or the DNS A record hasn't propagated yet (`dig yourdomain.com` should return your VPS IP).

### 10.3 — Update .env

```env
CORS_ORIGINS=https://yourdomain.com
FRONTEND_URL=https://yourdomain.com
PUBLIC_API_URL=https://yourdomain.com
```

```bash
docker compose restart app
```

---

## Phase 11: Bootstrap the First Admin User

The app is **invite-only**: `POST /auth/register` is disabled in code, and new users can only register via an invite token issued by an existing admin. This creates a chicken-and-egg problem for the very first deploy — there is no admin yet, so no one can approve the first signup.

The one-time workaround is to submit a normal signup request and then approve the DB row manually. You only need to do this once per deployment; after that, use the admin UI at `/admin/signups`.

### 11.1 — Confirm your admin email is set

In `.env`, `ADMIN_EMAILS` must contain the email you are about to use. Emails are matched case-insensitively. If you just edited it, restart the backend:

```bash
docker compose restart app
```

### 11.2 — Submit a signup request

In your browser, go to `https://yourdomain.com` (or the IP), click through to the signup form, and submit a request using the exact email you listed in `ADMIN_EMAILS`. The use-case text can be anything.

### 11.3 — Approve the row manually

PostgreSQL runs inside Docker, so open `psql` via the container (see the note in Phase 8.2 — there is no `psql` on the host):

```bash
docker compose exec postgres psql -U doe_user -d doe_db
```

At the `doe_db=#` prompt, replace the email and run:

```sql
UPDATE signup_requests
SET status = 'approved',
    invite_token = 'bootstrap-' || md5(random()::text),
    invite_expires_at = NOW() + INTERVAL '72 hours'
WHERE email = 'you@example.com'
RETURNING invite_token;
```

Copy the returned `invite_token` value, then `\q` to exit.

### 11.4 — Complete registration

In your browser, go to:

```
https://yourdomain.com/register/complete?token=<PASTE_TOKEN_HERE>
```

Set a password, log in. Because your email is in `ADMIN_EMAILS`, `/admin/signups` will now load for you, and from this point on you can approve all further signups through the UI.

> Not ideal. A future release should provide either a `bootstrap_admin` management script or auto-approve the first signup if the `users` table is empty and the email matches `ADMIN_EMAILS`.

---

## Phase 12: Auto-Restart & Monitoring

### 12.1 — Enable Docker on boot

```bash
sudo systemctl enable docker
```

### 12.2 — Container restart policies

The `docker-compose.yml` already includes `restart: unless-stopped` on all services. Containers will auto-restart after server reboots.

### 12.3 — Docker log rotation

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
cd /home/deploy/agentic-doe
docker compose up -d
```

### 12.4 — Automatic security updates

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## Phase 13: Redeployment

When updating the running server with new code:

```bash
ssh deploy@<YOUR_SERVER_IP>
cd /home/deploy/agentic-doe

git pull origin main
docker compose up --build -d
docker compose exec app uv run alembic upgrade head

docker compose ps
docker compose logs -f app --tail=50
```

---

## Phase 14: Backups

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
  -v agentic-doe_neo4j_data:/data \
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
0 3 * * * cd /home/deploy/agentic-doe && docker compose exec -T postgres pg_dump -U doe_user doe_db | gzip > /home/deploy/backups/pg_$(date +\%Y\%m\%d).sql.gz 2>/dev/null
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
| `https://...` refused / `ERR_CONNECTION_REFUSED` on 443 | Caddyfile still has `:80 { ... }` (Phase 9) instead of a domain block (Phase 10) — no cert, no 443 listener | Do Phase 10 with your real domain; confirm `sudo ss -tlnp \| grep 443` after reload |
| Caddy log spams `dial tcp [::1]:<port>: connect: connection refused` | `reverse_proxy localhost:...` resolves to IPv6 but Docker binds IPv4 only | Use `127.0.0.1:<port>` in Caddyfile, then `sudo systemctl reload caddy` |
| "CORS error" in browser | `CORS_ORIGINS` / `FRONTEND_URL` / `PUBLIC_API_URL` mismatch | Update `.env` so all three match the public origin, then `docker compose restart app` |
| "address already in use" | Ghost Docker state | `docker compose down --remove-orphans && sudo systemctl restart docker` |
| Docker build OOM | Not enough RAM | `free -h` — need at least 4GB, 8GB recommended |
| Disk full | Docker images/logs | `docker system prune -f` |
