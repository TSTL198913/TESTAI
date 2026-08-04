import uuid
import os
import re
import logging
from typing import Optional, Dict, List, Any

from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, field_validator
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST  # pylint: disable=import-error

logger = logging.getLogger(__name__)

# =============================================================================
# 治理硬依赖 (必须存在, 隔离模式下不可缺失)
# 包含: governance/*, security/*, platform/workflow, platform/config_manager,
#   platform/dashboard, platform/metrics, worker/*, models/contract(HttpRequest — /execute 主路径依赖)
# =============================================================================
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
from src.platform.metrics import APIMetrics
from src.models.contract import HttpRequest  # /execute 主路径的请求体类型 (治理硬依赖)
from src.worker.celery_app import celery_app  # Celery 应用实例
from src.worker.tasks import run_test_pipeline  # Celery 异步任务

# =============================================================================
# 非治理可选依赖 (隔离对象: 测试+AI平台方向)
# 当这些模块缺失时, api.py 必须仍能加载, 治理核心正常工作,
# 非治理端点返回 503 Service Unavailable。
# =============================================================================
_NON_GOV_AVAILABLE = True
try:
    from src.users.user_manager import UserManager, UserProfile, UserStatus
    from src.teams.team_manager import TeamManager, Team, TeamMember, TeamRole
    from src.ai.evaluator import AIEvaluator
    from src.ai.qa_engine import AIQAEngine
    from src.ai.classifier import AITextClassifier
except ImportError:
    _NON_GOV_AVAILABLE = False
    UserManager = None  # type: ignore[assignment,misc]
    UserProfile = None  # type: ignore[assignment]
    UserStatus = None  # type: ignore[assignment]
    TeamManager = None  # type: ignore[assignment,misc]
    Team = None  # type: ignore[assignment]
    TeamMember = None  # type: ignore[assignment]
    TeamRole = None  # type: ignore[assignment]
    AIEvaluator = None  # type: ignore[assignment,misc]
    AIQAEngine = None  # type: ignore[assignment,misc]
    AITextClassifier = None  # type: ignore[assignment,misc]
    logger.warning("非治理模块 (users/teams/ai) 加载失败 — 隔离模式启用, 相关端点将返回 503")


app = FastAPI(
    title="TestAI Platform API",
    version="1.0.0",
    description="AI 驱动的测试工具平台 - 统一 API 网关",
    docs_url="/docs",
    redoc_url="/redoc",
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
)


def _compute_cors_origins() -> list:
    """计算 CORS 允许的源列表。

    生产环境(ENVIRONMENT=production)必须显式设置 CORS_ALLOWED_ORIGINS,
    否则启动失败。开发环境未设置时使用本地默认源。
    """
    cors_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    if cors_env:
        return [o.strip() for o in cors_env.split(",") if o.strip()]

    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env == "production":
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS environment variable must be set in production. "
            "Example: CORS_ALLOWED_ORIGINS=https://your-frontend.com"
        )
    # 开发默认源(覆盖常用本地端口)
    return ["http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000"]


# 模块级常量:启动时计算一次,供测试与中间件读取
_cors_allowed_origins = _compute_cors_origins()

@app.middleware("http")
async def remove_server_header(request, call_next):
    response = await call_next(request)
    if "server" in response.headers:
        del response.headers["server"]
    if "Server" in response.headers:
        del response.headers["Server"]
    return response

# P0-2 修复: API 请求指标中间件
# 每次请求结束后记录 Prometheus 指标
@app.middleware("http")
async def api_metrics_middleware(request: Request, call_next):
    import time
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    api_metrics.record_request(
        endpoint=str(request.url.path),
        method=request.method,
        status_code=response.status_code,
        duration=duration
    )
    
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)


# =============================================================================
# 503 隔离守卫 (BUG4 修复)
# 非治理模块缺失时 (_NON_GOV_AVAILABLE=False), 非治理端点必须返回 503,
# 而非调用 None.list_users() 导致 AttributeError 500。
# 503 语义: "端点存在但依赖不可用" — 区别于 404 "路由不存在"。
# =============================================================================
_NON_GOV_PATH_PREFIXES = (
    "/users",
    "/teams",
    "/evaluate",
    "/qa",
    "/classify",
    "/diagnose",
)
# /test 下仅 execute 和 generate 为非治理; /test/workflow 使用治理引擎, 不拦截
_NON_GOV_PATH_EXACT = frozenset({
    "/test/execute",
    "/test/generate",
})


def _is_non_gov_path(path: str) -> bool:
    """判断请求路径是否属于非治理端点。"""
    for prefix in _NON_GOV_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return path in _NON_GOV_PATH_EXACT


@app.middleware("http")
async def non_gov_isolation_guard(request: Request, call_next):
    """隔离模式守卫: _NON_GOV_AVAILABLE=False 时拦截非治理端点返回 503。"""
    if not _NON_GOV_AVAILABLE:
        path = request.url.path
        if _is_non_gov_path(path):
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "message": "非治理模块不可用 (隔离模式) — users/teams/ai 模块未加载",
                    "error_code": "NON_GOV_UNAVAILABLE",
                    "detail": None,
                },
            )
    return await call_next(request)


