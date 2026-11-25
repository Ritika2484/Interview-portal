import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db


def test_pgvector_extension_and_distance_operator():
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        assert cursor.fetchone()[0].startswith("0.8.")
        cursor.execute("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")
        assert cursor.fetchone()[0] == 1.0


def test_all_migrations_applied():
    executor = MigrationExecutor(connection)
    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
