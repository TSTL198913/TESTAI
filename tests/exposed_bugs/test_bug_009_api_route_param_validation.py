"""BUG-009: API 路由参数验证缺失 - approver 参数可伪造 + 未验证身份。

源码位置: src/platform/api.py approve_patch / reject_patch

根因(已修复):
1. approve_patch 的 `approver` 参数是直接从请求获取的字符串,未验证是否为当前登录用户
   —— 攻击者可伪造 approver=admin 绕过身份验证
2. reject_patch 同样存在此问题
3. 路由返回成功时未验证实际审批操作是否成功

修复方案(P0-2):
- 移除 approve_patch 的 `approver` 查询参数
- 移除 reject_patch 的 `approver` 查询参数
- approver 强制取自认证用户的 user.username
- 即使前端传入 approver 参数,API 也会忽略并使用认证用户

本测试验证修复后的正确行为:伪造的 approver 参数被忽略,实际 approver 是认证用户。
"""
import pytest
from unittest.mock import AsyncMock, patch

from src.platform.api import app
from src.security.auth import TokenManager, User, Role
from src.governance.approval import ApprovalManager, ApprovalStatus, ApprovalRecord
from src.governance.models import PatchProposal, PatchType, DiagnosticContext


# 使用 conftest.py 的标准 client / admin_headers fixture
# 避免自定义 fixture 与全局 token_manager 状态不一致导致 401


@patch("src.platform.api.approval_manager")
@patch("src.platform.api.orchestrator")
def test_approve_patch_verifies_approver_identity(
    mock_orchestrator, mock_approval_manager, client, admin_headers
):
    """approve_patch 必须忽略查询参数 approver,强制使用认证用户。

    正确行为(已修复):即使 URL 中带 approver=hacker,实际 approver 必须是认证用户 admin。
    """
    mock_approval_manager.get_approval.return_value = ApprovalRecord(
        tx_id="tx_test",
        proposal=PatchProposal(target_function="test", suggested_code="pass"),
        context=DiagnosticContext(step_id="s1", component_name="c1", input_data={}, actual_output="", expected_baseline=""),
    )

    mock_orchestrator.approve_and_apply = AsyncMock(return_value={
        "status": "FIXED",
        "tx_id": "tx_test",
        "approved_by": "admin",
    })

    response = client.post(
        "/governance/approvals/tx_test/approve?approver=hacker&reason=test",
        headers=admin_headers,
    )

    assert response.status_code == 200, (
        f"修复后 approve_patch 应成功(200),实际: {response.status_code}, "
        f"response: {response.text}"
    )

    # 关键断言:approve_and_apply 必须收到 admin(认证用户),而非 hacker(查询参数)
    call_args = mock_orchestrator.approve_and_apply.call_args
    assert call_args is not None, "approve_and_apply 必须被调用"
    # approve_and_apply(self, tx_id, approver, reason=None)
    passed_approver = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("approver")
    assert passed_approver == "admin", (
        f"approver 必须从认证用户获取('admin'),而非查询参数('hacker'), "
        f"实际传入: {passed_approver!r}"
    )


@patch("src.platform.api.approval_manager")
def test_reject_patch_verifies_approver_identity(
    mock_approval_manager, client, admin_headers
):
    """reject_patch 必须忽略查询参数 approver,强制使用认证用户。"""
    mock_approval_manager.get_approval.return_value = ApprovalRecord(
        tx_id="tx_test",
        proposal=PatchProposal(target_function="test", suggested_code="pass"),
        context=DiagnosticContext(step_id="s1", component_name="c1", input_data={}, actual_output="", expected_baseline=""),
    )
    mock_approval_manager.reject.return_value = True

    response = client.post(
        "/governance/approvals/tx_test/reject?approver=hacker&reason=test",
        headers=admin_headers,
    )

    assert response.status_code == 200, (
        f"修复后 reject_patch 应成功(200),实际: {response.status_code}, "
        f"response: {response.text}"
    )

    # 关键断言:reject 必须收到 admin(认证用户),而非 hacker(查询参数)
    call_args = mock_approval_manager.reject.call_args
    assert call_args is not None, "reject 必须被调用"
    # reject(self, tx_id, approver, reason)
    passed_approver = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("approver")
    assert passed_approver == "admin", (
        f"approver 必须从认证用户获取('admin'),而非查询参数('hacker'), "
        f"实际传入: {passed_approver!r}"
    )


@patch("src.platform.api.approval_manager")
def test_approve_patch_validates_operation_result(
    mock_approval_manager, client, admin_headers
):
    """approve_patch 必须验证 approval_manager.approve 的返回值,而非直接返回成功。

    正确行为:当 approve_and_apply 返回 FAILED 时,应返回 success=False。
    """
    mock_approval_manager.get_approval.return_value = ApprovalRecord(
        tx_id="tx_test",
        proposal=PatchProposal(target_function="test", suggested_code="pass"),
        context=DiagnosticContext(step_id="s1", component_name="c1", input_data={}, actual_output="", expected_baseline=""),
    )
    with patch("src.platform.api.orchestrator.approve_and_apply", new=AsyncMock(
        return_value={"status": "FAILED", "reason": "apply_patch failed"}
    )):
        response = client.post(
            "/governance/approvals/tx_test/approve?reason=test",
            headers=admin_headers,
        )

    data = response.json()
    assert not data.get("success", True), (
        f"当 approve 操作失败时,API 应返回 success=False,实际: {data}"
    )
