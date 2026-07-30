import pytest

from src.security.auth import User, Role
from src.security.permissions import PermissionManager, Permission, PermissionCheckResult


class TestPermission:
    """权限枚举测试"""

    @pytest.mark.parametrize("permission,expected_value", [
        (Permission.VIEW_HEALTH, "view_health"),
        (Permission.VIEW_CONFIG, "view_config"),
        (Permission.EDIT_CONFIG, "edit_config"),
        (Permission.EXECUTE_GOVERNANCE, "execute_governance"),
        (Permission.VIEW_APPROVALS, "view_approvals"),
        (Permission.APPROVE_PATCH, "approve_patch"),
        (Permission.REJECT_PATCH, "reject_patch"),
        (Permission.VIEW_ALERTS, "view_alerts"),
        (Permission.ACKNOWLEDGE_ALERT, "acknowledge_alert"),
        (Permission.VIEW_METRICS, "view_metrics"),
        (Permission.VIEW_DASHBOARD, "view_dashboard"),
        (Permission.DEFINE_WORKFLOW, "define_workflow"),
        (Permission.EXECUTE_WORKFLOW, "execute_workflow"),
        (Permission.VIEW_WORKFLOW, "view_workflow"),
        (Permission.MANAGE_WORKFLOW, "manage_workflow"),
    ])
    def test_permission_enum_values(self, permission, expected_value):
        assert permission.value == expected_value

    def test_permission_count(self):
        assert len(list(Permission)) >= 14


