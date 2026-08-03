"""
API 隔离模式严格测试

验证目标: 当非治理模块(测试+AI平台方向: users/teams/ai/api_test)缺失时,
api.py 必须仍能加载, 治理核心正常工作, 非治理端点返回 503。

背景 — 之前的"隔离"实现是假绿, 存在 4 个 P0 bug:
  BUG1: except 块中 logger.warning() 在 logger 定义之前 → NameError
  BUG2: UserManager()/TeamManager() 在 _NON_GOV_AVAILABLE=False 时 None() → TypeError
  BUG3: src.api_test.* 和部分 src.ai.* 在 try/except 外裸导入 → ImportError
  BUG4: 非治理端点无 503 守卫 → 运行时 AttributeError

隔离边界(经代码分析确认):
  - 治理硬依赖(必须存在): governance/*, security/*, platform/workflow, platform/config_manager,
    platform/dashboard, platform/metrics, worker/*, models/contract(HttpRequest — /execute 主路径依赖)
  - 非治理可选依赖(隔离对象): users/*, teams/*, ai/evaluator, ai/qa_engine, ai/classifier,
    ai/test_case_generator, ai/defect_analyzer, ai/result_analyzer, api_test/*

测试方法: 通过 sys.modules[mod] = None 强制 ModuleNotFoundError, 重新导入 api.py。
"""
import sys
import pytest
from fastapi.testclient import TestClient


# 非治理模块完整列表(测试+AI平台方向)。
# 注意: 不包含 src.models.contract — HttpRequest 是 /execute 主路径的请求体类型, 属治理硬依赖。
_NON_GOV_MODULES = [
    "src.users.user_manager",
    "src.teams.team_manager",
    "src.ai.evaluator",
    "src.ai.qa_engine",
    "src.ai.classifier",
    "src.ai.test_case_generator",
    "src.ai.defect_analyzer",
    "src.ai.result_analyzer",
    "src.api_test.test_runner",
    "src.api_test.schema",
]


@pytest.fixture
def isolated_api():
    """在非治理模块被屏蔽的环境中重新加载 api.py。

    通过 sys.modules[name] = None 强制 import 抛 ModuleNotFoundError(Python 3 行为)。
    finally 中完整恢复 sys.modules + 包属性, 不污染其他测试。

    关键修复: `from src.platform import api` 取的是 src.platform 包对象的 api 属性,
    不是 sys.modules["src.platform.api"]。import 时会把包属性指向隔离版模块,
    finally 必须同时恢复 sys.modules 和包属性, 否则 conftest 的 reset_all_singletons
    拿到隔离版的 team_manager=None, 导致后续 test_api.py 全线崩溃。
    """
    api_key = "src.platform.api"
    original_api = sys.modules.pop(api_key, None)

    # 保存 src.platform 包对象上的 api 属性原始值
    import src.platform as _platform_pkg
    original_pkg_attr = getattr(_platform_pkg, "api", "_MISSING_")

    saved = {}
    for mod in _NON_GOV_MODULES:
        saved[mod] = sys.modules.get(mod, "_MISSING_")
        sys.modules[mod] = None  # None → ModuleNotFoundError on import

    try:
        # 重新导入 — 隔离实现有 bug 时会在此直接崩溃(NameError/TypeError/ImportError)
        # 不使用 importlib.reload: import 已创建新模块, reload 会重复执行模块代码创建多余单例
        import src.platform.api as api_module  # noqa: E402
        yield api_module
    finally:
        # 1. 清理隔离版本 (从 sys.modules 移除)
        sys.modules.pop(api_key, None)
        # 2. 恢复非治理模块原始状态
        for mod, val in saved.items():
            if val == "_MISSING_":
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = val
        # 3. 恢复原始 api 模块到 sys.modules
        if original_api is not None:
            sys.modules[api_key] = original_api
        # 4. 恢复 src.platform 包对象的 api 属性 (关键! 否则 from src.platform import api 拿到隔离版)
        if original_pkg_attr != "_MISSING_":
            _platform_pkg.api = original_pkg_attr


