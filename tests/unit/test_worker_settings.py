"""Regression tests for the ARQ worker settings."""

from arq.connections import RedisSettings
from arq.cron import CronJob

from app.config.settings import get_settings
from app.workers.main import WorkerSettings, fire_schedules


def test_worker_cron_jobs_use_arq_cronjob_instances() -> None:
    assert len(WorkerSettings.cron_jobs) == 1
    job = WorkerSettings.cron_jobs[0]

    assert isinstance(job, CronJob)
    assert job.coroutine is fire_schedules
    assert job.minute == set(range(60))


def test_worker_redis_settings_is_built_from_configured_url() -> None:
    configured = RedisSettings.from_dsn(get_settings().REDIS_URL)
    actual = WorkerSettings.redis_settings

    assert isinstance(actual, RedisSettings)
    assert (actual.host, actual.port, actual.database) == (
        configured.host,
        configured.port,
        configured.database,
    )
