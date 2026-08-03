# tests/conftest.py - 统一测试隔离 fixture

import logging
import os
import sys

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/testai")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-for-ci")

# =============================================================================
# 修复 ValueError: I/O operation on closed file
# =============================================================================
# 根因: pytest capture 系统替换 sys.stderr 为 CaptureIO 对象 (使用 tmpfile)。
# 当 TokenManager/GovernanceTracker 等单例在 fixture setup 期间 logging.warning()
# 时,logging 的 StreamHandler 持有对 CaptureIO 的引用。session teardown 时
# pytest 关闭 CaptureIO 的 tmpfile,但 handler 仍尝试写入 → ValueError。
#
# 此错误被 -W error::RuntimeWarning 升级为 ERROR,导致 fixture setup/teardown
# 崩溃 (pytest 报 ERROR 而非 FAILED)。
#
# 修复策略: 在 conftest 加载时禁用所有 logging handler,改用 NullHandler。
# 测试日志对 CI 门禁无价值,而禁用 handler 从根本上消除了对 closed stream 的写入。
# =============================================================================
_logging_root = logging.getLogger()
_logging_root.handlers.clear()
_logging_root.addHandler(logging.NullHandler())
_logging_root.setLevel(logging.CRITICAL)

# 对所有已知的模块 logger 也设置 NullHandler
for _logger_name in (
    "src", "src.security", "src.security.auth", "src.governance",
    "src.governance.tracker", "src.governance.approval", "src.platform",
    "src.platform.api", "src.platform.config_manager", "src.ai",
    "src.report", "src.report.generator", "src.report.storage",
    "src.users", "src.teams", "src.storage", "src.core",
):
    _lg = logging.getLogger(_logger_name)
    _lg.handlers.clear()
    _lg.addHandler(logging.NullHandler())
    _lg.setLevel(logging.CRITICAL)
    _lg.propagate = True  # 让记录传播到 root NullHandler

from src.platform.api import app
from src.report.generator import generator
from src.report.storage import registry

# 模块导入后再次清理 — 某些模块在 import 时添加了自己的 handler
_logging_root.handlers.clear()
_logging_root.addHandler(logging.NullHandler())

GLOBAL_RESULTS = {}


