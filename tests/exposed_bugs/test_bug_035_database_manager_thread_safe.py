import pytest
import threading
from src.storage.database import DatabaseManager, reset_db_manager


class TestDatabaseManagerThreadSafe:
    def test_singleton_is_thread_safe(self):
        reset_db_manager()
        DatabaseManager._instance = None

        instances = []
        def get_instance():
            db = DatabaseManager()
            instances.append(db)

        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(id(i) for i in instances)) == 1, "All threads should get the same singleton instance"

    def test_multiple_initialization_produces_single_instance(self):
        reset_db_manager()
        DatabaseManager._instance = None

        db1 = DatabaseManager()
        db2 = DatabaseManager()

        assert id(db1) == id(db2), "Multiple initialization should return same instance"