# ==================== 正向: 隔离模式下 api.py 必须成功加载 ====================

class TestApiLoadsInIsolationMode:
    """隔离模式下 api.py 必须成功加载, 不崩溃。

    这组测试直接暴露 BUG1(logger NameError)、BUG2(None TypeError)、BUG3(裸 ImportError)。
    如果隔离实现有任何 bug, isolated_api fixture 的 import 会直接抛异常, fixture 报错。
    """

    def test_api_module_imports_without_error(self, isolated_api):
        """非治理模块缺失时, api.py 必须能成功导入(不抛 NameError/TypeError/ImportError)。"""
        assert isolated_api is not None, "api 模块导入失败 — 隔离实现有 P0 bug"

    def test_non_gov_available_flag_is_false(self, isolated_api):
        """_NON_GOV_AVAILABLE 必须为 False(非治理模块被屏蔽)。"""
        assert isolated_api._NON_GOV_AVAILABLE is False, (
            "_NON_GOV_AVAILABLE 应为 False — 说明 except ImportError 块未正确执行"
        )

    def test_app_object_exists(self, isolated_api):
        """FastAPI app 对象必须存在(路由注册未崩溃)。"""
        # 直接访问 .app (属性不存在时 AttributeError 比 hasattr 更早、更明确失败)
        assert isolated_api.app is not None, "app 对象缺失 — 模块加载不完整"


# ==================== 治理核心: 隔离模式下必须正常初始化 ====================

class TestGovernanceCoreIntact:
    """治理核心单例在隔离模式下必须正常初始化(非 None)。

    这些是治理平台的核心资产: orchestrator/approval/tracker/baseline/executor/health_monitor。
    """

    def test_orchestrator_initialized(self, isolated_api):
        assert isolated_api.orchestrator is not None, "治理编排器未初始化"

    def test_approval_manager_initialized(self, isolated_api):
        assert isolated_api.approval_manager is not None

    def test_tracker_initialized(self, isolated_api):
        assert isolated_api.tracker is not None

    def test_baseline_manager_initialized(self, isolated_api):
        assert isolated_api.baseline_manager is not None

    def test_executor_initialized(self, isolated_api):
        assert isolated_api.executor is not None

    def test_health_monitor_initialized(self, isolated_api):
        assert isolated_api.health_monitor is not None

    def test_token_manager_initialized(self, isolated_api):
        """认证管理器必须初始化 — 治理端点需要权限校验。"""
        assert isolated_api.token_manager is not None

    def test_http_request_available(self, isolated_api):
        """HttpRequest 必须可用 — 它是 /execute 主路径的请求体类型(治理硬依赖)。

        如果 HttpRequest 为 None, 说明 src.models.contract 被错误地归入非治理模块,
        /execute 端点将无法注册(FastAPI 无法解析 None 类型的请求体)。
        """
        assert isolated_api.HttpRequest is not None, (
            "HttpRequest 为 None — src.models.contract 不应在非治理 try/except 中"
        )


# ==================== 非治理单例: 隔离模式下必须为 None(非崩溃) ====================

class TestNonGovSingletonsNulled:
    """非治理单例在隔离模式下必须为 None(而不是崩溃)。

    暴露 BUG2: UserManager()/TeamManager() 在 _NON_GOV_AVAILABLE=False 时调用 None() → TypeError。
    正确行为: 检查 _NON_GOV_AVAILABLE, 为 False 时不实例化, 设为 None。
    """

    def test_user_manager_is_none(self, isolated_api):
        """user_manager 必须为 None(不是 TypeError 崩溃, 也不是 NoneType 实例)。"""
        assert isolated_api.user_manager is None, (
            "user_manager 应为 None — 说明 _NON_GOV_AVAILABLE=False 时仍调用了 UserManager()"
        )

    def test_team_manager_is_none(self, isolated_api):
        assert isolated_api.team_manager is None, (
            "team_manager 应为 None — 说明 _NON_GOV_AVAILABLE=False 时仍调用了 TeamManager()"
        )