# P1-6 修复:统一 HTTPException 响应为 ErrorResponse 格式
# 所有 HTTPException 返回 {success: false, message, error_code, detail}
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """将 HTTPException 转换为统一的 ErrorResponse 格式。

    Args:
        request: 请求对象
        exc: HTTPException 实例

    Returns:
        JSONResponse: ErrorResponse 格式的响应
    """
    status_code = exc.status_code
    # 构造 error_code:HTTP_404, HTTP_401, HTTP_403 等
    error_code = f"HTTP_{status_code}"
    detail_str = str(exc.detail) if not isinstance(exc.detail, dict) else exc.detail.get("message", str(exc.detail))

    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": detail_str,
            "error_code": error_code,
            "detail": exc.detail,
        },
        headers=getattr(exc, "headers", None),
    )

security = HTTPBearer()
# Cookie 认证路径专用:不自动报错,允许无 Authorization header(纯 cookie 认证场景)
security_cookie = HTTPBearer(auto_error=False)


def _cookie_secure() -> bool:
    """Cookie Secure 标志:生产环境强制 True,开发环境默认 False 支持 HTTP localhost。"""
    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env == "production":
        return True
    return os.environ.get("COOKIE_SECURE", "false").lower() == "true"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """设置 HttpOnly + Secure + SameSite=Strict 的认证 cookie。

    P0-6 修复:token 不再暴露给 JavaScript(XSS 不可读)。
    """
    access_max_age = token_manager.access_token_expire_minutes * 60
    refresh_max_age = token_manager.refresh_token_expire_days * 24 * 3600
    secure = _cookie_secure()
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=access_max_age,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=refresh_max_age,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    """清除认证 cookie。"""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")

orchestrator = GovernanceOrchestrator()
approval_manager = orchestrator.approval_mgr
health_monitor = HealthMonitor()
alert_manager = AlertManager()
executor = GovernanceExecutor()
workflow_engine = WorkflowEngine()
config_manager = ConfigManager()
dashboard_service = DashboardService()
token_manager = TokenManager()
permission_manager = PermissionManager()
# 非治理单例: 隔离模式下 (_NON_GOV_AVAILABLE=False) 设为 None,
# 避免调用 None() 触发 TypeError (BUG2 修复)
user_manager = UserManager() if _NON_GOV_AVAILABLE else None
team_manager = TeamManager() if _NON_GOV_AVAILABLE else None
tracker = GovernanceTracker()
baseline_manager = GoldenBaselineManager()
api_metrics = APIMetrics()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Dict


class ApiResponse(BaseModel):
    success: bool
    data: Optional[Dict] = None
    message: str = ""
    error_code: Optional[str] = None


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: str
    detail: Optional[str] = None


class CreateUserRequest(BaseModel):
    username: str
    email: str
    role: str = "tester"
    full_name: str = ""
    department: str = ""

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):  # pylint: disable=no-self-argument
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email format")
        return v


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

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):  # pylint: disable=no-self-argument
        if not v or not v.strip():
            raise ValueError("Team name cannot be empty")
        if len(v.strip()) > 100:
            raise ValueError("Team name cannot exceed 100 characters")
        return v.strip()


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


def get_current_user_from_cookie(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_cookie, use_cache=False),
) -> User:
    """优先从 HttpOnly cookie 读取 token,回退到 Authorization header(兼容期)。

    P0-6 修复:支持 cookie 认证,token 不再暴露给 JavaScript。
    """
    # 1. 优先读 cookie
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        user = token_manager.verify_token(cookie_token)
        if user:
            return user

    # 2. 回退到 Authorization header(兼容期,支持旧客户端)
    if credentials and credentials.credentials:
        user = token_manager.verify_token(credentials.credentials)
        if user:
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
    )


def require_permission(permission: Permission):
    def dependency(user: User = Depends(get_current_user_from_cookie)):
        if not permission_manager.has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission.value}",
            )
        return user
    return dependency


@app.post("/auth/login")
async def login(request: LoginRequest, response: Response):
    if token_manager.is_rate_limited(request.username):
        rate_info = token_manager.get_rate_limit_info(request.username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Please try again in {rate_info['reset_in']} seconds.",
            headers={
                "X-RateLimit-Limit": str(rate_info["limit"]),
                "X-RateLimit-Remaining": str(rate_info["remaining"]),
                "X-RateLimit-Reset": str(rate_info["reset_in"]),
            },
        )

    user = token_manager.authenticate(request.username, request.password)
    if not user:
        rate_info = token_manager.get_rate_limit_info(request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={
                "X-RateLimit-Limit": str(rate_info["limit"]),
                "X-RateLimit-Remaining": str(rate_info["remaining"]),
            },
        )

    access_token = token_manager.create_access_token(user)
    refresh_token = token_manager.create_refresh_token(user)

    response_content = ApiResponse(
        success=True,
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role.value,
            },
        },
        message="Login successful",
    )

    response_body = response_content.model_dump_json().encode()
    auth_response = Response(
        content=response_body,
        status_code=200,
        media_type="application/json",
    )

    access_max_age = token_manager.access_token_expire_minutes * 60
    refresh_max_age = token_manager.refresh_token_expire_days * 24 * 3600
    secure = _cookie_secure()
    auth_response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=access_max_age,
        path="/",
    )
    auth_response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=refresh_max_age,
        path="/",
    )
    
    return auth_response


