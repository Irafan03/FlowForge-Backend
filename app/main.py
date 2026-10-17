"""
FlowForge Backend — FastAPI application factory.

Launch:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Swagger UI:   http://localhost:8000/docs
ReDoc:        http://localhost:8000/redoc
OpenAPI JSON: http://localhost:8000/openapi.json
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.credentials import router as credentials_router
from app.api.executions import router as executions_router
from app.api.integrations import router as integrations_router
from app.api.webhooks import router as webhooks_router
from app.api.workflows import router as workflows_router
from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="FlowForge Backend",
        description=(
            "Workflow automation engine — trigger, execute and monitor "
            "multi-step workflows over HTTP, Gmail, Telegram and ML."
        ),
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        # Disable docs in production
        # docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    # In production set ALLOWED_ORIGINS via env; for now allow everything in dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.ENVIRONMENT == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    api_prefix = "/api/v1"

    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(workflows_router, prefix=api_prefix)
    app.include_router(executions_router, prefix=api_prefix)
    app.include_router(webhooks_router, prefix=api_prefix)
    app.include_router(credentials_router, prefix=api_prefix)
    app.include_router(integrations_router, prefix=api_prefix)

    # ── Global exception handlers ─────────────────────────────────────────────

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred"},
        )

    # ── Health check ──────────────────────────────────────────────────────────

    @app.get("/health", tags=["health"], summary="Health check")
    def health() -> dict:
        return {"status": "ok", "version": settings.APP_VERSION}

    # ── Startup / shutdown events ─────────────────────────────────────────────

    @app.on_event("startup")
    async def _startup() -> None:
        logging.basicConfig(
            level=settings.LOG_LEVEL,
            format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        )
        logger.info(
            "FlowForge API v%s starting up (%s)", settings.APP_VERSION, settings.ENVIRONMENT
        )
        # Create a shared ARQ pool so enqueue_execution reuses one connection
        from arq import create_pool
        from arq.connections import RedisSettings

        from app.services.execution_service import set_shared_pool

        try:
            pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
            set_shared_pool(pool)
            logger.info("ARQ Redis pool connected")
        except Exception:
            logger.warning(
                "Could not connect to Redis on startup — executions will open "
                "a per-request pool (development mode only)"
            )

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        from app.services.execution_service import _get_shared_pool, clear_shared_pool

        pool = _get_shared_pool()
        if pool is not None:
            await pool.aclose()
            logger.info("ARQ Redis pool closed")
        clear_shared_pool()
        logger.info("FlowForge API shutting down")

    return app


# Module-level app instance used by uvicorn / gunicorn
app = create_app()