# ==================== 路由注册: 治理端点存在, 非治理端点也存在(但返回503) ====================

class TestRouteRegistration:
    """隔离模式下所有路由必须正确注册。

    治理端点: 正常工作
    非治理端点: 路由注册成功, 但请求时返回 503(通过中间件/依赖守卫)
    """

    def _get_paths(self, app):
        return {getattr(r, "path", None) for r in app.routes}

    def test_governance_routes_registered(self, isolated_api):
        """治理端点必须全部注册。"""
        paths = self._get_paths(isolated_api.app)
        required = {
            "/governance/execute",
            "/governance/approvals",
            "/governance/approvals/{tx_id}/approve",
            "/governance/approvals/{tx_id}/reject",
            "/governance/tracker/events",
            "/governance/tracker/summary",
            "/governance/baselines",
            "/monitoring/alerts",
            "/monitoring/metrics",
            "/health",
            "/metrics",
            "/execute",  # 主路径
        }
        missing = required - paths
        assert not missing, f"治理端点未注册: {missing}"

    def test_non_gov_routes_registered(self, isolated_api):
        """非治理端点路由也必须注册(只是请求时返回 503, 不是路由消失)。

        路由消失会导致客户端收到 404, 与 503(服务不可用)语义不同。
        503 表示"端点存在但依赖不可用", 这才是正确的隔离语义。
        """
        paths = self._get_paths(isolated_api.app)
        expected_non_gov = {
            "/users",
            "/teams",
            "/evaluate",
            "/qa",
            "/classify",
            "/test/execute",
            "/test/generate",
            "/diagnose/workflow",
        }
        missing = expected_non_gov - paths
        assert not missing, f"非治理端点路由未注册(应返回503而非404): {missing}"


# ==================== 端点级 503 守卫 ====================

class TestNonGovEndpointsReturn503:
    """非治理端点在隔离模式下必须返回 503 Service Unavailable。

    暴露 BUG4: 非治理端点无 503 守卫 → 调用 None.list_users() → AttributeError 500。
    正确行为: 中间件或依赖检查 _NON_GOV_AVAILABLE, 返回 503。
    """

    @pytest.fixture(autouse=True)
    def _client(self, isolated_api):
        # raise_server_exceptions=False: 即使端点内部崩溃也返回 500 而非抛异常
        self.client = TestClient(isolated_api.app, raise_server_exceptions=False)
        yield

    # --- 用户管理端点 ---

    def test_get_users_returns_503(self):
        r = self.client.get("/users")
        assert r.status_code == 503, f"/users 应返回 503, 实际 {r.status_code}: {r.text}"

    def test_post_users_returns_503(self):
        r = self.client.post("/users", json={"username": "x", "email": "x@x.com"})
        assert r.status_code == 503, f"POST /users 应返回 503, 实际 {r.status_code}"

    def test_get_user_by_id_returns_503(self):
        r = self.client.get("/users/some-id")
        assert r.status_code == 503

    def test_delete_user_returns_503(self):
        r = self.client.delete("/users/some-id")
        assert r.status_code == 503

    def test_get_user_stats_returns_503(self):
        r = self.client.get("/users/stats")
        assert r.status_code == 503

    # --- 团队管理端点 ---

    def test_get_teams_returns_503(self):
        r = self.client.get("/teams")
        assert r.status_code == 503

    def test_post_teams_returns_503(self):
        r = self.client.post("/teams", json={"name": "t"})
        assert r.status_code == 503

    def test_get_team_stats_returns_503(self):
        r = self.client.get("/teams/stats")
        assert r.status_code == 503

    # --- AI 端点 ---

    def test_evaluate_returns_503(self):
        r = self.client.post("/evaluate", params={"output": "a", "expected": "b"})
        assert r.status_code == 503

    def test_qa_returns_503(self):
        r = self.client.get("/qa", params={"question": "what"})
        assert r.status_code == 503

    def test_classify_returns_503(self):
        r = self.client.post("/classify", params={"text": "hello"})
        assert r.status_code == 503

    # --- 测试+诊断端点 ---

    def test_test_execute_returns_503(self):
        r = self.client.post("/test/execute", json={"test_cases": []})
        assert r.status_code == 503

    def test_test_generate_returns_503(self):
        r = self.client.post("/test/generate", json={})
        assert r.status_code == 503

    def test_diagnose_workflow_returns_503(self):
        r = self.client.post("/diagnose/workflow", json={"workflow_id": "w1"})
        assert r.status_code == 503

    # --- 503 响应体格式 ---

    def test_503_response_has_error_code(self):
        """503 响应必须包含 error_code 字段, 便于客户端区分隔离模式与其他错误。"""
        r = self.client.get("/users")
        assert r.status_code == 503
        body = r.json()
        assert body.get("success") is False
        assert "error_code" in body, "503 响应缺少 error_code 字段"
        assert body["error_code"] is not None


