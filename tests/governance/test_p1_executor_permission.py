"""P1-5 GovernanceExecutor 权限授予测试。

业务规则（基于代码梳理）：
- executor._grant_write_permission 在 chmod 失败时回退到 icacls，
  原实现 `icacls /grant Users:F` 给本机所有用户完全控制权，过度授权。
- 修复后：仅授予当前用户修改权限(M) `icacls /grant {username}:M`，
  并为 subprocess.run 增加 timeout 与具体异常捕获。

覆盖：正向(授予当前用户M)/负向(不得Users:F)/边界(无用户名)/异常(icacls失败)。
"""
import subprocess
from unittest.mock import MagicMock

import pytest

from src.governance.executor import GovernanceExecutor


@pytest.fixture
def executor():
    return GovernanceExecutor()


class TestExecutorPermission:
    """权限授予：覆盖正向/负向/边界/异常"""

    def test_icacls_grants_current_user_modify_not_users_full(self, executor, monkeypatch, tmp_path):
        """正向+负向：icacls 仅授予当前用户 M，绝不含 Users:F"""
        target = tmp_path / "target.py"
        target.write_text("x = 1")

        # 让 chmod 与 stat 失败，强制走 icacls 分支
        def _raise(*a, **k):
            raise PermissionError("mock chmod fail")
        monkeypatch.setattr("pathlib.Path.chmod", _raise)
        monkeypatch.setattr("pathlib.Path.stat", _raise)
        monkeypatch.setenv("USERNAME", "testuser")

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            r.stdout = ""
            return r
        monkeypatch.setattr("subprocess.run", fake_run)

        result = executor._grant_write_permission(target)

        assert result is True
        assert len(calls) == 1, "应调用一次 icacls"
        cmd = calls[0]
        # 负向断言：不得出现 Users:F 完全控制
        assert "Users:F" not in cmd, "禁止授予 Users:F 完全控制权限"
        assert not any(str(a) == "Users:F" for a in cmd)
        # 正向断言：授予当前用户修改权限
        assert "testuser:M" in cmd, "应授予当前用户修改权限(M)"

    def test_icacls_failure_returns_false(self, executor, monkeypatch, tmp_path):
        """异常：icacls returncode != 0 时返回 False"""
        target = tmp_path / "t.py"
        target.write_text("x=1")

        def _raise(*a, **k):
            raise PermissionError("mock")
        monkeypatch.setattr("pathlib.Path.chmod", _raise)
        monkeypatch.setattr("pathlib.Path.stat", _raise)
        monkeypatch.setenv("USERNAME", "testuser")

        def fake_run(cmd, **kwargs):
            r = MagicMock()
            r.returncode = 1
            r.stderr = "access denied"
            r.stdout = ""
            return r
        monkeypatch.setattr("subprocess.run", fake_run)

        assert executor._grant_write_permission(target) is False

    def test_no_username_returns_false(self, executor, monkeypatch, tmp_path):
        """边界：无法确定当前用户时返回 False，不调用 icacls"""
        target = tmp_path / "t.py"
        target.write_text("x=1")

        def _raise(*a, **k):
            raise PermissionError("mock")
        monkeypatch.setattr("pathlib.Path.chmod", _raise)
        monkeypatch.setattr("pathlib.Path.stat", _raise)
        # 清除所有用户名环境变量
        monkeypatch.delenv("USERNAME", raising=False)
        monkeypatch.delenv("USER", raising=False)
        # os.getlogin 抛 OSError
        monkeypatch.setattr("os.getlogin", lambda: (_ for _ in ()).throw(OSError("no tty")))

        calls = []
        monkeypatch.setattr("subprocess.run", lambda *a, **k: calls.append(a))

        assert executor._grant_write_permission(target) is False
        assert calls == [], "无用户名时不得调用 icacls"

    def test_icacls_timeout_handled(self, executor, monkeypatch, tmp_path):
        """异常：icacls 超时被捕获，返回 False 而非抛出"""
        target = tmp_path / "t.py"
        target.write_text("x=1")

        def _raise(*a, **k):
            raise PermissionError("mock")
        monkeypatch.setattr("pathlib.Path.chmod", _raise)
        monkeypatch.setattr("pathlib.Path.stat", _raise)
        monkeypatch.setenv("USERNAME", "testuser")

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=10)
        monkeypatch.setattr("subprocess.run", fake_run)

        # 不应抛出，应返回 False
        assert executor._grant_write_permission(target) is False
