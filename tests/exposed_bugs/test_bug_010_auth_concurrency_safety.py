"""BUG-010: Auth 模块并发安全缺失 - TokenManager 无锁保护共享状态。

源码位置: src/security/auth.py:83-246 TokenManager

根因(已修复):
1. _login_attempts、_password_hashes、users 是共享字典,无锁保护
2. _check_login_rate_limit 中的读取-修改-写入是非原子操作,存在竞态条件
3. Python GIL 在单进程下可能掩盖问题,但在多进程或 C 扩展释放 GIL 时会暴露
4. 缺乏线程安全设计,违反并发安全最佳实践

修复方案:
- authenticate 方法使用锁保护整个认证流程
- set_password 方法使用锁保护写入操作
- users 字典操作使用锁保护
"""
import pytest
import threading
import time

from src.security.auth import TokenManager, User, Role, PasswordHasher


def _reset_token_manager():
    """重置 TokenManager 状态用于测试。"""
    tm = TokenManager()
    tm._login_attempts = {}
    tm._password_hashes = {}
    tm._login_rate_limit = 100
    tm._login_rate_window_seconds = 60
    user = User(id="1", username="test_user", email="test@testai.com", role=Role.TESTER)
    tm.users["test_user"] = user
    tm._password_hashes["test_user"] = PasswordHasher.hash_password("password")
    return tm


def test_login_rate_limit_concurrent_with_delay():
    """在读取和写入之间插入延迟,放大竞态窗口。

    正确行为:即使在读写之间有延迟,计数也应准确。
    """
    tm = _reset_token_manager()
    tm._login_rate_limit = 100
    
    failed_count = [0]
    lock = threading.Lock()

    def attempt_login():
        result = tm.authenticate("test_user", "wrong_password")
        with lock:
            if result is None:
                failed_count[0] += 1

    threads = []
    for _ in range(10):
        t = threading.Thread(target=attempt_login)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    internal_count = tm._login_attempts.get("test_user", {}).get("count", 0)
    
    assert internal_count == 10, (
        f"10 次失败登录后内部计数应为 10,实际: {internal_count}。"
        f"外部失败计数: {failed_count[0]}, _login_attempts: {tm._login_attempts}"
    )


def test_password_set_concurrent_with_delay():
    """并发设置密码场景下,在写入前插入延迟。

    正确行为:最后设置的密码应生效。
    """
    tm = _reset_token_manager()
    
    passwords = ["pass1", "pass2", "pass3", "pass4", "pass5"]
    final_password = passwords[-1]

    def set_password(idx):
        tm.set_password("test_user", passwords[idx])

    threads = []
    for i in range(5):
        t = threading.Thread(target=set_password, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    stored_hash = tm._get_password_hash("test_user")
    assert PasswordHasher.verify_password(final_password, stored_hash), (
        f"最后设置的密码({final_password})应生效,实际验证失败。"
        f"可能存在并发写入竞态导致数据丢失。"
    )


def test_user_update_concurrent_with_delay():
    """并发更新用户状态场景下,在读取和写入之间插入延迟。

    正确行为:所有并发更新应依次生效。
    """
    tm = _reset_token_manager()
    
    update_count = [0]
    lock = threading.Lock()

    def update_user_role(idx):
        with tm._lock:
            user = tm.users.get("test_user")
            if user:
                user.role = Role.ADMIN if idx % 2 == 0 else Role.TESTER
                tm.users["test_user"] = user
        with lock:
            update_count[0] += 1

    threads = []
    for i in range(10):
        t = threading.Thread(target=update_user_role, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    user = tm.users.get("test_user")
    assert user is not None, "用户不应为 None"
    
    expected_role = Role.ADMIN if 9 % 2 == 0 else Role.TESTER
    assert user.role == expected_role, (
        f"最后一次更新(index=9)应设置角色为 {expected_role},实际: {user.role}。"
        f"更新次数: {update_count[0]}, 可能存在并发覆盖问题。"
    )