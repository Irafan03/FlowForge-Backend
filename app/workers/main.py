"""
ARQ worker entry point.

Defines:
- run_execution(ctx, execution_id) — the main task
- fire_schedules(ctx)             — periodic cron task (every 60s)
- WorkerSettings                  — ARQ configuration class

Launch with:
    python -m app.workers.main
or via Docker Compose (the 'worker' service runs this module).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from arq.connections import RedisSettings

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


# ── Tasks ─────────────────────────────────────────────────────────────────────

async def run_execution(ctx: dict[str, Any], execution_id: str) -> None:
    """
    Main ARQ task: run a single workflow execution to completion.

    The DB session is obtained fresh per-task to avoid sharing connections
    across concurrent workers.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    db = SessionLocal()
    try:
        from app.engine.runner import run_workflow

        logger.info("Starting execution %s", execution_id)
        run_workflow(db, uuid.UUID(execution_id))
        logger.info("Completed execution %s", execution_id)
    except Exception:
        logger.exception("Execution %s failed", execution_id)
        raise
    finally:
        db.close()
        engine.dispose()


async def fire_schedules(ctx: dict[str, Any]) -> None:
    """
    ARQ cron task: runs every 60 seconds, finds due schedule triggers and
    enqueues their executions.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    db = SessionLocal()
    try:
        try:
            from app.triggers.schedule import fire_due_schedules

            executions = await fire_due_schedules(db)
            if executions:
                logger.info("Enqueued %d scheduled execution(s)", len(executions))
        except Exception:
            logger.exception("Schedule trigger polling failed")

        try:
            from app.triggers.integrations import poll_integrations

            polled = await poll_integrations(db)
            if polled:
                logger.info("Enqueued %d Gmail/Telegram trigger execution(s)", polled)
        except Exception:
            logger.exception("Gmail/Telegram trigger polling failed")
    except Exception:
        logger.exception("fire_schedules cron task failed")
    finally:
        db.close()
        engine.dispose()


# ── ARQ Worker Settings ────────────────────────────────────────────────────────

class WorkerSettings:
    """
    ARQ discovers this class automatically when the module is passed to
    `arq.worker.run_worker()` or the `arq` CLI.
    """

    functions = [run_execution]

    # Cron: fire_schedules every minute
    cron_jobs = [
        {
            "coroutine": fire_schedules,
            "minute": {i for i in range(60)},  # every minute
        }
    ]

    @staticmethod
    def redis_settings() -> RedisSettings:
        settings = get_settings()
        return RedisSettings.from_dsn(settings.REDIS_URL)

    # Retry failed jobs up to 3 times with exponential back-off
    max_jobs = 10
    job_timeout = 300  # 5 minutes hard limit per execution
    keep_result = 3600  # keep job result in Redis for 1 hour
    retry_jobs = True
    max_tries = 3


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    from arq.worker import run_worker

    logging.basicConfig(
        level=get_settings().LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    run_worker(WorkerSettings)
