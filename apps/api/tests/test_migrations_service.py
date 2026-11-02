import pytest
from alembic import command
from alembic.config import Config

from shelfsense_api.settings import settings

from .conftest import REPO

pytestmark = pytest.mark.integration


def test_migrations_apply_roll_back_and_reapply(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "database_url", postgres_url)  # migrations/env.py reads it from here
    config = Config(str(REPO / "alembic.ini"))
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
