import uuid
from typing import Optional, Dict

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from src.governance.orchestrator import GovernanceOrchestrator
from src.governance.approval import ApprovalManager, ApprovalStatus
from src.governance.monitoring import HealthMonitor, AlertManager
from src.governance.transformer import FunctionTransformer, ContextAwareTransformer
from src.governance.executor import GovernanceExecutor
from src.governance.tracker import GovernanceTracker, GovernanceActionType
from src.governance.baseline import GoldenBaselineManager
from src.platform.workflow import WorkflowEngine, WorkflowDefinition
from src.platform.config_manager import ConfigManager
from src.platform.dashboard import DashboardService
from src.governance.models import DiagnosticContext, PatchProposal, PatchType
from src.security.auth import TokenManager, User, Role
from src.security.permissions import PermissionManager, Permission
from src.users.user_manager import UserManager, UserProfile, UserStatus
from src.teams.team_manager import TeamManager, Team, TeamMember, TeamRole


app = FastAPI(
    title="TestAI Platform API",
    version="1.0.0",
    description="AI 驱动的测试工具平台 - 统一 API 网关",
    docs_url="/docs",
    redoc_url="/redoc",
)

security = HTTPBearer()

orchestrator = GovernanceOrchestrator()
approval_manager = ApprovalManager()
health_monitor = HealthMonitor()
alert_manager = AlertManager()
executor = GovernanceExecutor()
workflow_engine = WorkflowEngine()
config_manager = ConfigManager()
dashboard_service = DashboardService()
token_manager = TokenManager()
permission_manager = PermissionManager()
user_manager = UserManager()
team_manager = TeamManager()
tracker = GovernanceTracker()
baseline_manager = GoldenBaselineManager()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Dict


class CreateUserRequest(BaseModel):
    username: str
    email: str
    role: str = "tester"
    full_name: str = ""
    department: str = ""


class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    full_name: Optional[str] = None
    department: Optional[str] = None


class CreateTeamRequest(BaseModel):
    name: str
    description: str = ""


class AddTeamMemberRequest(BaseModel):
    user_id: str
    username: str
    role: str = "member"


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    token = credentials.credentials
    user = token_manager.verify_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        )
    return user


def require_permission(permission: Permission):
    def dependency(user: User = Depends(get_current_user)):
        if not permission_manager.has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission.value}",
            )
        return user
    return dependency


@app.post("/auth/login")
async def login(request: LoginRequest):
    user = token_manager.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    access_token = token_manager.create_access_token(user)
    refresh_token = token_manager.create_refresh_token(user)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
        },
    )


@app.post("/auth/refresh")
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    refresh_token = credentials.credentials
    new_access_token = token_manager.refresh_token(refresh_token)
    if not new_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    return {"access_token": new_access_token, "token_type": "bearer"}


@app.get("/auth/me")
async def get_current_user_info(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "permissions": [p.value for p in permission_manager.get_user_permissions(user)],
    }


@app.get("/health")
async def health_check():
    status = health_monitor.get_health_status()
    return {
        "status": "healthy",
        "platform": "TestAI",
        "version": "1.0.0",
        "governance_status": status,
    }


@app.post("/governance/execute")
async def execute_governance(
    component_name: str,
    step_id: str = None,
    input_data: dict = None,
    actual_output: str = "",
    expected_baseline: str = "",
    user: User = Depends(require_permission(Permission.EXECUTE_GOVERNANCE)),
):
    trace_id = step_id or str(uuid.uuid4())[:8]
    context = DiagnosticContext(
        component_name=component_name,
        step_id=trace_id,
        input_data=input_data or {},
        actual_output=actual_output,
        expected_baseline=expected_baseline,
    )
    result = await orchestrator.execute_governance_flow(context)
    return {"trace_id": trace_id, **result}


@app.get("/governance/approvals")
async def list_approvals(
    status: Optional[str] = None,
    user: User = Depends(require_permission(Permission.VIEW_APPROVALS)),
):
    pending = approval_manager.list_pending()
    if status:
        status_enum = ApprovalStatus[status.upper()]
        pending = [p for p in pending if p.status == status_enum]
    return {"count": len(pending), "approvals": [p.to_dict() for p in pending]}


