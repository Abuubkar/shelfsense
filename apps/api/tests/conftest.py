from collections.abc import Iterator
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def opensearch_url() -> Iterator[str]:
    """A throwaway single-node OpenSearch, the same version as docker-compose."""
    from testcontainers.community.opensearch import OpenSearchContainer

    container = OpenSearchContainer("opensearchproject/opensearch:3.9.0").with_env(
        "OPENSEARCH_JAVA_OPTS", "-Xms512m -Xmx512m"
    )
    with container:
        config = container.get_config()
        yield f"http://{config['host']}:{config['port']}"


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A throwaway Postgres with pgvector, the same image as docker-compose."""
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("pgvector/pgvector:0.8.7-pg18-trixie", driver="asyncpg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def floci_url() -> Iterator[str]:
    """A throwaway Floci (SQS and S3), the same image as docker-compose, in memory."""
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import HttpWaitStrategy

    container = (DockerContainer("floci/floci:2.3.0").with_exposed_ports(4566)
                 .waiting_for(HttpWaitStrategy(4566, "/_floci/health")))
    with container:
        yield f"http://{container.get_container_host_ip()}:{container.get_exposed_port(4566)}"


@pytest.fixture(scope="session")
def migrated_postgres_url(postgres_url: str) -> str:
    """The Postgres container with every migration applied."""
    from alembic import command
    from alembic.config import Config

    from shelfsense_api.settings import settings

    original, settings.database_url = settings.database_url, postgres_url  # migrations/env.py reads it from here
    try:
        command.upgrade(Config(str(REPO / "alembic.ini")), "head")
    finally:
        settings.database_url = original
    return postgres_url
