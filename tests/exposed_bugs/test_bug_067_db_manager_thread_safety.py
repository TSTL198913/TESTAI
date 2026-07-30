import threading
import pytest
from src.storage.database import DatabaseManager, reset_db_manager


class TestDatabaseManagerThreadSafety:
    def setup_method(self):
        reset_db_manager()

    def teardown_method(self):
        reset_db_manager()

    def test_concurrent_init_thread_safe(self):
        errors = []

        def init_db():
            try:
                db = DatabaseManager()
                assert db is not None
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(10):
            t = threading.Thread(target=init_db)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"

    def test_concurrent_insert_thread_safe(self):
        db = DatabaseManager()
        errors = []
        insert_count = 0
        count_lock = threading.Lock()

        def insert_data():
            nonlocal insert_count
            try:
                import uuid
                db.insert_one(db.system_config_table, {
                    "key": f"test_key_{uuid.uuid4().hex[:8]}",
                    "value": "test_value",
                    "description": "test"
                })
                with count_lock:
                    insert_count += 1
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(20):
            t = threading.Thread(target=insert_data)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors during insert: {errors}"
        assert insert_count == 20, f"Expected 20 inserts, got {insert_count}"