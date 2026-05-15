<<<<<<< HEAD
# Notes API

A production-grade multi-user Notes backend built with **FastAPI**, **PostgreSQL**, and **async SQLAlchemy**. Designed to demonstrate engineering depth across architecture, security, scalability, and product thinking.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                    FastAPI (ASGI)                     │
│  Rate Limiting │ CORS │ Request Logging │ JWT Auth    │
├──────────────────────────────────────────────────────┤
│              API Layer (Routers / DTOs)               │
│  /auth  │  /notes  │  /shared  │  /activity           │
├──────────────────────────────────────────────────────┤
│                   Service Layer                       │
│  AuthService │ NoteService │ ActivityService          │
├──────────────────────────────────────────────────────┤
│               Repository Layer                        │
│  UserRepo │ NoteRepo │ ActivityRepo                   │
├──────────────────────────────────────────────────────┤
│           Database (Async SQLAlchemy + asyncpg)       │
│         PostgreSQL 16 │ Redis (rate limiting)         │
└──────────────────────────────────────────────────────┘
```

### Why This Stack?

| Choice | Reason |
|---|---|
| **FastAPI** | Native async, OpenAPI built-in, Pydantic v2 validation, best-in-class DX |
| **PostgreSQL** | JSONB, full-text search (tsvector/GIN), ACID, mature ecosystem |
| **asyncpg** | 3–5× faster than psycopg2 for async workloads |
| **SQLAlchemy 2.0 async** | Type-safe ORM with connection pooling, lazy-loading control |
| **Alembic** | Schema migrations with full upgrade/downgrade support |
| **Redis** | O(1) rate limit counters, future cache layer |
| **Fernet encryption** | AES-128-CBC + HMAC-SHA256 — authenticated symmetric encryption |
| **bcrypt (12 rounds)** | Adaptive hashing — secure today and tomorrow as hardware improves |

---

## Features

### Core
- ✅ User registration with strong password validation
- ✅ JWT auth with access + refresh tokens (rotation strategy)
- ✅ CRUD notes with soft-delete (data preserved for audit)
- ✅ Note sharing with per-user `read`/`write` permissions
- ✅ Full-text search (PostgreSQL `tsvector` + GIN index)
- ✅ Pagination on all list endpoints

### Advanced Product Features
- ✅ **Smart Version History** — every edit snapshots previous state; restore any version
- ✅ **Expiring Share Links** — time-limited (1h/24h/7d), optional one-time access, token hashing
- ✅ **Encrypted Private Notes** — Fernet AES at-rest encryption with key versioning
- ✅ **Pinned Notes** — up to 5 pinned notes per user, always surface first in list
- ✅ **Activity Timeline** — append-only audit log with filtering, pagination, JSONB metadata

### Production Extras
- ✅ Rate limiting (slowapi + Redis)
- ✅ Structured JSON logging (structlog)
- ✅ Correlation IDs on every request
- ✅ Centralized exception handling (domain exceptions → precise HTTP codes)
- ✅ Docker + Docker Compose
- ✅ GitHub Actions CI/CD (lint → type-check → unit tests → integration tests → Docker build)
- ✅ Alembic migrations with FTS trigger and auto-updated `updated_at`

---

## Quick Start

### Prerequisites
- Docker & Docker Compose

### Run with Docker Compose

```bash
cp .env.example .env
# Edit .env — set JWT_SECRET_KEY and ENCRYPTION_KEY

docker compose up --build
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

### Run migrations

```bash
docker compose run --rm migrate
```

### Local Development (without Docker)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt

# Start Postgres + Redis (Docker Compose services only)
docker compose up postgres redis -d

