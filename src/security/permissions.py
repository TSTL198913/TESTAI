from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
from .auth import Role, User


class Permission(str, Enum):
    VIEW_HEALTH = "view_health"
    VIEW_CONFIG = "view_config"
    EDIT_CONFIG = "edit_config"
    EXECUTE_GOVERNANCE = "execute_governance"
    VIEW_GOVERNANCE = "view_governance"
    VIEW_APPROVALS = "view_approvals"
    APPROVE_PATCH = "approve_patch"
    REJECT_PATCH = "reject_patch"
    VIEW_ALERTS = "view_alerts"
    ACKNOWLEDGE_ALERT = "acknowledge_alert"
    VIEW_METRICS = "view_metrics"
    VIEW_DASHBOARD = "view_dashboard"
    DEFINE_WORKFLOW = "define_workflow"
    EXECUTE_WORKFLOW = "execute_workflow"
    VIEW_WORKFLOW = "view_workflow"
    MANAGE_USERS = "manage_users"
    VIEW_USERS = "view_users"
    MANAGE_TEAMS = "manage_teams"
    VIEW_TEAMS = "view_teams"


ROLE_PERMISSIONS: Dict[Role, List[Permission]] = {
    Role.ADMIN: [
        Permission.VIEW_HEALTH,
        Permission.VIEW_CONFIG,
        Permission.EDIT_CONFIG,
        Permission.EXECUTE_GOVERNANCE,
        Permission.VIEW_GOVERNANCE,
        Permission.VIEW_APPROVALS,
        Permission.APPROVE_PATCH,
        Permission.REJECT_PATCH,
        Permission.VIEW_ALERTS,
        Permission.ACKNOWLEDGE_ALERT,
        Permission.VIEW_METRICS,
        Permission.VIEW_DASHBOARD,
        Permission.DEFINE_WORKFLOW,
        Permission.EXECUTE_WORKFLOW,
        Permission.VIEW_WORKFLOW,
        Permission.MANAGE_USERS,
        Permission.VIEW_USERS,
        Permission.MANAGE_TEAMS,
        Permission.VIEW_TEAMS,
    ],
    Role.TESTER: [
        Permission.VIEW_HEALTH,
        Permission.VIEW_CONFIG,
        Permission.EXECUTE_GOVERNANCE,
        Permission.VIEW_GOVERNANCE,
        Permission.VIEW_APPROVALS,
        Permission.VIEW_ALERTS,
        Permission.VIEW_METRICS,
        Permission.VIEW_DASHBOARD,
        Permission.DEFINE_WORKFLOW,
        Permission.EXECUTE_WORKFLOW,
        Permission.VIEW_WORKFLOW,
        Permission.VIEW_USERS,
        Permission.VIEW_TEAMS,
    ],
    Role.VIEWER: [
        Permission.VIEW_HEALTH,
        Permission.VIEW_CONFIG,
        Permission.VIEW_GOVERNANCE,
        Permission.VIEW_APPROVALS,
        Permission.VIEW_ALERTS,
        Permission.VIEW_METRICS,
        Permission.VIEW_DASHBOARD,
        Permission.VIEW_WORKFLOW,
        Permission.VIEW_USERS,
        Permission.VIEW_TEAMS,
    ],
    Role.GUEST: [
        Permission.VIEW_HEALTH,
        Permission.VIEW_DASHBOARD,
    ],
}


@dataclass
class PermissionCheckResult:
    allowed: bool
    required_permission: Permission
    user_role: Role
    missing_permissions: Optional[List[Permission]] = None


class PermissionManager:
    def __init__(self):
        self.role_permissions = ROLE_PERMISSIONS

    def has_permission(self, user: User, permission: Permission) -> bool:
        if user.role not in self.role_permissions:
            return False
        return permission in self.role_permissions[user.role]

    def check_permission(self, user: User, permission: Permission) -> PermissionCheckResult:
        if user.role not in self.role_permissions:
            return PermissionCheckResult(
                allowed=False,
                required_permission=permission,
                user_role=user.role,
                missing_permissions=[permission],
            )
        
        if permission in self.role_permissions[user.role]:
            return PermissionCheckResult(
                allowed=True,
                required_permission=permission,
                user_role=user.role,
            )
        
        return PermissionCheckResult(
            allowed=False,
            required_permission=permission,
            user_role=user.role,
            missing_permissions=[permission],
        )

    def get_user_permissions(self, user: User) -> List[Permission]:
        return self.role_permissions.get(user.role, [])

    def is_admin(self, user: User) -> bool:
        return user.role == Role.ADMIN

    def is_tester(self, user: User) -> bool:
        return user.role == Role.TESTER or user.role == Role.ADMIN

    def is_viewer(self, user: User) -> bool:
        return user.role in [Role.VIEWER, Role.TESTER, Role.ADMIN]