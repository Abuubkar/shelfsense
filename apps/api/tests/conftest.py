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
