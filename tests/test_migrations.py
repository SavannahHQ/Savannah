import pytest

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db


def test_test_database_is_built_by_running_every_migration():
    """The suite's PostgreSQL database comes from the migrations, with none left to apply."""
    executor = MigrationExecutor(connection)

    assert connection.vendor == "postgresql"
    assert executor.loader.applied_migrations
    assert not executor.migration_plan(executor.loader.graph.leaf_nodes())


def test_models_have_no_missing_migrations():
    """Every model change is covered by a migration."""
    call_command("makemigrations", check=True, dry_run=True)