# ==================== 治理端点: 隔离模式下不返回 503 ====================

class TestGovernanceEndpointsNot503:
    """治理端点在隔离模式下不得返回 503(可以返回 401/200/404 等, 但不能是 503)。

    503 表示"服务不可用", 治理端点必须始终可用。
    注意: 多数治理端点需要认证, 无 token 时返回 401 — 这是正确的(不是 503)。
    """

    @pytest.fixture(autouse=True)
    def _client(self, isolated_api):
        self.client = TestClient(isolated_api.app, raise_server_exceptions=False)
        yield

    @pytest.mark.parametrize("path,method", [
        ("/health", "GET"),
        ("/metrics", "GET"),
        ("/governance/approvals", "GET"),
        ("/governance/tracker/events", "GET"),
        ("/governance/tracker/summary", "GET"),
        ("/governance/baselines", "GET"),
        ("/monitoring/alerts", "GET"),
        ("/monitoring/metrics", "GET"),
        ("/governance/execute", "POST"),
    ])
    def test_gov_endpoint_not_503(self, path, method):
        if method == "GET":
            r = self.client.get(path)
        else:
            r = self.client.post(path, params={"component_name": "test"})
        assert r.status_code != 503, (
            f"治理端点 {method} {path} 不应返回 503 — "
            f"治理核心在隔离模式下必须可用, 实际返回 {r.status_code}: {r.text}"
        )

    def test_health_returns_200(self):
        """ /health 不需要认证, 隔离模式下必须返回 200。"""
        r = self.client.get("/health")
        assert r.status_code == 200, f"/health 应返回 200, 实际 {r.status_code}"
        body = r.json()
        assert body["success"] is True


# ==================== 边界: 隔离标志的一致性 ====================

class TestIsolationFlagConsistency:
    """验证 _NON_GOV_AVAILABLE 标志在模块各处使用一致。"""

    def test_flag_consistent_with_singletons(self, isolated_api):
        """_NON_GOV_AVAILABLE=False 时, 非治理单例必须为 None, 治理单例必须非 None。"""
        assert isolated_api._NON_GOV_AVAILABLE is False

        # 非治理 → None
        assert isolated_api.user_manager is None
        assert isolated_api.team_manager is None

        # 治理 → 非 None
        assert isolated_api.orchestrator is not None
        assert isolated_api.tracker is not None

    def test_503_isolation_header(self, isolated_api):
        """503 响应建议携带隔离标记头, 便于运维排查。"""
        client = TestClient(isolated_api.app, raise_server_exceptions=False)
        r = client.get("/users")
        assert r.status_code == 503
        # 响应体中应有隔离模式标识
        body = r.json()
        assert "隔离" in body.get("message", "") or "isolation" in body.get("error_code", "").lower() or body.get("error_code") is not None