class TestPermissionManager:
    """权限管理器测试"""

    @pytest.mark.parametrize("role,permission,expected", [
        (Role.ADMIN, Permission.VIEW_HEALTH, True),
        (Role.ADMIN, Permission.EDIT_CONFIG, True),
        (Role.ADMIN, Permission.APPROVE_PATCH, True),
        (Role.ADMIN, Permission.MANAGE_WORKFLOW, True),
        (Role.TESTER, Permission.VIEW_HEALTH, True),
        (Role.TESTER, Permission.EXECUTE_GOVERNANCE, True),
        (Role.TESTER, Permission.DEFINE_WORKFLOW, True),
        (Role.TESTER, Permission.MANAGE_WORKFLOW, True),
        (Role.TESTER, Permission.EDIT_CONFIG, False),
        (Role.TESTER, Permission.APPROVE_PATCH, False),
        (Role.VIEWER, Permission.VIEW_HEALTH, True),
        (Role.VIEWER, Permission.VIEW_CONFIG, True),
        (Role.VIEWER, Permission.VIEW_ALERTS, True),
        (Role.VIEWER, Permission.EXECUTE_GOVERNANCE, False),
        (Role.VIEWER, Permission.APPROVE_PATCH, False),
        (Role.VIEWER, Permission.MANAGE_WORKFLOW, False),
        (Role.GUEST, Permission.VIEW_HEALTH, True),
        (Role.GUEST, Permission.VIEW_DASHBOARD, True),
        (Role.GUEST, Permission.VIEW_CONFIG, False),
        (Role.GUEST, Permission.EXECUTE_GOVERNANCE, False),
        (Role.GUEST, Permission.MANAGE_WORKFLOW, False),
    ])
    def test_has_permission_parametrized(self, role, permission, expected):
        manager = PermissionManager()
        user = User(id="1", username="test", email="test@testai.com", role=role)
        assert manager.has_permission(user, permission) is expected

    def test_has_permission_admin_all(self):
        manager = PermissionManager()
        admin_user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        for perm in Permission:
            assert manager.has_permission(admin_user, perm) is True

    def test_check_permission_allowed(self):
        manager = PermissionManager()
        admin_user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        
        result = manager.check_permission(admin_user, Permission.EDIT_CONFIG)
        
        assert result.allowed is True
        assert result.required_permission == Permission.EDIT_CONFIG
        assert result.user_role == Role.ADMIN
        assert result.missing_permissions is None

    def test_check_permission_denied(self):
        manager = PermissionManager()
        viewer_user = User(id="3", username="viewer", email="viewer@testai.com", role=Role.VIEWER)
        
        result = manager.check_permission(viewer_user, Permission.EDIT_CONFIG)
        
        assert result.allowed is False
        assert result.required_permission == Permission.EDIT_CONFIG
        assert result.user_role == Role.VIEWER
        assert Permission.EDIT_CONFIG in result.missing_permissions

    def test_check_permission_none_user(self):
        manager = PermissionManager()
        result = manager.check_permission(None, Permission.VIEW_HEALTH)
        assert result.allowed is False

    def test_get_user_permissions(self):
        from src.security.permissions import ROLE_PERMISSIONS
        manager = PermissionManager()
        
        for role in Role:
            user = User(id="1", username="test", email="test@testai.com", role=role)
            permissions = manager.get_user_permissions(user)
            expected_count = len(ROLE_PERMISSIONS.get(role, []))
            assert len(permissions) == expected_count

    @pytest.mark.parametrize("role,expected", [
        (Role.ADMIN, True),
        (Role.TESTER, False),
        (Role.VIEWER, False),
        (Role.GUEST, False),
    ])
    def test_is_admin(self, role, expected):
        manager = PermissionManager()
        user = User(id="1", username="test", email="test@testai.com", role=role)
        assert manager.is_admin(user) is expected

    @pytest.mark.parametrize("role,expected", [
        (Role.ADMIN, True),
        (Role.TESTER, True),
        (Role.VIEWER, False),
        (Role.GUEST, False),
    ])
    def test_is_tester(self, role, expected):
        manager = PermissionManager()
        user = User(id="1", username="test", email="test@testai.com", role=role)
        assert manager.is_tester(user) is expected

    @pytest.mark.parametrize("role,expected", [
        (Role.ADMIN, True),
        (Role.TESTER, True),
        (Role.VIEWER, True),
        (Role.GUEST, False),
    ])
    def test_is_viewer(self, role, expected):
        manager = PermissionManager()
        user = User(id="1", username="test", email="test@testai.com", role=role)
        assert manager.is_viewer(user) is expected

    def test_is_admin_none_user(self):
        manager = PermissionManager()
        assert manager.is_admin(None) is False

    def test_is_tester_none_user(self):
        manager = PermissionManager()
        assert manager.is_tester(None) is False

    def test_is_viewer_none_user(self):
        manager = PermissionManager()
        assert manager.is_viewer(None) is False

    def test_tester_has_workflow_management_permission(self):
        manager = PermissionManager()
        tester_user = User(id="2", username="tester", email="tester@testai.com", role=Role.TESTER)
        
        assert manager.has_permission(tester_user, Permission.MANAGE_WORKFLOW) is True
        assert manager.has_permission(tester_user, Permission.DEFINE_WORKFLOW) is True
        assert manager.has_permission(tester_user, Permission.EXECUTE_WORKFLOW) is True
        assert manager.has_permission(tester_user, Permission.VIEW_WORKFLOW) is True

    def test_has_permission_none_permission(self):
        manager = PermissionManager()
        admin_user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        assert manager.has_permission(admin_user, None) is False

    def test_check_permission_none_permission(self):
        manager = PermissionManager()
        admin_user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        result = manager.check_permission(admin_user, None)
        assert result.allowed is False

    def test_get_user_permissions_none_user(self):
        manager = PermissionManager()
        permissions = manager.get_user_permissions(None)
        assert len(permissions) == 0

    def test_user_with_empty_username(self):
        manager = PermissionManager()
        user = User(id="1", username="", email="test@testai.com", role=Role.VIEWER)
        permissions = manager.get_user_permissions(user)
        assert len(permissions) > 0

    def test_user_with_empty_email(self):
        manager = PermissionManager()
        user = User(id="1", username="test", email="", role=Role.VIEWER)
        result = manager.check_permission(user, Permission.VIEW_HEALTH)
        assert result.allowed is True