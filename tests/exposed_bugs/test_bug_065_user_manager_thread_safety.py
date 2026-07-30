"""BUG-065: UserManager 线程安全缺失 - 并发操作 users 字典无锁保护。

源码位置: src/users/user_manager.py:55

根因:
1. create_user、update_user、delete_user、list_users 等方法无锁保护
2. 多线程并发操作 self.users 字典会导致数据损坏
3. 用户ID生成使用 len(self.users)+1，并发时会产生重复ID

正确行为:
- 所有对 self.users 的读写操作必须用锁保护
- 用户ID应使用UUID而非计数器
"""
import pytest
import threading
import time
import os
import tempfile

from src.users.user_manager import UserManager, UserStatus
from src.security.auth import Role


class TestUserManagerThreadSafety:
    """UserManager线程安全测试"""

    def setup_method(self):
        UserManager._instance = None

    def teardown_method(self):
        UserManager._instance = None

    def test_create_user_concurrent_thread_safe(self):
        """并发创建用户时，所有用户应正确记录"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = os.path.join(tmp_dir, "users.json")
            user_manager = UserManager(storage_path=storage_path)
            
            errors = []
            created_users = []
            
            def create_user_thread(thread_id):
                try:
                    for i in range(10):
                        user = user_manager.create_user(
                            username=f"user_{thread_id}_{i}",
                            email=f"user_{thread_id}_{i}@test.com",
                            role=Role.TESTER,
                            status=UserStatus.ACTIVE,
                        )
                        created_users.append(user.user_id)
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(f"Thread {thread_id} error: {e}")
            
            threads = []
            for i in range(5):
                t = threading.Thread(target=create_user_thread, args=(i,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            assert len(errors) == 0, f"Thread errors occurred: {errors}"
            assert len(created_users) == 50, (
                f"Expected 50 created users, got {len(created_users)}"
            )
            assert len(set(created_users)) == 50, (
                f"Expected all unique user IDs, got duplicates: {len(created_users) - len(set(created_users))}"
            )

    def test_update_user_concurrent_thread_safe(self):
        """并发更新用户时，所有更新应正确应用"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = os.path.join(tmp_dir, "users.json")
            user_manager = UserManager(storage_path=storage_path)
            
            users = []
            for i in range(20):
                user = user_manager.create_user(
                    username=f"update_user_{i}",
                    email=f"update_user_{i}@test.com",
                    role=Role.TESTER,
                )
                users.append(user)
            
            errors = []
            
            def update_user_thread(thread_id):
                try:
                    start_idx = thread_id * 5
                    end_idx = start_idx + 5
                    for user in users[start_idx:end_idx]:
                        updated = user_manager.update_user(
                            user.user_id,
                            department=f"Department_{thread_id}",
                        )
                        assert updated is not None, f"Failed to update {user.user_id}"
                        assert updated.department == f"Department_{thread_id}"
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(f"Thread {thread_id} error: {e}")
            
            threads = []
            for i in range(4):
                t = threading.Thread(target=update_user_thread, args=(i,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            assert len(errors) == 0, f"Thread errors occurred: {errors}"
            for i, user in enumerate(users):
                expected_dept = f"Department_{i // 5}"
                assert user.department == expected_dept, (
                    f"User {user.user_id} expected department {expected_dept}, got {user.department}"
                )

    def test_delete_user_concurrent_thread_safe(self):
        """并发删除用户时，应正确删除"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = os.path.join(tmp_dir, "users.json")
            user_manager = UserManager(storage_path=storage_path)
            
            initial_count = len(user_manager.users)
            users = []
            for i in range(20):
                user = user_manager.create_user(
                    username=f"delete_user_{i}",
                    email=f"delete_user_{i}@test.com",
                    role=Role.TESTER,
                )
                users.append(user)
            
            errors = []
            
            def delete_user_thread(thread_id):
                try:
                    start_idx = thread_id * 5
                    end_idx = start_idx + 5
                    for user in users[start_idx:end_idx]:
                        result = user_manager.delete_user(user.user_id)
                        assert result is True, f"Failed to delete {user.user_id}"
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(f"Thread {thread_id} error: {e}")
            
            threads = []
            for i in range(4):
                t = threading.Thread(target=delete_user_thread, args=(i,))
                threads.append(t)
                t.start()
            
            for t in threads:
                t.join()
            
            assert len(errors) == 0, f"Thread errors occurred: {errors}"
            assert len(user_manager.users) == initial_count, (
                f"Expected {initial_count} users after deletion (default users remain), "
                f"got {len(user_manager.users)}"
            )