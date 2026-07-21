import pytest

from src.security.auth import User, Role
from src.security.permissions import PermissionManager, Permission, PermissionCheckResult


class TestPermission:
    def test_permission_enum_values(self):
        assert Permission.VIEW_HEALTH.value == "view_health"
        assert Permission.VIEW_CONFIG.value == "view_config"
        assert Permission.EDIT_CONFIG.value == "edit_config"
        assert Permission.EXECUTE_GOVERNANCE.value == "execute_governance"
        assert Permission.VIEW_APPROVALS.value == "view_approvals"
        assert Permission.APPROVE_PATCH.value == "approve_patch"
        assert Permission.REJECT_PATCH.value == "reject_patch"
        assert Permission.VIEW_ALERTS.value == "view_alerts"
        assert Permission.ACKNOWLEDGE_ALERT.value == "acknowledge_alert"
        assert Permission.VIEW_METRICS.value == "view_metrics"
        assert Permission.VIEW_DASHBOARD.value == "view_dashboard"
        assert Permission.DEFINE_WORKFLOW.value == "define_workflow"
        assert Permission.EXECUTE_WORKFLOW.value == "execute_workflow"
        assert Permission.VIEW_WORKFLOW.value == "view_workflow"


class TestPermissionManager:
    def test_has_permission_admin(self):
        manager = PermissionManager()
        admin_user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        
        assert manager.has_permission(admin_user, Permission.VIEW_HEALTH) is True
        assert manager.has_permission(admin_user, Permission.EDIT_CONFIG) is True
        assert manager.has_permission(admin_user, Permission.APPROVE_PATCH) is True

    def test_has_permission_tester(self):
        manager = PermissionManager()
        tester_user = User(id="2", username="tester", email="tester@testai.com", role=Role.TESTER)
        
        assert manager.has_permission(tester_user, Permission.VIEW_HEALTH) is True
        assert manager.has_permission(tester_user, Permission.VIEW_CONFIG) is True
        assert manager.has_permission(tester_user, Permission.EXECUTE_GOVERNANCE) is True
        assert manager.has_permission(tester_user, Permission.EDIT_CONFIG) is False
        assert manager.has_permission(tester_user, Permission.APPROVE_PATCH) is False

    def test_has_permission_viewer(self):
        manager = PermissionManager()
        viewer_user = User(id="3", username="viewer", email="viewer@testai.com", role=Role.VIEWER)
        
        assert manager.has_permission(viewer_user, Permission.VIEW_HEALTH) is True
        assert manager.has_permission(viewer_user, Permission.VIEW_CONFIG) is True
        assert manager.has_permission(viewer_user, Permission.VIEW_ALERTS) is True
        assert manager.has_permission(viewer_user, Permission.EXECUTE_GOVERNANCE) is False
        assert manager.has_permission(viewer_user, Permission.APPROVE_PATCH) is False

    def test_has_permission_guest(self):
        manager = PermissionManager()
        guest_user = User(id="4", username="guest", email="guest@testai.com", role=Role.GUEST)
        
        assert manager.has_permission(guest_user, Permission.VIEW_HEALTH) is True
        assert manager.has_permission(guest_user, Permission.VIEW_DASHBOARD) is True
        assert manager.has_permission(guest_user, Permission.VIEW_CONFIG) is False
        assert manager.has_permission(guest_user, Permission.EXECUTE_GOVERNANCE) is False

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

    def test_get_user_permissions_admin(self):
        manager = PermissionManager()
        admin_user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        
        permissions = manager.get_user_permissions(admin_user)
        
        assert len(permissions) == 19

    def test_get_user_permissions_tester(self):
        manager = PermissionManager()
        tester_user = User(id="2", username="tester", email="tester@testai.com", role=Role.TESTER)
        
        permissions = manager.get_user_permissions(tester_user)
        
        assert len(permissions) == 13

    def test_get_user_permissions_viewer(self):
        manager = PermissionManager()
        viewer_user = User(id="3", username="viewer", email="viewer@testai.com", role=Role.VIEWER)
        
        permissions = manager.get_user_permissions(viewer_user)
        
        assert len(permissions) == 10

    def test_get_user_permissions_guest(self):
        manager = PermissionManager()
        guest_user = User(id="4", username="guest", email="guest@testai.com", role=Role.GUEST)
        
        permissions = manager.get_user_permissions(guest_user)
        
        assert len(permissions) == 2

    def test_is_admin(self):
        manager = PermissionManager()
        
        admin_user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        tester_user = User(id="2", username="tester", email="tester@testai.com", role=Role.TESTER)
        
        assert manager.is_admin(admin_user) is True
        assert manager.is_admin(tester_user) is False

    def test_is_tester(self):
        manager = PermissionManager()
        
        admin_user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        tester_user = User(id="2", username="tester", email="tester@testai.com", role=Role.TESTER)
        viewer_user = User(id="3", username="viewer", email="viewer@testai.com", role=Role.VIEWER)
        
        assert manager.is_tester(admin_user) is True
        assert manager.is_tester(tester_user) is True
        assert manager.is_tester(viewer_user) is False

    def test_is_viewer(self):
        manager = PermissionManager()
        
        admin_user = User(id="1", username="admin", email="admin@testai.com", role=Role.ADMIN)
        tester_user = User(id="2", username="tester", email="tester@testai.com", role=Role.TESTER)
        viewer_user = User(id="3", username="viewer", email="viewer@testai.com", role=Role.VIEWER)
        guest_user = User(id="4", username="guest", email="guest@testai.com", role=Role.GUEST)
        
        assert manager.is_viewer(admin_user) is True
        assert manager.is_viewer(tester_user) is True
        assert manager.is_viewer(viewer_user) is True
        assert manager.is_viewer(guest_user) is False