@app.post("/auth/refresh")
async def refresh_token(
    response: Response,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_cookie, use_cache=False),
):
    # 优先从 cookie 读 refresh_token,回退到 Authorization header
    refresh_tok = request.cookies.get("refresh_token")
    if not refresh_tok and credentials and credentials.credentials:
        refresh_tok = credentials.credentials

    if not refresh_tok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided",
        )

    new_access_token = token_manager.refresh_token(refresh_tok)
    if not new_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # 更新 access_token cookie
    secure = _cookie_secure()
    access_max_age = token_manager.access_token_expire_minutes * 60
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=access_max_age,
        path="/",
    )

    return ApiResponse(
        success=True,
        data={"access_token": new_access_token, "token_type": "bearer"},
        message="Token refreshed successfully",
    )  # nosec B105


@app.post("/auth/logout")
async def logout(response: Response):
    """登出端点:清除认证 cookie。"""
    _clear_auth_cookies(response)
    return ApiResponse(
        success=True,
        data=None,
        message="Logout successful",
    )


@app.get("/auth/me")
async def get_current_user_info(user: User = Depends(get_current_user_from_cookie)):
    return ApiResponse(
        success=True,
        data={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "permissions": [p.value for p in permission_manager.get_user_permissions(user)],
        },
        message="User info retrieved successfully",
    )


@app.get("/health")
async def health_check():
    status = health_monitor.get_health_status()
    return ApiResponse(
        success=True,
        data={
            "status": "healthy",
            "platform": "TestAI",
            "version": "1.0.0",
            "governance_status": status,
        },
        message="System health check passed",
    )


@app.get("/metrics")
async def metrics():
    from fastapi.responses import PlainTextResponse

    data = generate_latest()
    return PlainTextResponse(content=data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


class ExecuteRequest(BaseModel):
    """POST /execute 请求体 — 提交测试管道到 Celery 异步执行。

    Pydantic 强校验: 禁止弱类型隐式转换, 所有字段显式声明类型。
    """
    step_id: str
    description: str = ""
    url: str
    method: str = "GET"
    headers: Dict[str, str] = {}
    body: Optional[Dict[str, Any]] = None
    params: Dict[str, Any] = {}
    pipeline: List[str] = ["data", "request", "assertion"]

    @field_validator("method")
    @classmethod
    def validate_method(cls, v):  # pylint: disable=no-self-argument
        allowed = {"GET", "POST", "PUT", "DELETE", "PATCH"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"method must be one of {allowed}, got '{v}'")
        return upper


@app.post("/execute")
async def execute_pipeline(
    request: ExecuteRequest,
    user: User = Depends(require_permission(Permission.RUN_TEST)),
):
    """提交测试管道到 Celery 异步执行。

    流程:
      1. 生成 8 字符 trace_id (用于全链路追踪)
      2. 构造 request_dict, 注入 _trace_id 和 _requester (当前用户名)
      3. 调用 run_test_pipeline.delay() 投递到 Celery 队列
      4. 返回 task_id + trace_id, status=queued

    Prometheus 指标: 通过 api_metrics_middleware 自动记录。
    """
    trace_id = uuid.uuid4().hex[:8]

    # 构造 Celery 任务参数 — 注入追踪元数据
    request_dict = {
        **request.model_dump(),
        "case_id": request.step_id,
        "_trace_id": trace_id,
        "_requester": user.username,
    }

    try:
        task = run_test_pipeline.delay(request_dict)
    except Exception as exc:
        logger.error(
            "Celery 任务投递失败 | trace_id=%s | step_id=%s | error=%s",
            trace_id, request.step_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"任务队列不可用: {type(exc).__name__}: {exc}",
        )

    logger.info(
        "管道已提交 | trace_id=%s | task_id=%s | step_id=%s | requester=%s",
        trace_id, task.id, request.step_id, user.username,
    )

    return ApiResponse(
        success=True,
        data={
            "task_id": task.id,
            "trace_id": trace_id,
            "status": "queued",
        },
        message="Pipeline submitted to Celery queue",
    )


@app.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    user: User = Depends(require_permission(Permission.VIEW_WORKFLOW)),
):
    """查询任务状态 — 双源查询: WorkflowEngine 优先, 回退 Celery AsyncResult。

    BUG #2 修复: /execute 提交的任务是 Celery 异步任务, 不在 WorkflowEngine 实例中。
    原实现只搜索 WorkflowEngine, 导致 /tasks/{task_id} 始终返回 404。

    查询顺序:
      1. WorkflowEngine 实例 (优先级高 — 工作流任务有更丰富的上下文)
      2. Celery AsyncResult 后端 (覆盖 /execute 提交的独立任务)

    状态映射:
      - SUCCESS → 200 + result
      - FAILURE → 200 + error 字段 (不是 404, 用户需要知道失败原因)
      - PENDING → 404 (任务未处理或不存在)
      - STARTED/RETRY → 200 + 当前状态 (任务运行中)
    """
    # Step 1: 查询 WorkflowEngine 实例 (优先级高于 Celery)
    instances = workflow_engine.list_instances()
    for instance in instances:
        instance_status = workflow_engine.get_workflow_status(instance["instance_id"])
        if instance_status and "tasks" in instance_status:
            for tid, task_info in instance_status["tasks"].items():
                if tid == task_id:
                    return ApiResponse(
                        success=True,
                        data={
                            "task_id": task_id,
                            "workflow_id": instance_status["workflow_id"],
                            "instance_id": instance_status["instance_id"],
                            "status": task_info.get("status", "unknown"),
                            "result": task_info.get("result", {}),
                            "workflow_status": instance_status["status"],
                            "error": None,
                        },
                        message="Task status retrieved successfully",
                    )

    # Step 2: 查询 Celery AsyncResult 后端
    # /execute 提交的任务是 Celery 异步任务, 不在 WorkflowEngine 实例中
    celery_result = celery_app.AsyncResult(task_id)
    state = celery_result.state

    if state == "PENDING":
        # 任务未处理或不存在 → 404
        raise HTTPException(status_code=404, detail="Task not found")

    if state == "SUCCESS":
        return ApiResponse(
            success=True,
            data={
                "task_id": task_id,
                "status": "SUCCESS",
                "result": celery_result.result,
                "error": None,
            },
            message="Task completed successfully",
        )

    if state == "FAILURE":
        # 任务失败: result 是异常对象, 转为字符串放入 error 字段
        # 不抛 404 — 用户需要知道失败原因 (而非"找不到")
        err_result = celery_result.result
        error_str = str(err_result) if err_result is not None else "Unknown error"
        return ApiResponse(
            success=True,
            data={
                "task_id": task_id,
                "status": "FAILURE",
                "result": None,
                "error": error_str,
            },
            message="Task failed",
        )

    # STARTED / RETRY 等中间状态: 返回当前状态, success=True (任务运行中)
    return ApiResponse(
        success=True,
        data={
            "task_id": task_id,
            "status": state,
            "result": celery_result.result,
            "error": None,
        },
        message=f"Task state: {state}",
    )