@app.post("/governance/approvals/{tx_id}/approve")
async def approve_patch(
    tx_id: str,
    approver: str,
    reason: str = None,
    user: User = Depends(require_permission(Permission.APPROVE_PATCH)),
):
    result = await orchestrator.approve_and_apply(tx_id, approver, reason)
    return {"tx_id": tx_id, **result}


@app.post("/governance/approvals/{tx_id}/reject")
async def reject_patch(
    tx_id: str,
    approver: str,
    reason: str,
    user: User = Depends(require_permission(Permission.REJECT_PATCH)),
):
    result = approval_manager.reject(tx_id, approver, reason)
    return {"tx_id": tx_id, "approved": result}


@app.get("/monitoring/alerts")
async def get_alerts(
    level: Optional[str] = None,
    user: User = Depends(require_permission(Permission.VIEW_ALERTS)),
):
    if level:
        alerts = alert_manager.get_alerts_by_level(level.upper())
    else:
        alerts = alert_manager.get_alerts()
    return {"count": len(alerts), "alerts": [a.to_dict() for a in alerts]}


@app.post("/monitoring/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    user: User = Depends(require_permission(Permission.ACKNOWLEDGE_ALERT)),
):
    result = alert_manager.acknowledge_alert(alert_id)
    return {"alert_id": alert_id, "acknowledged": result}


@app.get("/monitoring/metrics")
async def get_metrics(user: User = Depends(require_permission(Permission.VIEW_METRICS))):
    status = health_monitor.get_health_status()
    metrics = health_monitor.get_metrics()
    return {"status": status, "metrics": metrics}


@app.post("/workflow/define")
async def define_workflow(
    workflow_def: WorkflowDefinition,
    user: User = Depends(require_permission(Permission.DEFINE_WORKFLOW)),
):
    workflow_id = workflow_engine.define_workflow(workflow_def)
    return {"workflow_id": workflow_id, "status": "defined"}


@app.post("/workflow/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    params: dict = None,
    user: User = Depends(require_permission(Permission.EXECUTE_WORKFLOW)),
):
    result = await workflow_engine.execute_workflow(workflow_id, params or {})
    return {"workflow_id": workflow_id, **result}


@app.get("/workflow/{workflow_id}/status")
async def get_workflow_status(
    workflow_id: str,
    user: User = Depends(require_permission(Permission.VIEW_WORKFLOW)),
):
    status = workflow_engine.get_workflow_status(workflow_id)
    if not status:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return status


@app.get("/config")
async def get_config(
    section: Optional[str] = None,
    user: User = Depends(require_permission(Permission.VIEW_CONFIG)),
):
    if section:
        return config_manager.get_section(section)
    return config_manager.get_all()


@app.put("/config/{section}")
async def update_config(
    section: str,
    config: dict,
    user: User = Depends(require_permission(Permission.EDIT_CONFIG)),
):
    config_manager.update_section(section, config)
    return {"section": section, "status": "updated"}


@app.get("/dashboard/summary")
async def get_dashboard_summary(user: User = Depends(require_permission(Permission.VIEW_DASHBOARD))):
    return dashboard_service.get_summary()


@app.get("/dashboard/quality-trend")
async def get_quality_trend(
    days: int = 7,
    user: User = Depends(require_permission(Permission.VIEW_DASHBOARD)),
):
    return dashboard_service.get_quality_trend(days)


@app.get("/users")
async def list_users(
    role: Optional[str] = None,
    status: Optional[str] = None,
    department: Optional[str] = None,
    user: User = Depends(require_permission(Permission.VIEW_USERS)),
):
    role_enum = Role[role.upper()] if role else None
    status_enum = UserStatus[status.upper()] if status else None
    users = user_manager.list_users(role=role_enum, status=status_enum, department=department)
    return {"count": len(users), "users": [
        {
            "user_id": u.user_id,
            "username": u.username,
            "email": u.email,
            "role": u.role.value,
            "status": u.status.value,
            "full_name": u.full_name,
            "department": u.department,
            "created_at": u.created_at.isoformat(),
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        }
        for u in users
    ]}


