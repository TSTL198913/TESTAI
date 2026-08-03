"""
P0-RUN-TEST: 真实运行验证测试

启动 uvicorn 服务并实际调用端点，验证功能真实可用。
这不是 mock 测试，而是真正的 HTTP 请求测试。

Windows 健壮性修复 (防止端口泄漏导致后续运行 "Failed to start API server"):
  1. 启动前先探测 8788 是否已有健康服务 → 复用, 不重复启动, 不在 teardown 杀掉它
  2. 启动时用 CREATE_NEW_PROCESS_GROUP 创建独立进程组
  3. teardown 用 taskkill /F /T 杀整个进程树 (uvicorn 会派生子进程,
     SIGTERM 在 Windows 上只杀父进程, 子进程泄漏占住端口)
"""
import time
import uuid
import logging
import pytest
import requests
import subprocess
import os
import atexit


logger = logging.getLogger(__name__)

BASE_URL = "http://127.0.0.1:8788"
SECRET_KEY = "this-is-a-very-long-secret-key-for-testing-32bytes-minimum"
_process = None
_we_started = False  # 标记是否由本模块启动 (复用外部服务时为 False, 不负责停止)


def _is_server_healthy():
    """探测 8788 端口是否已有健康服务 (避免端口冲突导致的启动失败)。"""
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=1)
        return resp.status_code == 200
    except Exception:
        return False


def _kill_process_tree(pid):
    """Windows 健壮终止: taskkill /F /T 杀整个进程树。

    subprocess.Popen.kill() / SIGTERM 在 Windows 上只终止父进程,
    uvicorn 的 reload/worker 子进程会存活并继续占用端口,
    导致下次运行 "Failed to start API server"。taskkill /T 递归杀子进程。
    """
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, timeout=5,
        )
    except Exception as e:
        # 兜底: 直接 kill 父进程 (至少释放父进程)
        logger.warning(f"taskkill 失败, 尝试 os.kill 兜底: {type(e).__name__}: {e}")
        try:
            os.kill(pid, 9)
        except Exception as e2:
            # 兜底也失败: 记录日志 (禁止静默 pass — 进程泄漏会导致后续端口冲突)
            logger.warning(
                f"os.kill 兜底也失败, 进程 {pid} 可能仍存活: {type(e2).__name__}: {e2}"
            )


def _start_server():
    global _process, _we_started

    # 1. 若已有健康服务 (如 CI 预启动或上一轮泄漏), 直接复用, 不重复启动
    if _is_server_healthy():
        _we_started = False
        return True

    # 2. 启动新服务
    env = os.environ.copy()
    env["SECRET_KEY"] = SECRET_KEY
    env["MONGO_URI"] = "mongodb://localhost:27017/testai_test"

    _process = subprocess.Popen(
        ["python", "-m", "uvicorn", "src.platform.api:app",
         "--host", "127.0.0.1", "--port", "8788"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # Windows: 独立进程组, 便于整组终止; POSIX 无此 flag 时忽略
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    # 注册 atexit 兜底: 即使 fixture teardown 未执行 (如 SIGINT), 也尝试清理
    atexit.register(_cleanup_on_exit)

    for _ in range(30):
        if _is_server_healthy():
            _we_started = True
            return True
        time.sleep(0.5)
    return False


def _cleanup_on_exit():
    """atexit 兜底清理, 防止任何路径下进程泄漏。"""
    global _process, _we_started
    if _process and _we_started:
        _kill_process_tree(_process.pid)
    _process = None
    _we_started = False


def _stop_server():
    """teardown: 仅停止本模块启动的服务 (复用的外部服务不停止)。"""
    global _process, _we_started
    if _process and _we_started:
        _kill_process_tree(_process.pid)
    _process = None
    _we_started = False


@pytest.fixture(scope="module", autouse=True)
def live_server():
    assert _start_server(), (
        f"Failed to start API server on {BASE_URL} — "
        "若端口 8788 被泄漏进程占用, 请先清理: "
        "Get-NetTCPConnection -LocalPort 8788 | Select OwningProcess | Stop-Process -Force"
    )
    yield
    _stop_server()


class TestRealHealthEndpoint:
    def test_health_returns_200(self):
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["data"]["status"] == "healthy"
        assert data["data"]["version"] == "1.0.0"

    def test_health_has_governance_status(self):
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        data = r.json()
        assert "governance_status" in data["data"]


class TestRealMetricsEndpoint:
    def test_metrics_returns_prometheus_format(self):
        r = requests.get(f"{BASE_URL}/metrics", timeout=5)
        assert r.status_code == 200
        assert "python_" in r.text or "process_" in r.text
        assert "text/plain" in r.headers.get("content-type", "") or "text/" in r.headers.get("content-type", "")


class TestRealAuthFlow:
    def test_login_returns_tokens(self):
        r = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "password"},
            timeout=5,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert len(data["data"]["access_token"]) > 100
        assert "refresh_token" in data["data"]


class TestRealExecuteEndpoint:
    def test_execute_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/execute",
            json={"step_id": "test-001", "url": "http://localhost:9999", "method": "GET"},
            timeout=5,
        )
        assert r.status_code in (401, 403)

    def test_execute_with_auth_returns_queued(self):
        login_r = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "password"},
            timeout=5,
        )
        token = login_r.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = requests.post(
            f"{BASE_URL}/execute",
            json={
                "step_id": f"real-test-{uuid.uuid4().hex[:8]}",
                "description": "Real pipeline test",
                "url": "http://localhost:9999/health",
                "method": "GET",
            },
            headers=headers,
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["data"]["status"] == "queued"
        assert "task_id" in data["data"]
        assert len(data["data"]["task_id"]) > 0
        assert "trace_id" in data["data"]

    def test_execute_with_auth_has_trace_id(self):
        login_r = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "password"},
            timeout=5,
        )
        token = login_r.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = requests.post(
            f"{BASE_URL}/execute",
            json={
                "step_id": f"trace-test-{uuid.uuid4().hex[:8]}",
                "description": "Trace ID verification",
                "url": "http://localhost:9999/health",
                "method": "GET",
            },
            headers=headers,
            timeout=10,
        )
        data = r.json()
        trace_id = data["data"]["trace_id"]
        assert len(trace_id) == 8
        assert trace_id.isalnum()


class TestRealBaselinesEndpoint:
    def test_baselines_requires_auth(self):
        r = requests.get(f"{BASE_URL}/governance/baselines", timeout=5)
        assert r.status_code in (401, 403)

    def test_baselines_with_auth_returns_list(self):
        login_r = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "password"},
            timeout=5,
        )
        token = login_r.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = requests.get(f"{BASE_URL}/governance/baselines", headers=headers, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "data" in data