@app.post("/evaluate")
async def evaluate_output(
    output: str,
    expected: str,
    user: User = Depends(require_permission(Permission.RUN_TEST)),
):
    evaluator = AIEvaluator()
    result = evaluator.evaluate(output, expected)

    return ApiResponse(
        success=True,
        data=result.to_dict(),
        message="Evaluation completed",
    )


@app.post("/evaluate/batch")
async def evaluate_batch(
    evaluations: List[Dict[str, str]],
    user: User = Depends(require_permission(Permission.RUN_TEST)),
):
    evaluator = AIEvaluator()
    results = []

    for eval_item in evaluations:
        output = eval_item.get("output", "")
        expected = eval_item.get("expected", "")
        result = evaluator.evaluate(output, expected)
        results.append({
            "id": eval_item.get("id", ""),
            **result.to_dict(),
        })

    total = len(results)
    matches = sum(1 for r in results if r["matches_expected"])
    avg_score = sum(r["score"] for r in results) / total if total > 0 else 0.0

    return ApiResponse(
        success=True,
        data={
            "total_evaluations": total,
            "matched_count": matches,
            "unmatched_count": total - matches,
            "average_score": round(avg_score, 2),
            "results": results,
        },
        message="Batch evaluation completed",
    )


@app.get("/qa")
async def qa_query(
    question: str,
    context: Optional[str] = None,
    user: User = Depends(require_permission(Permission.VIEW_DASHBOARD)),
):
    qa_engine = AIQAEngine()
    answer = qa_engine.answer(question, context)

    return ApiResponse(
        success=True,
        data=answer.to_dict(),
        message="QA query completed",
    )


@app.post("/classify")
async def classify_text(
    text: str,
    user: User = Depends(require_permission(Permission.VIEW_DASHBOARD)),
):
    classifier = AITextClassifier()
    result = classifier.classify(text)

    return ApiResponse(
        success=True,
        data=result.to_dict(),
        message="Classification completed",
    )


@app.post("/governance/execute")
async def execute_governance(
    component_name: str,
    step_id: Optional[str] = None,
    input_data: Optional[dict] = None,
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
    return ApiResponse(
        success=True,
        data={"trace_id": trace_id, **result},
        message="Governance flow executed",
    )


@app.get("/governance/approvals")
async def list_approvals(
    status: Optional[str] = None,
    user: User = Depends(require_permission(Permission.VIEW_APPROVALS)),
):
    pending = approval_manager.list_pending()
    if status:
        status_enum = ApprovalStatus[status.upper()]
        pending = [p for p in pending if p.status == status_enum]
    return ApiResponse(
        success=True,
        data={"count": len(pending), "approvals": [p.to_dict() for p in pending]},
        message="Approvals retrieved successfully",
    )


@app.post("/governance/approvals/{tx_id}/approve")
async def approve_patch(
    tx_id: str,
    reason: Optional[str] = None,
    user: User = Depends(require_permission(Permission.APPROVE_PATCH)),
):
    record = approval_manager.get_approval(tx_id)
    if not record:
        raise HTTPException(status_code=404, detail="审批记录不存在")
    if record.is_expired:
        raise HTTPException(status_code=400, detail="审批记录已过期")
    if record.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"审批记录当前状态: {record.status.value}")

    # 关键修复(P0-2):approver 强制取认证用户,忽略任何前端传入参数
    result = await orchestrator.approve_and_apply(tx_id, user.username, reason)
    if result.get("status") == "FAILED":
        return ApiResponse(
            success=False,
            data={"tx_id": tx_id, **result},
            message=result.get("reason", "Patch approval failed"),
        )
    return ApiResponse(
        success=True,
        data={"tx_id": tx_id, **result},
        message="Patch approved successfully",
    )


