"""SQLite adapter tests — runs the full JobRepository contract suite."""

import pytest

from store import SqliteJobRepository


# Import only the test class for inheritance, not for collection
from tests.test_job_repository_port import TestJobRepositoryContract as _Base


class TestSqliteAdapter(_Base):

    @pytest.fixture
    def repo(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        r = SqliteJobRepository(db_path=db_path)
        yield r
        r.close()
