"""BUG-070: Approval过期处理测试

问题描述: ApprovalRecord的is_expired属性是动态计算的，
但在requires_approval方法中，过期记录的状态更新可能存在问题。

成功指标: 
1. 过期记录的requires_approval应返回True（需要重新审批）
2. 过期记录的状态应被正确更新为EXPIRED
3. 已过期的记录不能被批准

失败指标:
1. 过期记录的状态未被更新为EXPIRED
2. 过期记录的requires_approval返回False
3. 已过期的记录被错误批准
"""
import pytest
from datetime import datetime, timedelta

from src.governance.approval import ApprovalManager, ApprovalStatus
from src.governance.models import DiagnosticContext, PatchProposal, PatchType


class TestBug070ApprovalExpireHandling:
    """验证Approval过期处理逻辑"""

    def _create_manager(self, tmp_path, db_name):
        """创建独立的ApprovalManager实例"""
        ApprovalManager._instance = None
        db_path = tmp_path / db_name
        return ApprovalManager(db_path=str(db_path))

    def test_expired_approval_status_update(self, tmp_path):
        """过期的审批记录状态应被正确更新为EXPIRED"""
        mgr = self._create_manager(tmp_path, "expire_status.db")
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        mgr.create_approval("tx_expire_test", proposal, context)

        record = mgr.get_approval("tx_expire_test")
        record.expires_at = datetime.now() - timedelta(minutes=1)

        result = mgr.get_approval("tx_expire_test")

        assert result.status == ApprovalStatus.EXPIRED, (
            f"过期记录状态应为EXPIRED，实际: {result.status.value}"
        )

    def test_expired_approval_requires_approval(self, tmp_path):
        """过期的审批记录requires_approval应返回True"""
        mgr = self._create_manager(tmp_path, "expire_requires.db")
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        mgr.create_approval("tx_expire_requires", proposal, context)

        record = mgr.get_approval("tx_expire_requires")
        record.expires_at = datetime.now() - timedelta(minutes=1)

        result = mgr.requires_approval("tx_expire_requires")

        assert result is True, (
            f"过期的SECURITY类型审批应返回True，实际: {result}"
        )

    def test_expired_approval_cannot_be_approved(self, tmp_path):
        """已过期的审批记录不能被批准"""
        mgr = self._create_manager(tmp_path, "expire_approve.db")
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        mgr.create_approval("tx_expire_approve", proposal, context)

        record = mgr.get_approval("tx_expire_approve")
        record.expires_at = datetime.now() - timedelta(minutes=1)

        result = mgr.approve("tx_expire_approve", "tech_committee")

        assert result is False, (
            f"已过期的审批应拒绝批准，实际返回: {result}"
        )

        record = mgr.get_approval("tx_expire_approve")
        assert record.status == ApprovalStatus.EXPIRED, (
            f"过期后尝试批准，状态应为EXPIRED，实际: {record.status.value}"
        )

    def test_expired_approval_cannot_be_rejected(self, tmp_path):
        """已过期的审批记录不能被拒绝"""
        mgr = self._create_manager(tmp_path, "expire_reject.db")
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        mgr.create_approval("tx_expire_reject", proposal, context)

        record = mgr.get_approval("tx_expire_reject")
        record.expires_at = datetime.now() - timedelta(minutes=1)

        result = mgr.reject("tx_expire_reject", "tech_committee", "Expired")

        assert result is False, (
            f"已过期的审批应拒绝拒绝操作，实际返回: {result}"
        )

        record = mgr.get_approval("tx_expire_reject")
        assert record.status == ApprovalStatus.EXPIRED, (
            f"过期后尝试拒绝，状态应为EXPIRED，实际: {record.status.value}"
        )

    def test_cleanup_expired_updates_status(self, tmp_path):
        """cleanup_expired应正确更新过期记录状态"""
        mgr = self._create_manager(tmp_path, "expire_cleanup.db")
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.FUNCTIONAL,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        mgr.create_approval("tx_cleanup", proposal, context)

        record = mgr.get_approval("tx_cleanup")
        record.expires_at = datetime.now() - timedelta(minutes=1)

        mgr.cleanup_expired()

        record = mgr.get_approval("tx_cleanup")
        assert record.status == ApprovalStatus.EXPIRED, (
            f"cleanup_expired后状态应为EXPIRED，实际: {record.status.value}"
        )

    def test_list_pending_excludes_expired(self, tmp_path):
        """list_pending不应包含过期记录"""
        mgr = self._create_manager(tmp_path, "expire_pending.db")
        proposal = PatchProposal(
            target_function="test_func",
            suggested_code="pass",
            patch_type=PatchType.SECURITY,
        )
        context = DiagnosticContext(
            step_id="test_step",
            component_name="test_component",
            input_data={},
            actual_output="",
            expected_baseline="",
        )
        mgr.create_approval("tx_pending_expired", proposal, context)

        record = mgr.get_approval("tx_pending_expired")
        record.expires_at = datetime.now() - timedelta(minutes=1)

        pending = mgr.list_pending()

        assert len(pending) == 0, (
            f"list_pending不应包含过期记录，实际: {len(pending)}"
        )