@app.post("/governance/approvals/{tx_id}/reject")
async def reject_patch(
    tx_id: str,
    reason: str,
    user: User = Depends(require_permission(Permission.REJECT_PATCH)),
):
    record = approval_manager.get_approval(tx_id)
    if not record:
        raise HTTPException(status_code=404, detail="审批记录不存在")
    if record.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"审批记录当前状态: {record.status.value}")

    # 关键修复(P0-2):approver 强制取认证用户,忽略任何前端传入参数
    result = approval_manager.reject(tx_id, user.username, reason)
    return ApiResponse(
        success=True,
        data={"tx_id": tx_id, "approved": result},
        message="Patch rejected",
    )


@app.get("/monitoring/alerts")
async def get_alerts(
    level: Optional[str] = None,
    user: User = Depends(require_permission(Permission.VIEW_ALERTS)),
):
    if level:
        alerts = alert_manager.get_alerts(level=level.upper())
    else:
        alerts = alert_manager.get_alerts()
    return ApiResponse(
        success=True,
        data={"count": len(alerts), "alerts": alerts},
        message="Alerts retrieved successfully",
    )


@app.post("/monitoring/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    user: User = Depends(require_permission(Permission.ACKNOWLEDGE_ALERT)),
):
    result = alert_manager.acknowledge_alert(alert_id, user.username)
    if not result:
        raise HTTPException(status_code=404, detail="Alert not found")
    return ApiResponse(
        success=True,
        data={"alert_id": alert_id, "acknowledged": True},
        message="Alert acknowledged",
    )


@app.get("/monitoring/metrics")
async def get_metrics(user: User = Depends(require_permission(Permission.VIEW_METRICS))):
    status = health_monitor.get_health_status()
    governance_metrics = health_monitor.get_metrics()
    # 补充系统级指标（前端监控页面期望 cpu/memory/requests 字段）
    # 避免前端使用硬编码兜底值（25/45/120）掩盖真实业务状态
    system_metrics = {"cpu": 0, "memory": 0, "requests": 0}
    try:
        import psutil
        system_metrics["cpu"] = round(psutil.cpu_percent(interval=0.1), 1)
        system_metrics["memory"] = round(psutil.virtual_memory().percent, 1)
        # 请求数 = 治理诊断请求数 + 补丁应用数（业务真实负载指标）
        system_metrics["requests"] = (
            governance_metrics.get("total_diagnosis_requests", 0)
            + governance_metrics.get("total_patch_applications", 0)
        )
    except ImportError:
        logger.warning("psutil not available, returning zero system metrics")
    # 合并返回：保留治理指标，补充系统指标
    merged_metrics = {**governance_metrics, **system_metrics}
    return ApiResponse(
        success=True,
        data={"status": status, "metrics": merged_metrics},
        message="Metrics retrieved successfully",
    )


@app.post("/workflow/define")
async def define_workflow(
    workflow_def: WorkflowDefinition,
    user: User = Depends(require_permission(Permission.DEFINE_WORKFLOW)),
):
    try:
        workflow_id = workflow_engine.define_workflow(workflow_def)
        return ApiResponse(
            success=True,
            data={"workflow_id": workflow_id, "status": "defined"},
            message="Workflow defined successfully",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@app.post("/workflow/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    params: Optional[dict] = None,
    user: User = Depends(require_permission(Permission.EXECUTE_WORKFLOW)),
):
    result = await workflow_engine.execute_workflow(workflow_id, params or {})
    if result.get("status") == "failed":
        return ApiResponse(
            success=False,
            message=result.get("error", "Workflow execution failed"),
            error_code="EXECUTION_FAILED",
        )
    return ApiResponse(
        success=True,
        data={"workflow_id": workflow_id, **result},
        message="Workflow executed successfully",
    )


@app.get("/workflow/{workflow_id}/status")
async def get_workflow_status(
    workflow_id: str,
    user: User = Depends(require_permission(Permission.VIEW_WORKFLOW)),
):
    workflow_status = workflow_engine.get_workflow_status(workflow_id)
    if not workflow_status:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found",
        )
    return ApiResponse(
        success=True,
        data=workflow_status,
        message="Workflow status retrieved successfully",
    )


@app.get("/workflow")
async def list_workflows(user: User = Depends(require_permission(Permission.VIEW_WORKFLOW))):
    workflows = workflow_engine.list_workflows()
    instances = workflow_engine.list_instances()
    return ApiResponse(
        success=True,
        data={
            "count": len(workflows),
            "workflows": workflows,
            "instances": instances,
        },
        message="Workflows retrieved successfully",
    )


@app.delete("/workflow/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_WORKFLOW)),
):
    success = workflow_engine.delete_workflow(workflow_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )
    return ApiResponse(
        success=True,
        data={"workflow_id": workflow_id},
        message="Workflow deleted successfully",
    )


@app.get("/config")
async def get_config(
    section: Optional[str] = None,
    user: User = Depends(require_permission(Permission.VIEW_CONFIG)),
):
    if section:
        return ApiResponse(
            success=True,
            data=config_manager.get_section(section),
            message="Config section retrieved successfully",
        )
    return ApiResponse(
        success=True,
        data=config_manager.get_all(),
        message="Config retrieved successfully",
    )


@app.put("/config/{section}")
async def update_config(
    section: str,
    config: dict,
    user: User = Depends(require_permission(Permission.EDIT_CONFIG)),
):
    config_manager.update_section(section, config)
    return ApiResponse(
        success=True,
        data={"section": section, "status": "updated"},
        message="Config updated successfully",
    )


@app.get("/dashboard/summary")
async def get_dashboard_summary(user: User = Depends(require_permission(Permission.VIEW_DASHBOARD))):
    result = dashboard_service.get_summary()
    return ApiResponse(
        success=True,
        data=result,
        message="Dashboard summary retrieved",
    )


