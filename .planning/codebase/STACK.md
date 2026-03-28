# Technology Stack

**Analysis Date:** 2026-03-28

## Languages

**Primary:**
- Python 3.12 - Backend API and all business logic (`backend/`)
- TypeScript 5.7 - Frontend SPA (`frontend/src/`)

**Secondary:**
- CSS (Tailwind utility classes) - Styling (`frontend/src/index.css`, component files)

## Runtime

**Environment:**
- Python 3.12-slim (Docker image: `python:3.12-slim`)
- Node 22-alpine (Docker image: `node:22-alpine`, build stage only)

**Package Manager:**
- Python: pip (no lockfile — `requirements.txt` pins exact versions)
- Node: npm with lockfile (`frontend/package-lock.json` present)

## Frameworks

**Core Backend:**
- FastAPI 0.115.6 - Async REST API framework + static file serving for SPA
- uvicorn[standard] 0.34.0 - ASGI server, runs on port 8080

**Core Frontend:**
- React 18.3.1 - UI component library
- react-router-dom 7.1.1 - Client-side routing (BrowserRouter)
- TanStack Query (@tanstack/react-query) 5.62.7 - Server state, caching, refetch

**Build/Dev:**
- Vite 6.0.7 - Frontend dev server + production bundler
- TypeScript compiler (tsc) - Type checking before build (`tsc && vite build`)
- postcss + autoprefixer - CSS processing for Tailwind

## Key Dependencies

**Critical Backend:**
- pydantic 2.10.4 - Request/response validation, settings management
- pydantic-settings 2.7.0 - `Settings` class loaded from `.env` (`backend/config.py`)
- SQLAlchemy 2.0.36 - ORM with async engine (`backend/database.py`)
- aiosqlite 0.20.0 - Async SQLite driver for SQLAlchemy
- greenlet 3.1.1 - Required by SQLAlchemy async
- paramiko 3.5.0 - SSH/SFTP client for remote save file operations (`backend/services/ssh_client.py`)
- cryptography 44.0.0 - Fernet symmetric encryption for SSH passwords at rest (`backend/routers/settings.py`)
- python-multipart 0.0.20 - Multipart form data (SSH key file uploads)
- boto3 1.36.4 - AWS SDK, used exclusively for SES email notifications (`backend/services/notify.py`)

**Critical Frontend:**
- axios 1.7.9 - HTTP client, configured with `baseURL: "/api"` and 30s timeout (`frontend/src/api/client.ts`)
- sonner 1.7.4 - Toast notification library (sync events, conflict alerts)

**Testing:**
- pytest 8.x - Test runner
- pytest-asyncio 0.24 - Async test support (`asyncio_mode = auto` in `pytest.ini`)

## Configuration

**Environment:**
- Configured via `.env` file (see `.env.example`)
- Required: `SECRET_KEY` — 32-char hex string used to derive Fernet key for password encryption
- Optional: `DATABASE_URL` — defaults to `sqlite+aiosqlite:///app/data/db.sqlite`; overridable for local dev
- Optional: `BACKUP_RETENTION_COUNT` — defaults to `10`
- Notification settings (AWS profile, SES addresses) stored in DB KV table, configured via Settings UI

**Build:**
- Docker multi-stage: `frontend-builder` (Node 22) + `runtime` (Python 3.12-slim) — `Dockerfile`
- Frontend build output copied from stage 1 to `frontend/dist/` in stage 2
- `docker-compose.yml` mounts `./data:/app/data` (persistent) and `~/.aws:/root/.aws:ro` (AWS credentials)
- `frontend/vite.config.ts` — dev proxy: `/api` → `http://localhost:8080`
- `frontend/tsconfig.json` — strict mode enabled, target ES2020, no path aliases

**TypeScript Strictness:**
- `strict: true`, `noUnusedLocals: true`, `noUnusedParameters: true`, `noFallthroughCasesInSwitch: true`

## Platform Requirements

**Development:**
- Docker + docker-compose (app runs in container; `./starth.sh` used to start)
- Node 22 not required locally — only needed inside Docker build stage

**Production:**
- Single Docker container on port 8080
- Persistent volume at `/app/data` (SQLite DB, backups, SSH keys, tmp files)
- AWS credentials at `~/.aws` (required only if SES notifications are enabled)
- LAN-accessible; no TLS termination built in

---

*Stack analysis: 2026-03-28*
