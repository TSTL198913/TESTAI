import pytest
import threading
from src.users.user_manager import UserManager, UserStatus
from src.security.auth import Role


class TestUserManagerUserIdUnique:
    def test_create_user_concurrent_unique_user_ids(self, tmp_path):
        storage_path = tmp_path / "test_users_concurrent.json"
        user_manager = UserManager(storage_path=str(storage_path), use_database=False)

        created_users = []
        def create_user_thread(user_num):
            try:
                user = user_manager.create_user(
                    username=f"user_{user_num}",
                    email=f"user_{user_num}@test.com",
                    role=Role.TESTER,
                )
                created_users.append(user.user_id)
            except Exception:
                pass

        threads = [threading.Thread(target=create_user_thread, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(created_users)) == len(created_users), "All user_ids should be unique"

    def test_user_id_format_is_consistent(self, tmp_path):
        storage_path = tmp_path / "test_users_format.json"
        user_manager = UserManager(storage_path=str(storage_path), use_database=False)
        
        for i in range(5):
            user = user_manager.create_user(
                username=f"test_{i}",
                email=f"test_{i}@test.com",
                role=Role.TESTER,
            )
            assert user.user_id.startswith("user_"), f"User ID should start with 'user_', got {user.user_id}"
            assert len(user.user_id) == 9, f"User ID should be 9 characters, got {len(user.user_id)}"