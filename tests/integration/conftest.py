import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def postgres_engine() -> Iterator[Engine]:
    database_url = os.getenv("GEARWATCH_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("GEARWATCH_TEST_DATABASE_URL is not configured")

    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(postgres_engine: Engine) -> Iterator[Session]:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()

