"""P0-4 补强: 密码文件权限校验测试。

验证 UserManager 在写入密码哈希文件时:
1. 检测已存在文件权限过松(非 owner 可读)时抛 PermissionError
2. 写入后设置严格权限(0o600,仅 owner 可读写)
3. Windows 环境跳过权限校验(记日志)
"""
import os
import stat
import sys

import pytest

from src.users.user_manager import UserManager


@pytest.mark.skipif(sys.platform == "win32", reason="Unix 权限模式在 Windows 上无意义")
def test_password_file_mode_strict(tmp_path, monkeypatch):
    """Unix: 已存在密码文件权限过松(0o644)时,写入必须抛 PermissionError。"""
    # 创建一个权限过松的密码文件
    storage_path = tmp_path / "users.json"
    storage_path.write_text("{}", encoding="utf-8")
    os.chmod(str(storage_path), 0o644)  # group/other 可读 - 不安全

    monkeypatch.setenv("ENVIRONMENT", "development")
    with pytest.raises(PermissionError, match="overly permissive"):
        UserManager(storage_path=str(storage_path), use_database=False)


@pytest.mark.skipif(sys.platform == "win32", reason="Unix 权限模式在 Windows 上无意义")
def test_password_file_mode_set_after_write(tmp_path, monkeypatch):
    """Unix: 写入后文件权限必须为 0o600(仅 owner 可读写)。"""
    storage_path = tmp_path / "users.json"
    monkeypatch.setenv("ENVIRONMENT", "development")

    # 文件不存在,创建后应设置严格权限
    mgr = UserManager(storage_path=str(storage_path), use_database=False)
    mgr.create_user(
        username="newuser",
        email="new@test.com",
        role=__import__("src.security.auth", fromlist=["Role"]).Role.TESTER,
    )

    # 重新读取文件权限
    file_stat = os.stat(str(storage_path))
    file_mode = stat.S_IMODE(file_stat.st_mode)
    assert file_mode == 0o600, (
        f"密码文件权限必须为 0o600(仅 owner 可读写),实际: {oct(file_mode)}"
    )


def test_password_file_mode_strict_windows_skip(monkeypatch):
    """Windows: 跳过权限校验,不抛异常。"""
    # 模拟 Windows 环境
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setenv("ENVIRONMENT", "development")

    # 应该不抛 PermissionError
    try:
        from src.users.user_manager import UserManager
        # 使用临时路径避免污染真实数据
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "users.json")
            UserManager(storage_path=storage_path, use_database=False)
    except PermissionError:
        pytest.fail("Windows 环境不应抛 PermissionError")


@pytest.mark.skipif(sys.platform == "win32", reason="Unix 权限模式在 Windows 上无意义")
def test_password_file_strict_mode_does_not_raise(tmp_path, monkeypatch):
    """Unix: 已存在文件权限严格(0o600)时,正常加载不抛异常。"""
    storage_path = tmp_path / "users.json"
    storage_path.write_text("{}", encoding="utf-8")
    os.chmod(str(storage_path), 0o600)  # 严格权限 - 安全

    monkeypatch.setenv("ENVIRONMENT", "development")
    # 不应抛异常
    mgr = UserManager(storage_path=str(storage_path), use_database=False)
    assert mgr is not None