cp .env.example .env            # edit as needed
alembic upgrade head
uvicorn app.main:app --reload
```

---

## API Reference

Interactive docs available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Auth Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register a new user |
| POST | `/api/v1/auth/login` | Login → access + refresh tokens |
| POST | `/api/v1/auth/refresh` | Rotate refresh token |
| POST | `/api/v1/auth/logout` | Revoke refresh token |
| GET | `/api/v1/auth/me` | Get current user |

### Notes Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/notes` | List owned notes (search, pagination) |
| POST | `/api/v1/notes` | Create note (optional encryption) |
| GET | `/api/v1/notes/{id}` | Get note |
| PUT | `/api/v1/notes/{id}` | Update note (auto-snapshots version) |
| DELETE | `/api/v1/notes/{id}` | Soft-delete note |
| GET | `/api/v1/notes/shared` | Notes shared with me |
| POST | `/api/v1/notes/{id}/share` | Share with a user |
| DELETE | `/api/v1/notes/{id}/share/{user_id}` | Revoke share |
| POST | `/api/v1/notes/{id}/pin` | Pin note (max 5) |
| POST | `/api/v1/notes/{id}/unpin` | Unpin note |
| GET | `/api/v1/notes/{id}/versions` | Version history |
| GET | `/api/v1/notes/{id}/versions/{n}` | Specific version |
| POST | `/api/v1/notes/{id}/restore/{n}` | Restore version |
| POST | `/api/v1/notes/{id}/share-link` | Create expiring share link |
| GET | `/api/v1/shared/{token}` | Access note via share link (public) |

### Activity

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/activity` | Personal audit timeline |

---

## Database Schema

```
users                   notes                  note_shares
──────────────          ──────────────         ──────────────
id (UUID PK)            id (UUID PK)           id (UUID PK)
username (unique)       owner_id (FK)          note_id (FK)
email (unique)          title                  shared_with_id (FK)
hashed_password         content                shared_by_id (FK)
full_name               is_private             permission (enum)
is_active               encryption_key_version
is_verified             is_pinned
last_login_at           pinned_at
refresh_token_hash      deleted_at
                        search_vector (GIN)    note_versions
                                               ──────────────
share_links                                    id (UUID PK)
──────────────         activity_logs           note_id (FK)
id (UUID PK)           ──────────────          version_number
note_id (FK)           id (UUID PK)            title
created_by_id (FK)     user_id (FK)            content
token_hash (SHA-256)   action_type (enum)      modified_by_id (FK)
expires_at             note_id (FK)
access_count           metadata (JSONB)
max_accesses           created_at
is_active
```

---

## Testing

```bash
# All tests
pytest

# Unit only (no DB needed)
pytest tests/unit/ -v

# Integration (needs DB)
pytest tests/integration/ -v

# Coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

---

## Security Design Notes

| Concern | Implementation |
|---|---|
| Password storage | bcrypt with 12 rounds (adaptive) |
| JWT revocation | Refresh token hash stored in DB; rotation on every use |
| Token timing attacks | Login always runs bcrypt even on unknown email |
| Share link security | Token stored as SHA-256 hash; raw token shown once |
| Private note encryption | Fernet (AES-128-CBC + HMAC-SHA256); key versioning |
| UUID primary keys | Prevents resource enumeration attacks |
| Soft delete | Audit trail preserved; hard delete not exposed via API |
| Rate limiting | IP-based, Redis-backed, configurable per route |

---

## Project Structure

```
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── auth.py          # Auth endpoints
│   │   │   ├── notes.py         # Notes + share links + versions
│   │   │   └── activity.py      # Activity timeline
│   │   ├── exception_handlers.py
│   │   └── middleware.py
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── dependencies.py      # FastAPI DI graph
│   │   ├── exceptions.py        # Domain exception hierarchy
│   │   ├── logging.py           # structlog configuration
│   │   └── security.py          # bcrypt, JWT, Fernet, token gen
│   ├── db/
│   │   ├── base.py              # Engine, base model (UUID PK, timestamps)
│   │   └── session.py           # Async session dependency
│   ├── models/
│   │   ├── user.py
│   │   ├── note.py              # Note, NoteShare, NoteVersion, ShareLink
│   │   └── activity.py
│   ├── repositories/            # Data access layer
│   ├── schemas/                 # Pydantic DTOs (request/response)
│   ├── services/                # Business logic
│   └── main.py                  # App factory + lifespan
├── alembic/
│   └── versions/
│       └── 0001_initial_schema.py
├── tests/
│   ├── unit/                    # No DB — pure logic tests
│   └── integration/             # Full stack via AsyncClient
├── .github/workflows/ci.yml
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```
=======
# Notes-App-Backend-APIs-
A small backend application for a multi-user notes service. It exposes REST APIs to manage users and their personal notes.
>>>>>>> 90c49642d4949cda54b8ef77958e9ee6d1d69a97