@pytest.fixture
def client():
    from src.security.auth import TokenManager
    token_manager = TokenManager()
    token_manager._login_attempts.clear()
    
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    from src.security.auth import TokenManager
    token_manager = TokenManager()
    with token_manager._lock:
        token_manager._login_attempts.clear()
    
    response = client.post("/auth/login", json={"username": "admin", "password": "password"})
    assert response.status_code == 200, f"登录失败: {response.status_code} - {response.text}"
    data = response.json()
    token = data["data"]["access_token"] if "data" in data else data.get("access_token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_token(client):
    from src.security.auth import TokenManager
    token_manager = TokenManager()
    with token_manager._lock:
        token_manager._login_attempts.clear()
    
    response = client.post("/auth/login", json={"username": "admin", "password": "password"})
    assert response.status_code == 200, f"登录失败: {response.status_code} - {response.text}"
    data = response.json()
    return data["data"]["access_token"] if "data" in data else data.get("access_token")


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ==================== 统一单例重置策略 ====================

# 单例类注册表:每个单例需要重置的属性
# 格式: (类引用, {"_instance": None, "类变量名": 默认值, ...})
_SINGLETON_REGISTRY = []


def _register_singleton(singleton_class, reset_attrs):
    """注册单例类及其需要重置的属性。"""
    _SINGLETON_REGISTRY.append((singleton_class, reset_attrs))


def _reset_all_singletons():
    """重置所有已注册的单例类。

    策略:
    1. 重置类级别的 _instance = None
    2. 重置类级别的可变属性(如 _approvals, _events, _users 等)
    3. 如果实例已存在,也重置实例级别的可变属性
    """
    for singleton_class, reset_attrs in _SINGLETON_REGISTRY:
        # 重置类级别属性
        for attr_name, default_value in reset_attrs.items():
            if hasattr(singleton_class, attr_name):
                setattr(singleton_class, attr_name, default_value)

        # 重置实例级别属性(如果实例存在)
        instance = getattr(singleton_class, "_instance", None)
        if instance is not None:
            for attr_name, default_value in reset_attrs.items():
                if attr_name != "_instance" and hasattr(instance, attr_name):
                    setattr(instance, attr_name, default_value)


@pytest.fixture(autouse=True)
def reset_all_singletons():
    """统一重置所有单例,确保测试隔离。

    问题背景:
    - ApprovalManager/GovernanceTracker 等单例使用类变量存储状态(_approvals, _events)
    - TokenManager/UserManager/TeamManager 虽然不是单例,但模块级实例被共享
    - 测试间状态污染导致:
      1. tx_id 唯一性校验失败(P0修复后引入)
      2. 用户/团队数据持久化导致后续测试期望不一致
      3. WorkflowEngine 的 workflows/instances 积累导致 ID 冲突
      4. 登录速率限制状态未重置导致后续测试被拒绝

    解决策略:
    - 在每个测试前后重置所有单例的 _instance 和可变状态
    - 使用注册表模式,新增单例只需注册即可
    - 同时重置类级别和实例级别的属性(影子覆盖问题)
    """
    # 初始化注册表(延迟导入避免循环依赖)
    if not _SINGLETON_REGISTRY:
        _init_singleton_registry()

    # 测试前重置 — 包裹 try/except 防止 Linux CI I/O 流异常
    token_manager = None
    try:
        _reset_all_singletons()

        from src.security.auth import TokenManager
        token_manager = TokenManager()
        with token_manager._lock:
            token_manager._login_attempts.clear()
    except (ValueError, OSError):
        # Linux CI: coverage plugin 可能已关闭 stderr,
        # TokenManager() 的日志写入会触发 ValueError。
        # _SafeStreamHandler 应已拦截, 但此处做最后防线。
        pass

    yield
    # 测试后再次重置(确保本测试不污染后续测试)
    try:
        _reset_all_singletons()

        if token_manager is not None:
            with token_manager._lock:
                token_manager._login_attempts.clear()
    except (ValueError, OSError):
        pass


def _init_singleton_registry():
    """初始化单例注册表。"""
    # ApprovalManager - 单例模式,类变量 _approvals
    from src.governance.approval import ApprovalManager
    _register_singleton(ApprovalManager, {
        "_instance": None,
        "_approvals": {},
        "_db_path": None,
    })

    # GovernanceTracker - 单例模式,类变量 _events
    from src.governance.tracker import GovernanceTracker
    _register_singleton(GovernanceTracker, {
        "_instance": None,
        "_events": [],
    })

    # GoldenBaselineManager - 单例模式
    from src.governance.baseline import GoldenBaselineManager
    _register_singleton(GoldenBaselineManager, {
        "_instance": None,
    })

    # StructuredLogger - 单例模式
    from src.governance.monitoring import StructuredLogger
    _register_singleton(StructuredLogger, {
        "_instance": None,
    })

    # AlertManager (governance) - 单例模式
    from src.governance.monitoring import AlertManager as GovernanceAlertManager
    _register_singleton(GovernanceAlertManager, {
        "_instance": None,
    })

    # HealthMonitor - 单例模式
    from src.governance.monitoring import HealthMonitor
    _register_singleton(HealthMonitor, {
        "_instance": None,
    })

    # ProcessManager - 单例模式
    from src.governance.process_manager import ProcessManager
    _register_singleton(ProcessManager, {
        "_instance": None,
        "_processes": {},
        "_running": False,
    })

    # GovernanceRegistry - 单例模式
    from src.governance.registry import GovernanceRegistry
    from src.governance.transformer import ContextAwareTransformer, FunctionTransformer
    from src.governance.registry import PatchType
    _register_singleton(GovernanceRegistry, {
        "_instance": None,
        "_registry": {
            PatchType.SECURITY: ContextAwareTransformer,
            PatchType.PERFORMANCE: FunctionTransformer,
            PatchType.FUNCTIONAL: FunctionTransformer,
            PatchType.REFACTORING: ContextAwareTransformer,
        },
    })

    # GovernanceClientSDK - 单例模式
    from src.governance.sdk import GovernanceClientSDK
    _register_singleton(GovernanceClientSDK, {
        "_instance": None,
    })

    # TokenManager - 单例模式
    from src.security.auth import TokenManager
    _register_singleton(TokenManager, {
        "_instance": None,
        "users": {},
        "_password_hashes": {},
        "_login_attempts": {},
        "_initialized": False,
    })

    # UserManager - 单例模式
    from src.users.user_manager import UserManager
    _register_singleton(UserManager, {
        "_instance": None,
        "users": {},
        "_initialized": False,
    })

    # TeamManager - 单例模式
    from src.teams.team_manager import TeamManager
    _register_singleton(TeamManager, {
        "_instance": None,
        "teams": {},
        "_initialized": False,
    })

    # WorkflowEngine - 单例模式
    from src.platform.workflow import WorkflowEngine
    _register_singleton(WorkflowEngine, {
        "_instance": None,
        "workflows": {},
        "instances": {},
        "_initialized": False,
    })

    # ConfigManager - 单例模式
    from src.platform.config_manager import ConfigManager
    _register_singleton(ConfigManager, {
        "_instance": None,
        "_sections": {},
        "_initialized": False,
    })

    # DatabaseManager - 单例模式
    from src.storage.database import DatabaseManager
    _register_singleton(DatabaseManager, {
        "_instance": None,
        "_initialized": False,
    })

    # FileLockManager - 单例模式
    from src.governance.file_lock import FileLockManager
    _register_singleton(FileLockManager, {
        "_instance": None,
    })

    # ResourceContainer - 单例模式
    from src.core.container import ResourceContainer
    _register_singleton(ResourceContainer, {
        "_instance": None,
        "_client": None,
        "_repo": None,
    })





@pytest.fixture(scope="session", autouse=True)
def run_report_generator():
    yield
    # Session teardown: pytest capture may already be closed on Linux CI
    # (causes ValueError: I/O operation on closed file with -W error::RuntimeWarning).
    # Use try/except + logging fallback to avoid crashing the last test's teardown.
    try:
        all_data = registry.get_all()
        import sys
        out = sys.stderr if sys.stderr and not sys.stderr.closed else None
        if out:
            out.write(f"\n[DEBUG] Registry size: {len(all_data)}\n")
            out.flush()

        if all_data:
            report_path = generator.generate(all_data)
            if out:
                out.write(f"[SUCCESS] Report generated: {report_path}\n")
                out.flush()
    except (ValueError, OSError):
        # Capture system already torn down — report generation is best-effort
        pass
