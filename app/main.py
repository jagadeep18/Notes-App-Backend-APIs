"""
app/main.py
────────────
Application factory.

Design: create_app() factory pattern (not a module-level app instance) allows:
1. Test isolation — each test suite gets a fresh app with its own state
2. Multiple app variants (e.g., minimal health-check app for load balancers)
3. Clean startup/shutdown lifecycle with lifespan context manager
"""


from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from typing import Annotated

from pathlib import Path

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.exception_handlers import register_exception_handlers
from app.api.middleware import RequestLoggingMiddleware
from app.api.v1 import auth, notes, activity
from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DbSession
from app.core.logging import configure_logging, get_logger
from app.db.base import engine
from app.schemas.common import PaginatedResponse, PaginationParams
from app.schemas.note import NoteResponse
from app.services.note_service import NoteService

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Startup: configure logging, warm connection pool.
    Shutdown: dispose pool gracefully.
    """
    configure_logging()
    logger.info("application_starting", version=settings.app_version, env=settings.app_env)

    # Warm the connection pool at startup (avoid cold-start latency on first request)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda _: None)
        logger.info("database_pool_initialized")
    except Exception as exc:
        logger.warning("database_connection_failed", error=str(exc),
                       hint="App will retry on first request. Start Postgres or use Docker Compose.")

    yield

    await engine.dispose()
    logger.info("application_shutdown")


# Rate limiter — uses Redis in production via REDIS_URL
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])


def create_app() -> FastAPI:
    app = FastAPI(
        title="Notes App (Backend APIs)",
        version="1.0.0",
        description="""
### 📝 Notes App (Backend APIs)
Build a multi-user notes service with production-grade security and features.

**Key Features:**
*   **User Management**: Registration and JWT-based authentication.
*   **Notes CRUD**: Manage personal notes with title and content.
*   **Secure Sharing**: Share notes with other users via email.
*   **Encryption**: Optional AES-based at-rest encryption for private notes.
*   **Search**: Full-text search across all your notes.
*   **Versioning**: Historical snapshots and restoration.
        """,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-Response-Time"],
    )

    # ── Request Logging ───────────────────────────────────────────────────────
    app.add_middleware(RequestLoggingMiddleware)

    # ── Exception Handlers ────────────────────────────────────────────────────
    register_exception_handlers(app)

    # ── Routers (root level — matches automated test paths) ───────────────────
    # Auth: /register, /login, /logout, /me, /refresh
    app.include_router(auth.router)

    # Notes: /notes, /notes/{id}, /notes/{id}/share, etc.
    app.include_router(notes.router)

    # Share links: /shared/{token}
    app.include_router(notes.shared_router)

    # Activity: /activity
    app.include_router(activity.router)

    # ── Also mount under /api/v1 for versioned access ─────────────────────────
    API_PREFIX = "/api/v1"
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(notes.router, prefix=API_PREFIX)
    app.include_router(notes.shared_router, prefix=API_PREFIX)
    app.include_router(activity.router, prefix=API_PREFIX)

    # ── Health Check ─────────────────────────────────────────────────────────
    @app.get("/health", tags=["System"], summary="Health check")
    async def health() -> dict:
        return {"status": "ok", "version": settings.app_version, "env": settings.app_env}

    # ── About ─────────────────────────────────────────────────────────────────
    @app.get("/about", tags=["System"], summary="About this API")
    async def about() -> dict:
        return {
            "name": "Jagadeep",
            "email": "jagadeep@example.com",
            "my features": {
                "Encrypted Private Notes": "End-to-end security for sensitive data. Content is encrypted at rest using AES-128-CBC and authenticated with HMAC-SHA256 (Fernet).",
                "Note Versioning": "Automatic snapshots on every edit. Users can view history and restore any previous version, ensuring data is never lost.",
                "Smart Sharing": "Granular permissions (READ/WRITE) and temporary public share links with expiration and access limits.",
                "Full-Text Search": "High-performance search using PostgreSQL tsvector and GIN indices for instant retrieval of notes by content."
            }
        }

    # ── Search (dedicated endpoint) ───────────────────────────────────────────

    def _search_pagination(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> PaginationParams:
        return PaginationParams(page=page, page_size=page_size)

    SearchPaginationDep = Annotated[PaginationParams, Depends(_search_pagination)]

    @app.get("/search", tags=["Search"], response_model=PaginatedResponse, summary="Full-text search notes")
    async def search_notes(
        current_user: CurrentUser,
        db: DbSession,
        pagination: SearchPaginationDep,
        q: str = Query(..., min_length=1, description="Search keyword"),
    ) -> PaginatedResponse:
        """Search across all your notes by keyword. Uses PostgreSQL full-text search."""
        service = NoteService(db)
        found_notes, total = await service.list_notes(current_user, pagination, search=q)
        items = [NoteResponse.model_validate(n) for n in found_notes]
        return PaginatedResponse.create(items=items, total=total, pagination=pagination)

    # ── Static Files & Frontend ─────────────────────────────────────────
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(str(static_dir / "index.html"))

    return app


app = create_app()

