# Deployment Guide: Factorial

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
git clone https://github.com/kgdunn/factorial.git
cd factorial
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

The canonical list of every setting the backend reads lives in [`.env.example`](https://github.com/kgdunn/factorial/blob/main/.env.example) at the repo root — it stays in sync with `backend/src/app/config.py`. The block below only covers the values you must change from the template defaults for a production deploy. Leave everything else (`TOOL_*`, `MCP_*`, `SHARE_TOKEN_*`, `EXPORTS_*`, `CHAT_RATE_LIMIT`, etc.) at the `.env.example` defaults unless you know you need to override them.

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

# Anthropic — required for the agent loop
ANTHROPIC_API_KEY=sk-ant-...

# Security — API key for endpoint authentication
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
API_SECRET_KEY=<GENERATE_A_RANDOM_SECRET>

# JWT Authentication
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(64))"
JWT_SECRET_KEY=<GENERATE_A_RANDOM_SECRET>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS / public origins — your server IP for now. All three must match the
# origin the browser actually hits. Swap to https://yourdomain.com in Phase 10.
# FRONTEND_URL is also embedded in outgoing emails (invite, approval, share
# links) — if wrong, those links break.
CORS_ORIGINS=http://<YOUR_SERVER_IP>
FRONTEND_URL=http://<YOUR_SERVER_IP>
PUBLIC_API_URL=http://<YOUR_SERVER_IP>

# SMTP — required for invite, signup-approval, and password-reset emails.
# Leave SMTP_HOST blank only if you have no users who need email (dev only).
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=<your-smtp-user>
SMTP_PASSWORD=<your-smtp-password>
SMTP_FROM_EMAIL=signup@yourdomain.com
SMTP_USE_TLS=true

# How long an invite link (emailed to an approved user to finish registration)
# or a password-reset link stays valid.
INVITE_TOKEN_EXPIRE_HOURS=72

# GeoIP — optional. Path to a MaxMind GeoLite2-Country.mmdb file used to
# resolve login IPs into ISO-3166 country codes for the admin Users panel.
# Download from https://www.maxmind.com/ (free account required) and drop the
# .mmdb file on the VPS. If this is empty or the file is missing, country
# lookup is silently skipped — logins still work. Refresh the file monthly.
GEOIP_COUNTRY_DB_PATH=/opt/factorial/geoip/GeoLite2-Country.mmdb
```

> Admins are **not** configured via env vars anymore — `users.is_admin` in the database is the source of truth. See Phase 11 for how to bootstrap the first admin.

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

> **Do NOT use `docker-compose.override.yml`** for port changes. Docker Compose _merges_ (concatenates) list fields like `ports` from overrides, creating duplicate bindings that cause "address already in use" errors.

---

## Phase 6: Build & Start All Services

### 6.0 — Check for port conflicts

```bash
sudo ss -tlnp | grep -E ':(8000|3000|5432|7474|7687)\b'
```

If anything is listening, stop it:

| Cause                                                          | Fix                                                                   |
| -------------------------------------------------------------- | --------------------------------------------------------------------- |
| Standalone Neo4j                                               | `sudo systemctl stop neo4j && sudo systemctl disable neo4j`           |
| Standalone PostgreSQL                                          | `sudo systemctl stop postgresql && sudo systemctl disable postgresql` |
| Previous Docker attempt                                        | `docker compose down --remove-orphans`                                |
| Ghost Docker state (ss shows nothing but Docker says "in use") | See 6.0a below                                                        |

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
```

> The Swagger UI (`/docs`), ReDoc (`/redoc`), and raw OpenAPI schema (`/openapi.json`) are intentionally **disabled in production** — they're gated on `APP_ENV != "production"` in [`backend/src/app/main.py`](https://github.com/kgdunn/agentic-doe/blob/main/backend/src/app/main.py). Expect a 404 from those paths on a correctly-configured deploy. Run the app locally with `APP_ENV=development` if you want to browse the schema.

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

### 8.3 — Tail application logs

From the repo root on the VPS, use the Makefile targets to follow logs (Ctrl+C to exit):

```bash
make logs             # backend + frontend, interleaved
make logs-app         # backend (FastAPI) only
make logs-frontend    # frontend (nginx) only
```

