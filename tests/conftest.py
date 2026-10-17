"""
Shared pytest fixtures for FlowForge tests.

Unit tests use an in-memory SQLite DB (no Docker required).
Integration tests require a real PostgreSQL + Redis stack
(start with: docker compose up db redis -d).
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import make_url
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

# ── In-memory SQLite for unit tests ───────────────────────────────────────────

SQLITE_URL = "sqlite:///:memory:"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs) -> str:
    """Use SQLite JSON storage in tests that only persist JSON documents."""
    return "JSON"


@pytest.fixture(scope="function")
def sqlite_engine():
    """Fresh SQLite engine + schema for each test function."""
    # Import all models so Base.metadata is populated
    import app.models  # noqa: F401
    from app.models.base import Base

    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def postgres_engine():
    """Use an empty test database initialized by Alembic, never ORM create_all."""
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not raw_url:
        raise pytest.UsageError("TEST_DATABASE_URL is required for the PostgreSQL test fixture")
    url = make_url(raw_url)
    if not (
        url.drivername.startswith("postgresql")
        and url.username == "flowforge_test"
        and url.password == "flowforge_test_password"
        and url.database == "flowforge_test"
        and (
            (url.host in {"localhost", "127.0.0.1", "::1"} and url.port == 5433)
            # A separately launched, disposable PostgreSQL instance for migration
            # verification uses tmpfs and is published on this dedicated port.
            or (
                url.host in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
                and url.port == 55432
            )
            # When tests run in a container attached to Compose's project network,
            # db_test resolves directly to that service on its internal port.
            or (url.host == "db_test" and url.port == 5432)
        )
    ):
        raise pytest.UsageError(
            "PostgreSQL tests are restricted to flowforge_test with the configured "
            "test credentials at Compose db_test (localhost:5433 or db_test:5432) "
            "or the disposable localhost:55432 instance"
        )

    engine = create_engine(raw_url, pool_pre_ping=True)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names(schema="public"))

    if "alembic_version" not in tables:
        if tables:
            engine.dispose()
            raise pytest.UsageError(
                "Refusing to modify a non-empty PostgreSQL test database without "
                "Alembic revision tracking. Use a fresh disposable database."
            )
        if url.port != 55432 or url.host not in {
            "localhost",
            "127.0.0.1",
            "::1",
            "host.docker.internal",
        }:
            engine.dispose()
            raise pytest.UsageError(
                "Only the dedicated disposable PostgreSQL instance on localhost:55432 "
                "may be initialized by the test fixture."
            )

        # Only bootstrap a completely empty public schema. This prevents the test
        # fixture from silently altering an existing or untracked test database.
        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = raw_url
        from app.config.settings import get_settings

        get_settings.cache_clear()
        try:
            from alembic import command
            from alembic.config import Config

            repo_root = Path(__file__).resolve().parents[1]
            alembic_config = Config(str(repo_root / "alembic.ini"))
            alembic_config.set_main_option(
                "script_location", str(repo_root / "migrations")
            )
            command.upgrade(alembic_config, "head")
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url
            get_settings.cache_clear()

        with engine.connect() as connection:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one_or_none()
        if revision != "0004_trigger_type_alignment":
            engine.dispose()
            raise pytest.UsageError(
                "Alembic did not initialize the disposable PostgreSQL database at head; "
                f"found {revision!r}"
            )
    else:
        with engine.connect() as connection:
            revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one_or_none()
        if revision != "0004_trigger_type_alignment":
            engine.dispose()
            raise pytest.UsageError(
                "PostgreSQL test database must already be at Alembic head; "
                f"found {revision!r}. The fixture will not upgrade an existing database."
            )

    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db(request) -> Generator[Session, None, None]:
    """Use SQLite by default, or an isolated PostgreSQL transaction when opted in."""
    if os.environ.get("TEST_DATABASE_URL"):
        engine = request.getfixturevalue("postgres_engine")
        connection = engine.connect()
        outer_transaction = connection.begin()
        SessionLocal = sessionmaker(
            bind=connection,
            autocommit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
            if outer_transaction.is_active:
                outer_transaction.rollback()
            connection.close()
        return

    sqlite_engine = request.getfixturevalue("sqlite_engine")
    SessionLocal = sessionmaker(bind=sqlite_engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── Sample graph fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def minimal_graph() -> dict:
    """manual_trigger → set_data node (simplest valid graph)."""
    return {
        "nodes": [
            {"id": "trigger_1", "type": "manual_trigger", "config": {}},
            {
                "id": "set_1",
                "type": "set_data",
                "config": {"fields": [{"key": "hello", "value": "world"}]},
            },
        ],
        "edges": [
            {"id": "e1", "source": "trigger_1", "target": "set_1"},
        ],
    }


@pytest.fixture
def if_branch_graph() -> dict:
    """manual_trigger → if_condition → (true) set_data_a / (false) set_data_b"""
    return {
        "nodes": [
            {"id": "t1", "type": "manual_trigger", "config": {}},
            {"id": "if1", "type": "if_condition", "config": {"condition": "1 == 1"}},
            {
                "id": "a",
                "type": "set_data",
                "config": {"fields": [{"key": "branch", "value": "true_branch"}]},
            },
            {
                "id": "b",
                "type": "set_data",
                "config": {"fields": [{"key": "branch", "value": "false_branch"}]},
            },
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "if1"},
            {"id": "e2", "source": "if1", "target": "a", "source_handle": "true"},
            {"id": "e3", "source": "if1", "target": "b", "source_handle": "false"},
        ],
    }


# ── FastAPI TestClient (unit — overrides DB dep) ──────────────────────────────

@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    """
    TestClient with DB dependency overridden to use the in-memory SQLite session.
    JWT auth is also handled via a helper below.
    """
    from app.api.deps import get_db
    from app.main import app

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