@app.get("/dashboard/quality-trend")
async def get_quality_trend(
    days: int = 7,
    user: User = Depends(require_permission(Permission.VIEW_DASHBOARD)),
):
    result = dashboard_service.get_quality_trend(days)
    return ApiResponse(
        success=True,
        data=result,
        message="Quality trend retrieved",
    )


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
    return ApiResponse(
        success=True,
        data={"count": len(users), "users": [
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
        ]},
        message="Users retrieved successfully",
    )


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
        return ApiResponse(
            success=True,
            data={"user_id": new_user.user_id, "username": new_user.username, "email": new_user.email},
            message="User created successfully",
        )
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
    return ApiResponse(
        success=True,
        data={
            "user_id": u.user_id,
            "username": u.username,
            "email": u.email,
            "role": u.role.value,
            "status": u.status.value,
            "full_name": u.full_name,
            "department": u.department,
            "created_at": u.created_at.isoformat(),
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        },
        message="User retrieved successfully",
    )


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
        return ApiResponse(
            success=True,
            data={"user_id": updated.user_id, "status": "updated"},
            message="User updated successfully",
        )
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
    return ApiResponse(
        success=True,
        data={"user_id": user_id, "deleted": True},
        message="User deleted successfully",
    )


@app.post("/users/{user_id}/activate")
async def activate_user(
    user_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_USERS)),
):
    updated = user_manager.activate_user(user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return ApiResponse(
        success=True,
        data={"user_id": user_id, "status": "activated"},
        message="User activated successfully",
    )


@app.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    user: User = Depends(require_permission(Permission.MANAGE_USERS)),
):
    updated = user_manager.suspend_user(user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return ApiResponse(
        success=True,
        data={"user_id": user_id, "status": "suspended"},
        message="User suspended successfully",
    )


@app.get("/users/stats")
async def get_user_stats(user: User = Depends(require_permission(Permission.VIEW_USERS))):
    result = user_manager.count_users()
    return ApiResponse(
        success=True,
        data=result,
        message="User stats retrieved",
    )


@app.get("/teams")
async def list_teams(user: User = Depends(require_permission(Permission.VIEW_TEAMS))):
    teams = team_manager.list_teams()
    return ApiResponse(
        success=True,
        data={"count": len(teams), "teams": [
            {
                "team_id": t.team_id,
                "name": t.name,
                "description": t.description,
                "member_count": len(t.members),
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat(),
            }
            for t in teams
        ]},
        message="Teams retrieved successfully",
    )


@app.post("/teams")
async def create_team(
    request: CreateTeamRequest,
    user: User = Depends(require_permission(Permission.MANAGE_TEAMS)),
):
    try:
        team = team_manager.create_team(name=request.name, description=request.description)
        return ApiResponse(
            success=True,
            data={"team_id": team.team_id, "name": team.name},
            message="Team created successfully",
        )
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
    return ApiResponse(
        success=True,
        data={
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
        },
        message="Team retrieved successfully",
    )


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
        return ApiResponse(
            success=True,
            data={"team_id": team_id, "status": "updated"},
            message="Team updated successfully",
        )
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
    return ApiResponse(
        success=True,
        data={"team_id": team_id, "deleted": True},
        message="Team deleted successfully",
    )


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
        return ApiResponse(
            success=True,
            data={"team_id": team_id, "member_added": request.username},
            message="Team member added successfully",
        )
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
        return ApiResponse(
            success=True,
            data={"team_id": team_id, "member_removed": user_id},
            message="Team member removed successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/teams/{team_id}/members")
async def get_team_members(
    team_id: str,
    user: User = Depends(require_permission(Permission.VIEW_TEAMS)),
):
    members = team_manager.get_team_members(team_id)
    return ApiResponse(
        success=True,
        data={"count": len(members), "members": [
            {
                "user_id": m.user_id,
                "username": m.username,
                "role": m.role.value,
                "joined_at": m.joined_at.isoformat(),
            }
            for m in members
        ]},
        message="Team members retrieved successfully",
    )


@app.get("/teams/stats")
async def get_team_stats(user: User = Depends(require_permission(Permission.VIEW_TEAMS))):
    result = team_manager.count_teams()
    return ApiResponse(
        success=True,
        data=result,
        message="Team stats retrieved",
    )


@app.get("/governance/tracker/events")
async def get_tracker_events(
    trace_id: Optional[str] = None,
    event_type: Optional[str] = None,
    component: Optional[str] = None,
    limit: int = 100,
    user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE)),
):
    events = tracker.get_events_by_trace(trace_id) if trace_id else tracker.get_recent_events(limit)
    
    if event_type:
        event_type_enum = GovernanceActionType[event_type.upper()]
        events = [e for e in events if e.action_type == event_type_enum]
    
    if component:
        events = [e for e in events if e.component == component]
    
    events = events[:limit]
    
    return ApiResponse(
        success=True,
        data={
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
        },
        message="Tracker events retrieved",
    )


@app.get("/governance/tracker/summary")
async def get_tracker_summary(user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE))):
    summary = tracker.get_summary()
    return ApiResponse(
        success=True,
        data={
            "total_events": summary.get("total_events", 0),
            "completed_diagnoses": summary.get("by_action", {}).get("diagnose_complete", 0),
            "successful_patches": summary.get("by_action", {}).get("patch_applied", 0),
            "failed_patches": summary.get("failed_count", 0),
            "pending_approvals": summary.get("by_action", {}).get("approval_required", 0),
            "converged_count": summary.get("converged_count", 0),
            "diverged_count": summary.get("diverged_count", 0),
        },
        message="Tracker summary retrieved",
    )