Each shows the last 100 lines and then follows. The underlying command is `docker compose logs -f --tail=100 <service>` if you prefer to invoke it directly or add other services (e.g. `postgres`, `neo4j`).

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

Only `/api/*` is proxied to the backend. Swagger / ReDoc / `openapi.json` are disabled in production by the FastAPI app itself (see Phase 8.1), so there is no reason to route those paths through Caddy.

```bash
sudo tee /etc/caddy/Caddyfile << 'EOF'
:80 {
    handle /api/* {
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
- **API health:** `http://<YOUR_SERVER_IP>/api/v1/health`

(`/docs` is intentionally disabled in production — see the note in Phase 8.1.)

---

## Phase 10: Enable HTTPS (When You Have a Domain)

### 10.1 — Set DNS

At your domain registrar, create an A record:

| Type | Name             | Value              | TTL |
| ---- | ---------------- | ------------------ | --- |
| A    | `@` or subdomain | `<YOUR_SERVER_IP>` | 300 |

Verify: `dig yourdomain.com` (for the canonical deployment, the domain is `factori.al`)

### 10.2 — Update the Caddyfile

Replace `yourdomain.com` with your real domain (e.g. `factori.al`). As soon as Caddy sees a domain name as the site address, it will obtain a Let's Encrypt certificate and start listening on port 443.

```bash
sudo tee /etc/caddy/Caddyfile << 'EOF'
yourdomain.com {
    handle /api/* {
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

The app is **invite-only**: `POST /auth/register` is disabled in code, and new users can only register via an invite token issued by an existing admin. Since there is no admin yet on a fresh deploy, create one directly with the backend CLI — it inserts a shell `User` row with `is_admin = true` and prints a one-time setup link the admin follows to pick a password.

### 11.1 — Run the create-admin command

```bash
docker compose exec app uv run python -m app.cli create-admin --email you@example.com --name "Your Name"
```

The command prints a setup URL of the form:

```
https://yourdomain.com/register/complete?token=<SETUP_TOKEN>
```

(On an IP-only deploy before Phase 10, this will use `http://<YOUR_SERVER_IP>` instead, pulled from `FRONTEND_URL`.)

### 11.2 — Complete registration

Open the setup URL in your browser and pick a password. You're logged in as an admin; `/admin/users` and `/admin/signups` will load for you, and from here on you can approve further signups and promote/demote other users through the UI.

> The link is valid for `INVITE_TOKEN_EXPIRE_HOURS` (default 72). If it expires before you use it, rerun the `create-admin` command and use the freshly printed setup link.

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
cd /home/deploy/factorial
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
cd /home/deploy/factorial

git pull origin main
docker compose up --build -d
docker compose exec app uv run alembic upgrade head

docker compose ps
docker compose logs -f app --tail=50
```

This approach restarts the single `app` container in place — expect ~3–10 s of 5xx while the new image starts. Active chat SSE streams will be severed (the browser will auto-reconnect via the resume endpoint once the new container is up, but the in-progress assistant turn cannot be finished on a new container; the user will see an "interrupted — retry?" state).

For production use, the next phase describes a zero-downtime variant.

---

## Phase 13b: Zero-Downtime Redeploy (Blue-Green)

Run two backend containers (`app-blue` on `:8000`, `app-green` on `:8001`) alongside the shared Postgres + Neo4j + frontend. Only one colour is "live" at a time — Caddy's `reverse_proxy` points at whichever port the deploy script writes into `/etc/caddy/active_backend.caddy`. Deploys build the idle colour, health-check it, run migrations, flip Caddy, and drain the old colour. Existing SSE streams on the old colour finish their turn during the drain window; new requests go to the new colour immediately.

### 13b.1 — One-time host setup

```bash
# State directory that records which colour is currently live.
sudo install -d -o deploy -g deploy /var/lib/factorial
echo blue | sudo tee /var/lib/factorial/active-color >/dev/null

# Allow the deploy user to reload Caddy without a password prompt.
# (If you already run deploy under full sudo, skip this.)
echo 'deploy ALL=(root) NOPASSWD: /bin/systemctl reload caddy, /usr/bin/caddy validate *' \
  | sudo tee /etc/sudoers.d/doe-caddy-reload
