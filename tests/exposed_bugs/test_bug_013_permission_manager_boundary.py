"""BUG-013: PermissionManager 边界条件测试 - None用户和无效角色处理。

源码位置:src/security/permissions.py:99-134 PermissionManager

测试场景:
1. None用户传入 has_permission/check_permission/get_user_permissions
2. 无效角色(不在ROLE_PERMISSIONS中)的处理
3. 权限枚举值验证

正确行为:
- None用户应返回False/空列表
- 无效角色应返回False/空列表，不应抛出异常
- 权限检查应基于ROLE_PERMISSIONS映射
"""
import pytest
from src.security.permissions import PermissionManager, Permission, PermissionCheckResult
from src.security.auth import User, Role


class TestPermissionManagerBoundary:
    """PermissionManager边界条件测试"""

    def test_has_permission_with_none_user(self):
        """边界：None用户调用has_permission应返回False"""
        pm = PermissionManager()
        result = pm.has_permission(None, Permission.VIEW_HEALTH)
        assert result is False, "None用户应无任何权限"

    def test_check_permission_with_none_user(self):
        """边界：None用户调用check_permission应返回allowed=False"""
        pm = PermissionManager()
        result = pm.check_permission(None, Permission.VIEW_HEALTH)
        assert isinstance(result, PermissionCheckResult)
        assert result.allowed is False
        assert result.user_role is None
        assert result.missing_permissions == [Permission.VIEW_HEALTH]

    def test_get_user_permissions_with_none_user(self):
        """边界：None用户调用get_user_permissions应返回空列表"""
        pm = PermissionManager()
        permissions = pm.get_user_permissions(None)
        assert permissions == [], "None用户应无任何权限"

    def test_has_permission_with_invalid_role(self):
        """边界：无效角色应返回False"""
        pm = PermissionManager()
        invalid_user = User(id="1", username="test", email="test@test.com", role="INVALID_ROLE")
        result = pm.has_permission(invalid_user, Permission.VIEW_HEALTH)
        assert result is False, "无效角色应无任何权限"

    def test_check_permission_with_invalid_role(self):
        """边界：无效角色应返回allowed=False"""
        pm = PermissionManager()
        invalid_user = User(id="1", username="test", email="test@test.com", role="INVALID_ROLE")
        result = pm.check_permission(invalid_user, Permission.VIEW_HEALTH)
        assert isinstance(result, PermissionCheckResult)
        assert result.allowed is False
        assert result.user_role is None
        assert result.missing_permissions == [Permission.VIEW_HEALTH]

    def test_get_user_permissions_with_invalid_role(self):
        """边界：无效角色应返回空列表"""
        pm = PermissionManager()
        invalid_user = User(id="1", username="test", email="test@test.com", role="INVALID_ROLE")
        permissions = pm.get_user_permissions(invalid_user)
        assert permissions == [], "无效角色应无任何权限"

    def test_guest_cannot_approve_patch(self):
        """负向：GUEST角色不能审批补丁"""
        pm = PermissionManager()
        guest_user = User(id="1", username="guest", email="guest@test.com", role=Role.GUEST)
        result = pm.has_permission(guest_user, Permission.APPROVE_PATCH)
        assert result is False, "GUEST角色不应有审批权限"

    def test_tester_can_run_test_but_cannot_manage_users(self):
        """边界：TESTER角色权限边界 - 能运行测试但不能管理用户"""
        pm = PermissionManager()
        tester_user = User(id="1", username="tester", email="tester@test.com", role=Role.TESTER)
        
        can_run_test = pm.has_permission(tester_user, Permission.RUN_TEST)
        can_manage_users = pm.has_permission(tester_user, Permission.MANAGE_USERS)
        
        assert can_run_test is True, "TESTER角色应能运行测试"
        assert can_manage_users is False, "TESTER角色不应能管理用户"