@app.post("/users")
async def create_user(
    request: CreateUserRequest,
    user: User = Depends(require_permission(Permission.MANAGE_USERS)),
):
    try:
        role_enum = Role[request.role.upper()]
        new_user = user_manager.create_user(
            username=request.username,
            email=request.email,
            role=role_enum,
            full_name=request.full_name,
            department=request.department,
        )
        return {"user_id": new_user.user_id, "username": new_user.username, "email": new_user.email}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/users/{user_id}")
async def get_user(
    user_id: str,
    user: User = Depends(require_permission(Permission.VIEW_USERS)),
):
    u = user_manager.get_user(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": u.user_id,
        "username": u.username,
        "email": u.email,
        "role": u.role.value,
        "status": u.status.value,
        "full_name": u.full_name,
        "department": u.department,
        "created_at": u.created_at.isoformat(),
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
    }


@app.put("/users/{user_id}")
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    user: User = Depends(require_permission(Permission.MANAGE_USERS)),
):
    try:
        role_enum = Role[request.role.upper()] if request.role else None
        status_enum = UserStatus[request.status.upper()] if request.status else None
        updated = user_manager.update_user(
            user_id=user_id,
            username=request.username,
            email=request.email,
            role=role_enum,
            status=status_enum,
            full_name=request.full_name,
            department=request.department,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="User not found")
        return {"user_id": updated.user_id, "status": "updated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_USERS)),
):
    success = user_manager.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "deleted": True}


@app.post("/users/{user_id}/activate")
async def activate_user(
    user_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_USERS)),
):
    updated = user_manager.activate_user(user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "status": "activated"}


@app.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_USERS)),
):
    updated = user_manager.suspend_user(user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, "status": "suspended"}


@app.get("/users/stats")
async def get_user_stats(user: User = Depends(require_permission(Permission.VIEW_USERS))):
    return user_manager.count_users()


@app.get("/teams")
async def list_teams(user: User = Depends(require_permission(Permission.VIEW_TEAMS))):
    teams = team_manager.list_teams()
    return {"count": len(teams), "teams": [
        {
            "team_id": t.team_id,
            "name": t.name,
            "description": t.description,
            "member_count": len(t.members),
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
        }
        for t in teams
    ]}


@app.post("/teams")
async def create_team(
    request: CreateTeamRequest,
    user: User = Depends(require_permission(Permission.MANAGE_TEAMS)),
):
    try:
        team = team_manager.create_team(name=request.name, description=request.description)
        return {"team_id": team.team_id, "name": team.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/teams/{team_id}")
async def get_team(
    team_id: str,
    user: User = Depends(require_permission(Permission.VIEW_TEAMS)),
):
    team = team_manager.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {
        "team_id": team.team_id,
        "name": team.name,
        "description": team.description,
        "members": [
            {
                "user_id": m.user_id,
                "username": m.username,
                "role": m.role.value,
                "joined_at": m.joined_at.isoformat(),
            }
            for m in team.members
        ],
        "created_at": team.created_at.isoformat(),
        "updated_at": team.updated_at.isoformat(),
    }


@app.put("/teams/{team_id}")
async def update_team(
    team_id: str,
    request: CreateTeamRequest,
    user: User = Depends(require_permission(Permission.MANAGE_TEAMS)),
):
    try:
        updated = team_manager.update_team(
            team_id=team_id,
            name=request.name,
            description=request.description,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Team not found")
        return {"team_id": team_id, "status": "updated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/teams/{team_id}")
async def delete_team(
    team_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_TEAMS)),
):
    success = team_manager.delete_team(team_id)
    if not success:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"team_id": team_id, "deleted": True}