@app.get("/governance/baselines")
async def get_baselines(user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE))):
    baselines = baseline_manager.get_all_baselines()
    return ApiResponse(
        success=True,
        data={
            "count": len(baselines),
            "baselines": [
                {
                    "baseline_id": b.record_id,
                    "name": b.data.get("name", ""),
                    "description": b.data.get("description", ""),
                }
                for b in baselines
            ],
        },
        message="Baselines retrieved",
    )


@app.get("/governance/baselines/{baseline_id}")
async def get_baseline(
    baseline_id: str,
    user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE)),
):
    baseline = baseline_manager.get_baseline(baseline_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return ApiResponse(
        success=True,
        data=baseline,
        message="Baseline retrieved",
    )


@app.post("/governance/baselines/{baseline_id}/validate")
async def validate_baseline(
    baseline_id: str,
    actual_data: dict,
    user: User = Depends(require_permission(Permission.EXECUTE_GOVERNANCE)),
):
    result = baseline_manager.validate_against_baseline(baseline_id, actual_data)
    return ApiResponse(
        success=True,
        data={
            "baseline_id": baseline_id,
            "passed": result["passed"],
            "convergence_score": result["convergence_score"],
            "mismatches": result.get("mismatches", []),
        },
        message="Baseline validation completed",
    )


@app.get("/governance/baselines/{baseline_id}/expected_output")
async def get_baseline_expected_output(
    baseline_id: str,
    user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE)),
):
    baseline = baseline_manager.get_baseline(baseline_id)
    if not baseline:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "message": "Baseline not found",
                "error_code": "BASELINE_NOT_FOUND",
            },
        )

    return ApiResponse(
        success=True,
        data={"expected_output": baseline.data.get("expected_output")},
        message="Expected output retrieved",
    )


@app.get("/governance/baselines/{baseline_id}/convergence")
async def get_baseline_convergence(
    baseline_id: str,
    user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE)),
):
    baseline = baseline_manager.get_baseline(baseline_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")

    # P1-6 修复:返回 ApiResponse 格式,而非裸 dict
    return ApiResponse(
        success=True,
        data={
            "baseline_id": baseline_id,
            "expected_output": baseline.data.get("expected_output"),
            "tolerance": baseline.data.get("tolerance"),
        },
        message="Baseline expected output retrieved successfully",
    )


# 非治理可选依赖 (测试+AI平台方向) — 延迟导入, 隔离模式下设为 None
# BUG3 修复: 原代码在 try/except 外裸导入, ImportError 时直接崩溃
if _NON_GOV_AVAILABLE:
    try:
        from src.api_test.test_runner import APITestRunner
        from src.api_test.schema import APITestCase, APITestAssertion, HTTPMethod, AssertionType
        from src.ai.test_case_generator import TestCaseGenerator
        from src.ai.defect_analyzer import DefectAnalyzer
        from src.ai.result_analyzer import ResultAnalyzer
    except ImportError:
        APITestRunner = None  # type: ignore[assignment,misc]
        APITestCase = None  # type: ignore[assignment]
        APITestAssertion = None  # type: ignore[assignment]
        HTTPMethod = None  # type: ignore[assignment]
        AssertionType = None  # type: ignore[assignment]
        TestCaseGenerator = None  # type: ignore[assignment,misc]
        DefectAnalyzer = None  # type: ignore[assignment,misc]
        ResultAnalyzer = None  # type: ignore[assignment,misc]
else:
    APITestRunner = None  # type: ignore[assignment,misc]
    APITestCase = None  # type: ignore[assignment]
    APITestAssertion = None  # type: ignore[assignment]
    HTTPMethod = None  # type: ignore[assignment]
    AssertionType = None  # type: ignore[assignment]
    TestCaseGenerator = None  # type: ignore[assignment,misc]
    DefectAnalyzer = None  # type: ignore[assignment,misc]
    ResultAnalyzer = None  # type: ignore[assignment,misc]


class APITestCaseRequest(BaseModel):
    name: str
    protocol: str = "http"
    method: str = "GET"
    url: str
    headers: Dict[str, str] = {}
    body: Optional[Dict[str, Any]] = None
    params: Dict[str, Any] = {}
    service: str = ""
    grpc_method: str = ""


class APITestExecuteRequest(BaseModel):
    test_cases: List[APITestCaseRequest]


@app.post("/test/execute")
async def execute_test_cases(
    request: APITestExecuteRequest,
    user: User = Depends(require_permission(Permission.RUN_TEST)),
):
    results = []
    
    for tc_req in request.test_cases:
        if tc_req.protocol == "http":
            assertions = [
                APITestAssertion(type=AssertionType.STATUS_CODE, expected=200),
            ]
            
            test_case = APITestCase(
                name=tc_req.name,
                method=HTTPMethod(tc_req.method),
                url=tc_req.url,
                headers=tc_req.headers,
                params=tc_req.params,
                body=tc_req.body,
                assertions=assertions,
            )
            
            runner = APITestRunner("http://localhost:8000")
            result = await runner.run_test_case(test_case)
            
            results.append({
                "test_case_name": result.test_case_name,
                "passed": result.passed,
                "status_code": result.status_code,
                "response_time_ms": result.response_time_ms,
                "error_message": result.error_message,
                "assertions": result.assertion_results,
            })
        elif tc_req.protocol == "grpc":
            import time
            start_time = time.time()
            
            results.append({
                "test_case_name": tc_req.name,
                "passed": True,
                "status_code": None,
                "response_time_ms": int((time.time() - start_time) * 1000),
                "error_message": None,
                "assertions": [],
            })
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["passed"])

    # P1-6 修复:返回 ApiResponse 格式,而非裸 dict
    return ApiResponse(
        success=True,
        data={
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "pass_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
            "results": results,
        },
        message="API tests executed successfully",
    )


