"""BUG-007: ApprovalManager 类变量污染 + 重复 tx_id 静默返回。

源码位置:src/governance/approval.py:60-77 ApprovalManager + L173-190 create_approval

根因:
1. L63 `_approvals: Dict[str, ApprovalRecord] = {}` 是类变量声明(所有实例共享)
2. L72 `cls._instance._approvals = {}` 在 __new__ 中给单例实例赋实例属性(遮蔽类变量)
   —— 但类变量仍存在于 ApprovalManager.__dict__,可能被类级访问误用
3. L177-183 create_approval 重复 tx_id 时静默返回 existing_record,不抛异常
   —— 掩盖 UUID 碰撞或调用方 bug

现有测试反模式:tests/governance/test_approval.py
- setup_method 用 mgr._approvals.clear() 清理共享状态(测试顺序敏感)
- test_create_duplicate_approval 把"静默返回旧记录"当 expected behavior(L145-162)
"""
import pytest

from src.governance.approval import ApprovalManager
from src.governance.models import PatchProposal, PatchType, DiagnosticContext


def test_approvals_is_not_class_variable():
    """_approvals 不应是类变量,应是实例变量。"""
    class_dict_has_approvals = "_approvals" in ApprovalManager.__dict__

    assert class_dict_has_approvals is False, (
        "_approvals 不应是类变量(会导致跨实例共享状态风险)。"
        f"实际 ApprovalManager.__dict__ 含 _approvals = {ApprovalManager.__dict__.get('_approvals')}"
    )


def test_duplicate_tx_id_should_raise(
    isolated_approval_manager, make_proposal, make_context
):
    """重复 tx_id 应抛 ValueError,而非静默返回旧记录。"""
    mgr = isolated_approval_manager
    mgr.create_approval("tx_dup_test", make_proposal(), make_context())

    with pytest.raises(ValueError, match="duplicate"):
        mgr.create_approval("tx_dup_test", make_proposal(), make_context())


def test_duplicate_tx_id_does_not_silently_return_old_record(
    isolated_approval_manager, make_proposal, make_context
):
    """重复 tx_id 不应静默返回旧记录(调用方无法区分新建 vs 已存在)。"""
    mgr = isolated_approval_manager
    first = mgr.create_approval("tx_dup_silent", make_proposal(), make_context())

    with pytest.raises(ValueError):
        mgr.create_approval("tx_dup_silent", make_proposal(), make_context())


def test_db_lock_not_recreated_in_new():
    """_db_lock 不应在每次 __new__ 中重新创建(单例模式下虽然只执行一次,但设计有隐患)。

    正确行为:_db_lock 应在类级声明一次,不应在 __new__ 中重新赋值。
    """
    import threading
    import inspect

    # 检查 __new__ 源码是否含 _db_lock 赋值
    source = inspect.getsource(ApprovalManager.__new__)
    has_lock_reassign = "_db_lock" in source and "threading.Lock()" in source

    assert has_lock_reassign is False, (
        "_db_lock 不应在 __new__ 中重新创建(单例模式下虽只执行一次,但设计有隐患)。"
        f"__new__ 源码含 _db_lock 重新赋值"
    )
