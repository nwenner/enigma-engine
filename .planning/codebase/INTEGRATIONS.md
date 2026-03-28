# External Integrations

**Analysis Date:** 2026-03-28

## APIs & External Services

**SSH/SFTP (Remote Save File Access):**
- Paramiko SSH/SFTP — connects to Windows PC and Steam Deck over LAN to read/write Diablo 2 save files
  - SDK/Client: `paramiko==3.5.0`
  - Auth: password (Fernet-encrypted, stored in `Settings` DB table) or SSH private key (`data/keys/pc.pem`, `data/keys/deck.pem`)
  - Connection settings: `pc_host`, `pc_port`, `pc_username`, `pc_password`, `pc_save_path` (and `deck_*` equivalents) stored in DB KV store
  - Implementation: `backend/services/ssh_client.py` — context manager `get_sftp()`, `check_d2r_running()`, `list_d2s_files()`
  - Key policy: `AutoAddPolicy` (auto-accepts host keys — LAN-only, not for untrusted networks)
  - Supported key types: RSA, Ed25519, ECDSA (tried in sequence via `_load_private_key()`)
  - Timeouts: 10s connect / banner / auth

**Amazon SES (Email Notifications):**
- AWS Simple Email Service — sends conflict-detected email alerts (optional feature)
  - SDK/Client: `boto3==1.36.4`
  - Auth: AWS named profile from `~/.aws/credentials` (profile name stored in DB, not a secret)
  - Config: `notification_aws_profile`, `notification_aws_region` (default `us-east-1`), `notification_ses_from`, `notification_ses_to` — all stored in DB KV, configured via Settings UI
  - Implementation: `backend/services/notify.py` — `_send_ses_email()` (blocking, called via `asyncio.to_thread`)
  - Trigger: auto-sync watcher calls `notify_conflict()` on conflict detection
  - This integration is entirely optional; `notification_type = "none"` (default) disables it

## Data Storage

**Databases:**
- SQLite
  - Connection: `DATABASE_URL` env var, defaults to `sqlite+aiosqlite:///app/data/db.sqlite`
  - Client: SQLAlchemy 2.0 async engine + aiosqlite driver (`backend/database.py`)
  - Session factory: `AsyncSessionLocal` (async_sessionmaker, `expire_on_commit=False`)
  - Schema: defined in `backend/models.py` via SQLAlchemy ORM (DeclarativeBase)
  - Migrations: runtime `ALTER TABLE` statements in `init_db()` — no migration framework

**File Storage:**
- Local filesystem only (Docker volume at `./data:/app/data`)
  - `data/backups/pc/` — snapshot directories for PC saves
  - `data/backups/deck/` — snapshot directories for Steam Deck saves
  - `data/keys/` — uploaded SSH private key files (`pc.pem`, `deck.pem`)
  - `data/tmp/` — temporary staging for in-flight transfers
  - `data/staging/` — staging directory (config path, `cfg.staging_dir`)

**Caching:**
- TanStack Query in-memory cache only (frontend, `staleTime: 30_000ms`)
- No server-side cache layer

## Authentication & Identity

**Auth Provider:**
- None — no user login system; the web UI is assumed to be LAN-private
- SSH password encryption: Fernet key derived from `SECRET_KEY` env var via SHA-256 + base64 (`backend/routers/settings.py` `_fernet()`)
- Passwords stored encrypted in `Settings` KV table; decrypted only when building SSH connection kwargs

## Monitoring & Observability

**Error Tracking:**
- None

**Logs:**
- Python standard `logging` module throughout backend (`log = logging.getLogger(__name__)`)
- uvicorn access logs via `uvicorn[standard]`
- No structured logging format; no log aggregation

## Real-Time Communication

**Server-Sent Events (SSE):**
- Internal push channel from backend to browser
  - Endpoint: `GET /api/events/stream` (`backend/routers/events.py`)
  - In-memory event bus: `backend/services/event_bus.py` — `subscribe()` / `unsubscribe()` / asyncio queues
  - Keepalive comment every 25s to prevent proxy timeouts
  - Frontend consumer: `frontend/src/api/useEventStream.ts`
  - Used for: sync completion toasts, conflict alerts, auto-sync state changes

## CI/CD & Deployment

**Hosting:**
- Self-hosted Docker container on LAN (single-machine, `restart: unless-stopped`)
- Port: 8080

**CI Pipeline:**
- None (no GitHub Actions, CircleCI, etc.)
- Pre-commit hook: `.git/hooks/pre-commit` runs full pytest suite before each commit
- Claude Code stop hook: `.claude/settings.json` runs `tail -3` of test output after each response

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None (SES is fire-and-forget email, not a webhook)

## Environment Configuration

**Required env vars:**
- `SECRET_KEY` — Fernet key seed for SSH password encryption (generate with `python3 -c "import secrets; print(secrets.token_hex(32))"`)

**Optional env vars:**
- `DATABASE_URL` — SQLite path override for local dev (default: `/app/data/db.sqlite`)
- `BACKUP_RETENTION_COUNT` — default `10`

**Secrets location:**
- `.env` file at project root (mapped via `env_file` in `docker-compose.yml`)
- SSH keys stored on disk at `data/keys/{machine}.pem` (chmod 0600, inside Docker volume)
- AWS credentials at `~/.aws/` (mounted read-only into container)
- SSH passwords encrypted in SQLite `settings` table; never stored in plaintext

---

*Integration audit: 2026-03-28*
