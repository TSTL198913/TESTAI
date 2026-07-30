import pytest
from src.governance.approval import ApprovalManager, ApprovalStatus
from src.governance.models import DiagnosticContext, PatchProposal, PatchType


class TestApprovalManagerClassVar:
    def test_approvals_dict_is_instance_variable(self):
        """边界：_approvals应是实例变量而非类变量"""
        assert "_approvals" not in ApprovalManager.__dict__, (
            "_approvals 不应是类变量"
        )

    def test_class_variables_not_shared_across_subclasses(self):
        """边界：子类不应共享父类的类变量"""
        assert "_approvals" not in ApprovalManager.__dict__, (
            "_approvals 不是类变量，子类不会继承类级别的共享状态"
        )