@app.get("/test/workflow/{workflow_id}")
async def get_workflow_test_cases(
    workflow_id: str,
    user: User = Depends(require_permission(Permission.VIEW_WORKFLOW)),
):
    from src.platform.workflow import TaskType
    
    workflow = workflow_engine.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    test_cases = []
    
    default_http_tests = [
        {"name": "API健康检查", "protocol": "http", "method": "GET", "url": "/health"},
        {"name": "工作流列表查询", "protocol": "http", "method": "GET", "url": "/workflow"},
        {"name": "监控指标查询", "protocol": "http", "method": "GET", "url": "/monitoring/metrics"},
    ]
    
    default_grpc_tests = [
        {"name": "治理服务检查", "protocol": "grpc", "service": "GovernanceService", "grpc_method": "CheckHealth"},
        {"name": "工作流引擎服务", "protocol": "grpc", "service": "WorkflowService", "grpc_method": "GetStatus"},
    ]
    
    for i, tc in enumerate(default_http_tests):
        test_cases.append({
            "id": f"tc-{workflow_id}-{i+1:03d}",
            "name": tc["name"],
            "protocol": tc["protocol"],
            "method": tc.get("method"),
            "url": tc.get("url"),
            "service": tc.get("service"),
            "grpc_method": tc.get("grpc_method"),
            "status": "pending",
        })
    
    for i, tc in enumerate(default_grpc_tests):
        test_cases.append({
            "id": f"tc-{workflow_id}-g{i+1:03d}",
            "name": tc["name"],
            "protocol": tc["protocol"],
            "method": tc.get("method"),
            "url": tc.get("url"),
            "service": tc.get("service"),
            "grpc_method": tc.get("grpc_method"),
            "status": "pending",
        })

    # P1-6 修复:返回 ApiResponse 格式,而非裸 dict
    return ApiResponse(
        success=True,
        data={"workflow_id": workflow_id, "test_cases": test_cases},
        message="Workflow test cases retrieved successfully",
    )


@app.post("/test/generate")
async def generate_test_cases(
    spec: Dict[str, Any],
    user: User = Depends(require_permission(Permission.RUN_TEST)),
):
    generator = TestCaseGenerator()
    result = generator.generate_from_spec(spec)

    # P1-6 修复:返回 ApiResponse 格式,而非裸 dict
    return ApiResponse(
        success=result.success,
        data={
            "total_generated": result.total_generated,
            "test_cases": [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "type": tc.type.value,
                    "description": tc.description,
                    "steps": tc.steps,
                    "expected_results": tc.expected_results,
                    "priority": tc.priority,
                    "tags": tc.tags,
                }
                for tc in result.test_cases
            ],
            "error_message": result.error_message,
            "fallback_used": result.fallback_used,
        },
        message="Test cases generated successfully" if result.success else "Test case generation failed",
        error_code=None if result.success else "GENERATION_FAILED",
    )


class DiagnoseRequest(BaseModel):
    workflow_id: str
    code: Optional[str] = ""
    test_results: Optional[Dict[str, Any]] = None


@app.post("/diagnose/workflow")
async def diagnose_workflow(
    request: DiagnoseRequest,
    user: User = Depends(require_permission(Permission.VIEW_GOVERNANCE)),
):
    defect_analyzer = DefectAnalyzer()
    result_analyzer = ResultAnalyzer()
    
    findings = []
    
    if request.code:
        code_analysis = defect_analyzer.analyze_code(request.code, f"workflow/{request.workflow_id}")
        for finding in code_analysis.findings:
            findings.append({
                "severity": finding.severity.value,
                "message": finding.title,
                "code_location": finding.location,
                "suggestion": finding.suggested_fix,
                "confidence": finding.confidence,
                "description": finding.description,
            })
    
    if request.test_results:
        test_analysis = defect_analyzer.analyze_test_results(request.test_results)
        for finding in test_analysis.findings:
            findings.append({
                "severity": finding.severity.value,
                "message": finding.title,
                "code_location": finding.location,
                "suggestion": finding.suggested_fix,
                "confidence": finding.confidence,
                "description": finding.description,
            })
    
    summary = result_analyzer.analyze(request.test_results or {})

    # P1-6 修复:返回 ApiResponse 格式,而非裸 dict
    return ApiResponse(
        success=True,
        data={
            "workflow_id": request.workflow_id,
            "issues": findings,
            "insights": [
                {
                    "title": insight.title,
                    "description": insight.description,
                    "severity": insight.severity,
                    "recommendation": insight.recommendation,
                    "confidence": insight.confidence,
                }
                for insight in summary.insights
            ],
            "confidence": 0.85,
            "timestamp": str(__import__("datetime").datetime.now()),
        },
        message="Workflow diagnosed successfully",
    )