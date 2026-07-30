"""BUG-004: approve_patch 的 approver 是查询参数,可伪造审批人身份。

源码位置:src/platform/api.py:281-301 approve_patch

根因:
- L284 `approver: str` 是查询参数(无 Depends,无默认值)
- L296 `await orchestrator.approve_and_apply(tx_id, approver, reason)` 用查询参数的 approver
- approval.py:213 `record.approved_by = approver` —— 审计日志记录伪造的 approver
- 已通过 `require_permission(Permission.APPROVE_PATCH)` 获取认证用户 user,但未使用

正确行为:approver 必须从认证用户 user 获取,而非查询参数。
违反用户规则"防御性校验:所有函数入参与跨模块通信必须引入 Pydantic 模型进行强校验"。

现有测试反模式:tests/platform/test_api.py:143-157
- params={"approver": "admin"} 直接传查询参数
- 仅断言 status_code == 200,未验证 approver 来源
- Mock 掉 orchestrator.approve_and_apply,无法验证 approver 参数
"""
import pytest
from unittest.mock import AsyncMock, patch

from src.governance.models import PatchProposal, PatchType, DiagnosticContext


def test_approver_must_be_authenticated_user(
    client, admin_headers, isolated_approval_manager, monkeypatch
):
    """伪造的 approver 查询参数应被忽略,实际 approver 必须是登录用户 admin。

    正确行为(P0-2 修复后):approver 从认证用户 user 获取,查询参数中的 approver 被忽略。
    """
    from src.platform import api as api_module

    # 用隔离的 approval_manager 替换 api 模块全局单例
    monkeypatch.setattr(api_module, "approval_manager", isolated_approval_manager)

    # 创建一条 pending 审批记录(FUNCTIONAL 类型不强制审批,但可被 approve)
    proposal = PatchProposal(
        target_function="test_func",
        suggested_code="pass",
        patch_type=PatchType.FUNCTIONAL,
    )
    context = DiagnosticContext(
        step_id="step_bug_004",
        component_name="test_component",
        input_data={},
        actual_output="",
        expected_baseline="",
    )
    tx_id = "tx_bug_004"
    isolated_approval_manager.create_approval(tx_id, proposal, context)

    # Mock approve_and_apply 捕获 approver 参数(避免真实文件操作)
    with patch.object(
        api_module.orchestrator,
        "approve_and_apply",
        new=AsyncMock(return_value={"status": "FIXED"}),
    ) as mock_apply:
        response = client.post(
            f"/governance/approvals/{tx_id}/approve",
            params={"approver": "someone_else"},
            headers=admin_headers,
        )

    # P0-2 修复后:API 应成功(200),因为 approver 参数被忽略,使用认证用户 admin
    assert response.status_code == 200, (
        f"修复后 API 应接受请求(200),实际: {response.status_code}, response: {response.text}"
    )

    # 验证 approve_and_apply 收到的 approver 必须是认证用户 admin,而非查询参数 someone_else
    call_args = mock_apply.call_args
    assert call_args is not None, "approve_and_apply 必须被调用"
    # approve_and_apply(self, tx_id, approver, reason=None)
    passed_approver = (
        call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("approver")
    )
    assert passed_approver == "admin", (
        f"approver 必须从认证用户获取(应为 'admin'),而非查询参数('someone_else'), "
        f"实际传入: {passed_approver!r}"
    )


def test_approval_record_approved_by_is_authenticated_user(
    client, admin_headers, isolated_approval_manager, monkeypatch
):
    """审批记录的 approved_by 字段必须是认证用户,而非查询参数。

    正确行为:record.approved_by == "admin"(认证用户)。
    """
    from src.platform import api as api_module

    monkeypatch.setattr(api_module, "approval_manager", isolated_approval_manager)
    # 关键:同时替换 orchestrator 内部的 approval_mgr,使 approve_and_apply 使用隔离实例
    monkeypatch.setattr(api_module.orchestrator, "approval_mgr", isolated_approval_manager)

    proposal = PatchProposal(
        target_function="test_func",
        suggested_code="pass",
        patch_type=PatchType.FUNCTIONAL,
    )
    context = DiagnosticContext(
        step_id="step_bug_004_record",
        component_name="test_component",
        input_data={},
        actual_output="",
        expected_baseline="",
    )
    tx_id = "tx_bug_004_record"
    isolated_approval_manager.create_approval(tx_id, proposal, context)

    # Mock executor.apply_patch 避免真实文件修改,但让 approve_and_apply 真实执行
    with patch.object(
        api_module.orchestrator.executor, "apply_patch", new=AsyncMock(return_value=True)
    ), patch.object(api_module.orchestrator.git_mgr, "start_transaction"), \
         patch.object(api_module.orchestrator.git_mgr, "commit"), \
         patch.object(api_module.orchestrator.git_mgr, "rollback"):
        response = client.post(
            f"/governance/approvals/{tx_id}/approve",
            params={"approver": "attacker"},
            headers=admin_headers,
        )

    if response.status_code == 200:
        record = isolated_approval_manager.get_approval(tx_id)
        assert record is not None, "审批记录必须存在"
        assert record.approved_by == "admin", (
            f"approved_by 必须是认证用户 'admin',而非查询参数 'attacker', "
            f"实际: {record.approved_by!r}"
        )