@app.post("/teams/{team_id}/members")
async def add_team_member(
    team_id: str,
    request: AddTeamMemberRequest,
    user: User = Depends(require_permission(Permission.MANAGE_TEAMS)),
):
    try:
        role_enum = TeamRole(request.role.lower())
        team = team_manager.add_member(
            team_id=team_id,
            user_id=request.user_id,
            username=request.username,
            role=role_enum,
        )
        if not team:
            raise HTTPException(status_code=404, detail="Team not found")
        return {"team_id": team_id, "member_added": request.username}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/teams/{team_id}/members/{user_id}")
async def remove_team_member(
    team_id: str,
    user_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_TEAMS)),
):
    try:
        team = team_manager.remove_member(team_id=team_id, user_id=user_id)
        if not team:
            raise HTTPException(status_code=404, detail="Team or member not found")
        return {"team_id": team_id, "member_removed": user_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/teams/{team_id}/members")
async def get_team_members(
    team_id: str,
    user: User = Depends(require_permission(Permission.VIEW_TEAMS)),
):
    members = team_manager.get_team_members(team_id)
    return {"count": len(members), "members": [
        {
            "user_id": m.user_id,
            "username": m.username,
            "role": m.role.value,
            "joined_at": m.joined_at.isoformat(),
        }
        for m in members
    ]}


@app.get("/teams/stats")
async def get_team_stats(user: User = Depends(require_permission(Permission.VIEW_TEAMS))):
    return team_manager.count_teams()


@app.get("/governance/tracker/events")
async def get_tracker_events(
    trace_id: Optional[str] = None,
    event_type: Optional[str] = None,
    component: Optional[str] = None,
    limit: int = 100,
    user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE)),
):
    events = tracker.get_events_by_trace(trace_id) if trace_id else tracker._events
    
    if event_type:
        event_type_enum = GovernanceActionType[event_type.upper()]
        events = [e for e in events if e.action_type == event_type_enum]
    
    if component:
        events = [e for e in events if e.component == component]
    
    events = events[:limit]
    
    return {
        "count": len(events),
        "events": [
            {
                "trace_id": e.trace_id,
                "event_type": e.action_type.value,
                "component": e.component,
                "timestamp": e.timestamp.isoformat(),
                "details": e.metadata,
            }
            for e in events
        ],
    }


@app.get("/governance/tracker/summary")
async def get_tracker_summary(user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE))):
    summary = tracker.get_summary()
    return {
        "total_events": summary.get("total_events", 0),
        "completed_diagnoses": summary.get("by_action", {}).get("diagnose_complete", 0),
        "successful_patches": summary.get("by_action", {}).get("patch_applied", 0),
        "failed_patches": summary.get("failed_count", 0),
        "pending_approvals": summary.get("by_action", {}).get("approval_required", 0),
        "converged_count": summary.get("converged_count", 0),
        "diverged_count": summary.get("diverged_count", 0),
    }


@app.get("/governance/baselines")
async def get_baselines(user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE))):
    baselines = baseline_manager.get_all_baselines()
    return {
        "count": len(baselines),
        "baselines": [
            {
                "baseline_id": b["baseline_id"],
                "name": b["name"],
                "description": b["description"],
            }
            for b in baselines
        ],
    }


@app.get("/governance/baselines/{baseline_id}")
async def get_baseline(
    baseline_id: str,
    user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE)),
):
    baseline = baseline_manager.get_baseline(baseline_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return baseline


@app.post("/governance/baselines/{baseline_id}/validate")
async def validate_baseline(
    baseline_id: str,
    actual_data: dict,
    user: User = Depends(require_permission(Permission.EXECUTE_GOVERNANCE)),
):
    result = baseline_manager.validate_against_baseline(baseline_id, actual_data)
    return {
        "baseline_id": baseline_id,
        "passed": result["passed"],
        "convergence_score": result["convergence_score"],
        "mismatches": result.get("mismatches", []),
    }


@app.get("/governance/baselines/{baseline_id}/convergence")
async def get_baseline_convergence(
    baseline_id: str,
    user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE)),
):
    baseline = baseline_manager.get_baseline(baseline_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    
    return {
        "baseline_id": baseline_id,
        "expected_output": baseline["expected_output"],
        "tolerance": baseline["tolerance"],
    }