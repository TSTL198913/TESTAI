"""P2-2 GitTransactionManager 回滚分支名一致性测试。

业务规则（基于代码梳理）：
- start_transaction 用 _sanitize_branch_name(tx_id) 创建分支 governance_{sanitized}
- rollback 原用 f"governance_{tx_id}"（原始 tx_id）删除分支
- 当 tx_id 含特殊字符（被 sanitize 替换为 _）时，两者分支名不一致，
  branch -D 删除失败，事务未真正回滚（假回滚）。
- 修复后：rollback 也用 _sanitize_branch_name(tx_id)。

覆盖：正向(一致)/边界(特殊字符)/异常(分支不存在不致命)。
"""
from unittest.mock import MagicMock

import pytest

from src.governance.git_manager import GitTransactionManager


@pytest.fixture
def captured(monkeypatch):
    """mock subprocess.run 并捕获所有 git 命令"""
    cmds = []

    def fake_run(cmd, **kw):
        cmds.append(list(cmd))
        r = MagicMock()
        r.returncode = 0
        r.stderr = ""
        r.stdout = ""
        return r
    monkeypatch.setattr("subprocess.run", fake_run)
    return cmds


@pytest.fixture
def mgr(captured):
    return GitTransactionManager(repo_path=".")


def _arg_after(cmd, flag):
    """返回 cmd 中 flag 后的参数"""
    if flag in cmd:
        return cmd[cmd.index(flag) + 1]
    return None


class TestGitRollbackConsistency:
    """回滚分支名一致性：覆盖正向/边界/异常"""

    def test_rollback_branch_matches_start_special_chars(self, mgr, captured):
        """正向：tx_id 含特殊字符，rollback 删除分支名 == start 创建分支名"""
        tx_id = "tx_a/b:c"
        mgr.start_transaction(tx_id)
        start_create = [c for c in captured if "-b" in c]
        start_branch = _arg_after(start_create[-1], "-b")

        mgr.rollback(tx_id)
        delete = [c for c in captured if "-D" in c]
        delete_branch = _arg_after(delete[-1], "-D")

        # 关键断言：回滚删除的分支名与创建的一致（都用 sanitized）
        assert delete_branch == start_branch, (
            f"回滚分支名不一致: start={start_branch!r}, rollback={delete_branch!r}"
        )
        # 验证确实经过 sanitize（特殊字符被替换）
        assert "/" not in delete_branch
        assert ":" not in delete_branch

    def test_plain_tx_id_consistent(self, mgr, captured):
        """边界：普通 tx_id（无特殊字符）回滚一致"""
        tx_id = "tx_001"
        mgr.start_transaction(tx_id)
        start_branch = _arg_after([c for c in captured if "-b" in c][-1], "-b")

        mgr.rollback(tx_id)
        delete_branch = _arg_after([c for c in captured if "-D" in c][-1], "-D")

        assert delete_branch == start_branch == mgr._sanitize_branch_name(tx_id)

    def test_rollback_branch_not_exist_does_not_raise(self, monkeypatch):
        """异常：回滚时分支不存在不应致命抛出（被捕获，不影响 checkout）"""
        import subprocess as sp

        def selective_run(cmd, **kw):
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            r.stdout = ""
            return r

        # checkout -b 阶段让 show-ref 返回存在（returncode=0）以走 branch -D 清理
        monkeypatch.setattr(sp, "run", selective_run)
        mgr = GitTransactionManager(repo_path=".")

        # rollback 内 branch -D 失败应被捕获
        def fail_delete(cmd, **kw):
            if "-D" in cmd:
                raise sp.CalledProcessError(returncode=1, cmd=cmd)
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            r.stdout = ""
            return r
        monkeypatch.setattr(sp, "run", fail_delete)

        # 不应抛出
        mgr.rollback("tx_any")