sudo chmod 0440 /etc/sudoers.d/doe-caddy-reload
```

Replace the Caddyfile from Phase 9.2 / 10.2 with this version, which imports the mutable upstream snippet:

```bash
sudo tee /etc/caddy/Caddyfile << 'EOF'
yourdomain.com {
    handle /api/* {
        import /etc/caddy/active_backend.caddy
    }
    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
EOF

# Seed the snippet to point at port 8000 (blue).
sudo tee /etc/caddy/active_backend.caddy << 'EOF'
# Managed by scripts/deploy-blue-green.sh — do not edit by hand.
reverse_proxy 127.0.0.1:8000
EOF

sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

The legacy `app` service (from Phase 6) binds to port 8000 and would conflict with `app-blue`. Stop it before the first blue-green deploy:

```bash
docker compose stop app
docker compose rm -f app
```

### 13b.2 — Deploy a new version

```bash
cd /home/deploy/factorial
git pull origin main
make deploy-bg       # interactive: prompts before each side-effect
# or
make deploy-bg-force # non-interactive (e.g. from CI)
```

What the script does, step by step:

1. Reads `/var/lib/factorial/active-color` → current colour.
2. Builds the idle colour: `docker compose --profile <next> build app-<next>`.
3. Starts it: `docker compose --profile <next> up -d app-<next>`.
4. Polls `http://127.0.0.1:<next-port>/api/v1/health` until it returns 2xx.
5. Runs `alembic upgrade head` inside the idle container.
6. Writes a new `/etc/caddy/active_backend.caddy` pointing at the new port and `caddy validate` + `systemctl reload caddy`.
7. Updates the state file so subsequent deploys flip back the other way.
8. Sleeps `DRAIN_SECONDS` (default 120) so long-lived SSE streams on the old colour finish naturally.
9. Stops the old colour container.

Override the drain window if your typical chat turns are shorter (or longer):

```bash
DRAIN_SECONDS=30 make deploy-bg-force
```

### 13b.3 — Migration discipline (expand / contract)

Because both colours run the same schema for the duration of each deploy, every migration in a blue-green world must be backwards-compatible with the previous code version. Follow expand / contract:

- **Expand** (safe in a blue-green deploy): add a nullable column, add a new table, add an index `CONCURRENTLY`, widen a `VARCHAR`.
- **Contract** (NOT safe in the same deploy that introduces the expand): drop a column, tighten NOT NULL, remove a table, rename a column.

A destructive (contract) migration must ship in a **subsequent** deploy after the expand-only change has been rolled out and the old code is no longer running anywhere. Until the first production release there are no real users, so one-shot breaking migrations are still fine — but once live traffic is on both colours at once during a cutover, the discipline is load-bearing.

### 13b.4 — Rollback

Caddy's upstream is a file reload, so rolling back a bad deploy is one command as long as the old colour hasn't been stopped yet (i.e. you are inside the drain window):

```bash
make rollback-bg
```

This flips the Caddy snippet back to the previous port and reloads Caddy — no container rebuild, typically sub-second recovery. If the drain window has already expired, restart the previous colour first:

```bash
docker compose --profile blue up -d app-blue   # or app-green
make rollback-bg
```

### 13b.5 — What happens to in-flight chat streams?

- **New requests** after Caddy reload: served by the new colour.
- **SSE streams already open** on the old colour: stay connected on the old colour until the drain window expires, at which point the container is stopped and the TCP connection closes.
- **Client-side**: the SvelteKit chat page tracks the `Last-Event-ID` of every SSE event and, on disconnect, calls `GET /api/v1/chat/{conversation_id}/resume` with that header. The new colour replays any events the client missed from `chat_events` and, if the original turn was cut short by the container stop, emits a synthetic `interrupted` event so the UI can offer a retry.

This means blue-green gets you to ~95% SSE-stream preservation with no application-level coordination. The remaining 5% is turns that cross the drain boundary — those are gracefully surfaced as an interruption, not a silent failure.

### 13b.6 — Verification

From your laptop during a deploy:

```bash
# Uptime probe (should stay 2xx throughout).
while true; do
  curl -s -o /dev/null -w "%{http_code} %{time_total}\n" https://yourdomain.com/api/v1/health
  sleep 0.2
done

# SSE survival: open a slow chat turn in the browser during the deploy
# and confirm the stream either completes cleanly (drain path) or
# resumes and surfaces an 'interrupted' state (drain-expired path).
```

From the VPS after a deploy:

```bash
cat /var/lib/factorial/active-color
docker compose ps
docker compose logs -f app-green --tail=50    # or app-blue
```

---

## Phase 14: Backups

### PostgreSQL — production backup/restore tooling

PostgreSQL backups are handled by two shell scripts that ship in the repo:

- `scripts/backup-postgres.sh` — dumps the DB (via `pg_dump` in the `postgres` container), uploads the dump to an S3-compatible object store (Hetzner Object Storage, by default), verifies the upload, and records run status in the `admin_events` table.
- `scripts/restore-postgres.sh` — lists available backups, downloads one, verifies its checksum, and restores it back into the running stack.

Both scripts are verbose by design (step-by-step output + end-of-run `SUCCESS` / `FAILED` summary) and check credentials **before** touching the database.

**Full operator runbook:** see [`scripts/README.md`](https://github.com/kgdunn/factorial/blob/main/scripts/README.md) for one-time setup (Hetzner bucket + Object Lock + lifecycle rules + credentials on the VPS + cron installation).

High-level shape once set up:

| Concern           | How it's handled                                                                                                                                                                                                         |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Storage           | Hetzner Object Storage (S3-compatible) — same region as the VPS, free internal traffic                                                                                                                                   |
| Credentials       | AWS CLI profile `doe-backup` on the `deploy` user (`~/.aws/credentials`, 0600)                                                                                                                                           |
| Retention         | Grandfather-Father-Son: `postgres/daily/` (35d), `postgres/weekly/` (100d), `postgres/monthly/` (400d) — enforced by Hetzner **bucket lifecycle rules**, not by script-side deletion                                     |
| Immutability      | Hetzner Object Lock (WORM, compliance mode) on the bucket — stolen credentials cannot delete backups within the retention window                                                                                         |
| Encryption        | `--sse AES256` on every upload                                                                                                                                                                                           |
| Integrity         | `sha256` computed locally + written to object metadata + verified on both upload and restore                                                                                                                             |
| Run logs          | Per-run log file at `/var/log/doe/backup-<UTC-stamp>.log` (rotated via logrotate)                                                                                                                                        |
| Run history       | `admin_events` table — rows for `in_progress` / `success` / `failed`, with payload: size, sha, s3 key, alembic head, git sha, duration. Viewable in the app at `/admin/events` (filter by `event_type=postgres_backup`). |
| Dead-man's switch | Optional healthchecks.io URL (`HC_PING_URL`) — pings `/start`, success, `/fail`. Alerts on missed runs, which cron MAILTO cannot.                                                                                        |
| Failure webhook   | Optional `WEBHOOK_URL` — Slack/Discord POST on failure                                                                                                                                                                   |
| Concurrency       | `flock` on `/var/lock/doe-backup.lock`                                                                                                                                                                                   |
| Restore drill     | Weekly `scripts/restore-drill.sh` — restores latest backup to a scratch DB, runs smoke queries, drops it, logs `restore_drill` event                                                                                     |

Quick ad-hoc commands (once the scripts are installed and credentials are configured):

```bash
# Manual backup (daily-class)
./scripts/backup-postgres.sh

# List recent backups in S3
./scripts/restore-postgres.sh --list

# Restore the latest backup (interactive confirmation required)
./scripts/restore-postgres.sh

# Dry-run (preflight + verification, no side effects)
./scripts/backup-postgres.sh --dry-run
```

### Neo4j

> Neo4j backup is **out of scope** for the current tooling. For now, use the manual snapshot below.

```bash
docker compose stop neo4j
docker run --rm \
  -v factorial_neo4j_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/neo4j_backup_$(date +%Y%m%d).tar.gz /data
docker compose start neo4j
```

### Automated daily backup (cron)

Cron entries are version-controlled at [`deploy/cron/doe-backup.cron`](https://github.com/kgdunn/factorial/blob/main/deploy/cron/doe-backup.cron). Install with:

```bash
sudo cp /home/deploy/factorial/deploy/cron/doe-backup.cron /etc/cron.d/doe-backup
sudo chown root:root /etc/cron.d/doe-backup
sudo chmod 0644 /etc/cron.d/doe-backup
```

Schedule (all times UTC, offset off the hour to avoid platform-wide cron pile-ups):

| When               | What                         |
| ------------------ | ---------------------------- |
| Daily 03:07        | `backup-postgres.sh daily`   |
| Sunday 03:30       | `backup-postgres.sh weekly`  |
| 1st of month 04:00 | `backup-postgres.sh monthly` |
| Monday 04:30       | `restore-drill.sh`           |

Log rotation is handled by [`deploy/logrotate/doe-backup`](https://github.com/kgdunn/factorial/blob/main/deploy/logrotate/doe-backup), installed into `/etc/logrotate.d/`.

---

## Quick Reference

| Task                    | Command                                                                |
| ----------------------- | ---------------------------------------------------------------------- |
| Start all services      | `docker compose up -d`                                                 |
| Stop all services       | `docker compose down`                                                  |
| Rebuild and restart     | `docker compose up --build -d`                                         |
| View all logs (once)    | `docker compose logs`                                                  |
| Tail backend + frontend | `make logs` (or `docker compose logs -f --tail=100 app frontend`)      |
| Tail backend only       | `make logs-app` (or `docker compose logs -f --tail=100 app`)           |
| Tail frontend only      | `make logs-frontend` (or `docker compose logs -f --tail=100 frontend`) |
| Check service health    | `docker compose ps`                                                    |
| Run migrations          | `docker compose exec app uv run alembic upgrade head`                  |
| Restart one service     | `docker compose restart app`                                           |
| Shell into backend      | `docker compose exec app bash`                                         |
| Shell into postgres     | `docker compose exec postgres psql -U doe_user doe_db`                 |
| Disk usage              | `docker system df`                                                     |
| Clean unused images     | `docker image prune -f`                                                |
| Full cleanup (DANGER)   | `docker compose down -v --remove-orphans`                              |

---

## Troubleshooting

| Symptom                                                              | Likely Cause                                                                                                | Fix                                                                                   |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Backend crashes on startup                                           | Database not ready                                                                                          | `docker compose restart app` after 30s                                                |
| "Connection refused" to API                                          | Backend not running                                                                                         | `docker compose ps` + `docker compose logs app`                                       |
| Frontend shows blank page                                            | SvelteKit build failed                                                                                      | `docker compose logs frontend`                                                        |
| Neo4j "unhealthy"                                                    | Slow startup (30s+)                                                                                         | Wait, check `docker compose logs neo4j`                                               |
| Can't connect from browser                                           | UFW blocking port                                                                                           | `sudo ufw status` — port 80 must be open                                              |
| `https://...` refused / `ERR_CONNECTION_REFUSED` on 443              | Caddyfile still has `:80 { ... }` (Phase 9) instead of a domain block (Phase 10) — no cert, no 443 listener | Do Phase 10 with your real domain; confirm `sudo ss -tlnp \| grep 443` after reload   |
| Caddy log spams `dial tcp [::1]:<port>: connect: connection refused` | `reverse_proxy localhost:...` resolves to IPv6 but Docker binds IPv4 only                                   | Use `127.0.0.1:<port>` in Caddyfile, then `sudo systemctl reload caddy`               |
| "CORS error" in browser                                              | `CORS_ORIGINS` / `FRONTEND_URL` / `PUBLIC_API_URL` mismatch                                                 | Update `.env` so all three match the public origin, then `docker compose restart app` |
| "address already in use"                                             | Ghost Docker state                                                                                          | `docker compose down --remove-orphans && sudo systemctl restart docker`               |
| Docker build OOM                                                     | Not enough RAM                                                                                              | `free -h` — need at least 4GB, 8GB recommended                                        |
| Disk full                                                            | Docker images/logs                                                                                          | `docker system prune -f`                                                              |
