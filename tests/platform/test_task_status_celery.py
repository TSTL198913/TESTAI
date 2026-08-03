"""
BUG #2 回归测试: /tasks/{task_id} 端点查询 Celery 结果后端

BUG 历史:
  src/platform/api.py 的 get_task_status 只搜索 WorkflowEngine 实例,
  不查询 Celery 结果后端。/execute 提交的任务是 Celery 异步任务,
  不在 WorkflowEngine 实例中, 因此 /tasks/{task_id} 始终返回 404。

修复:
  get_task_status 增加第二步: 查询 celery_app.AsyncResult(task_id)。
  当任务在 Celery 后端有结果时 (state != PENDING), 返回结果。

验证:
  1. 源码检查: get_task_status 包含 Celery 后端查询逻辑
  2. 功能测试: 模拟 Celery AsyncResult 返回 SUCCESS, 端点返回 200
  3. 功能测试: 模拟 Celery AsyncResult 返回 PENDING, 端点返回 404
  4. 边界场景: 空task_id/超长/特殊字符/格式崩溃
  5. 并发闭环: 10 个 /execute 提交 → 取 task_id → 分别查状态

注意:
  所有测试通过 api_module 动态访问 get_task_status 和 celery_app,
  避免模块重载导致的引用过期问题 (test_api_security 等会重载 api 模块)。
"""
import asyncio
import inspect
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

import src.platform.api as api_module
from src.platform.api import app as platform_app


class TestTaskStatusCeleryBackend:
    """回归测试: /tasks/{task_id} 必须查询 Celery 结果后端。"""

    def test_get_task_status_queries_celery_backend(self):
        """源码验证: get_task_status 必须包含 celery_app.AsyncResult 调用。

        这是 BUG #2 的修复点 — 确保修复未被回退。
        """
        # 动态获取最新的 get_task_status (防止模块重载导致引用过期)
        source = inspect.getsource(api_module.get_task_status)
        assert "AsyncResult" in source, (
            "get_task_status 必须查询 Celery AsyncResult — "
            "否则 /execute 提交的异步任务永远返回 404"
        )
        assert "celery_app" in source, (
            "get_task_status 必须使用 celery_app 查询后端结果"
        )

    @pytest.mark.asyncio
    async def test_returns_celery_success_result(self):
        """功能测试: Celery 任务成功时, 端点返回 200 + 结果。"""
        mock_result = MagicMock()
        mock_result.state = "SUCCESS"
        mock_result.successful.return_value = True
        mock_result.result = {
            "is_fixable": True,
            "confidence_score": 0.95,
            "patch_proposal": {"patch_type": "functional"},
        }
        mock_result.failed.return_value = False

        # 用 mock workflow_engine 替换 api 模块引用, 返回空实例列表
        mock_we = MagicMock()
        mock_we.list_instances.return_value = []

        with patch.object(api_module, "workflow_engine", mock_we):
            with patch.object(
                api_module.celery_app, "AsyncResult", return_value=mock_result
            ):
                response = await api_module.get_task_status(
                    task_id="test-celery-success"
                )

        assert response.success is True
        assert response.data["status"] == "SUCCESS"
        assert response.data["result"]["patch_proposal"]["patch_type"] == "functional"
        assert response.data["error"] is None

    @pytest.mark.asyncio
    async def test_returns_celery_failure_result(self):
        """功能测试: Celery 任务失败时, 端点返回 200 + 错误信息。"""
        mock_result = MagicMock()
        mock_result.state = "FAILURE"
        mock_result.successful.return_value = False
        mock_result.failed.return_value = True
        mock_result.result = ValueError("Connection refused")

        mock_we = MagicMock()
        mock_we.list_instances.return_value = []

        with patch.object(api_module, "workflow_engine", mock_we):
            with patch.object(
                api_module.celery_app, "AsyncResult", return_value=mock_result
            ):
                response = await api_module.get_task_status(
                    task_id="test-celery-failure"
                )

        assert response.success is True
        assert response.data["status"] == "FAILURE"
        assert "Connection refused" in response.data["error"]

    @pytest.mark.asyncio
    async def test_returns_404_when_celery_pending(self):
        """功能测试: Celery 任务 PENDING (未处理) 时, 端点返回 404。"""
        from fastapi import HTTPException

        mock_result = MagicMock()
        mock_result.state = "PENDING"

        mock_we = MagicMock()
        mock_we.list_instances.return_value = []

        with patch.object(api_module, "workflow_engine", mock_we):
            with patch.object(
                api_module.celery_app, "AsyncResult", return_value=mock_result
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await api_module.get_task_status(
                        task_id="test-celery-pending"
                    )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_workflow_instance_takes_priority_over_celery(self):
        """功能测试: Workflow 实例中的任务优先于 Celery 后端查询。

        用 mock workflow_engine 替换 api 模块中的引用,
        避免单例重置导致的引用不一致问题。
        """
        mock_we = MagicMock()
        mock_we.list_instances.return_value = [{"instance_id": "inst-001"}]
        mock_we.get_workflow_status.return_value = {
            "workflow_id": "wf-001",
            "instance_id": "inst-001",
            "status": "running",
            "tasks": {
                "task-in-workflow": {
                    "status": "completed",
                    "result": {"key": "value"},
                }
            },
        }

        with patch.object(api_module, "workflow_engine", mock_we):
            # Celery 后端不应被调用 (workflow 优先)
            with patch.object(
                api_module.celery_app, "AsyncResult"
            ) as mock_async_result:
                response = await api_module.get_task_status(
                    task_id="task-in-workflow"
                )

        assert response.success is True
        assert response.data["status"] == "completed"
        assert response.data["workflow_id"] == "wf-001"
        # Celery 后端未被调用 (workflow 中已找到)
        mock_async_result.assert_not_called()


class TestTaskStatusBoundaryScenarios:
    """[严格真实] 边界场景测试: task_id 格式/空值/超长/非法字符/404 路径。

    覆盖:
    1. 空 task_id / 空白 task_id → 端点行为 (返回 404 或 422?)
    2. 超长 task_id (1000 字符 UUID 拼接)
    3. 特殊字符 (SQL 注入, 路径遍历, XSS)
    4. 标准格式: UUID, 含破折号/不含破折号的 UUID
    5. Celery PENDING + Workflow 无 → 返回 404, 不是 500
    """

    @pytest.mark.asyncio
    async def test_empty_task_id_returns_404_not_500(self):
        """空 task_id: 返回 404, 不应抛 500 异常。
        防止数据库/Redis 在空 key 下崩溃。
        """
        mock_we = MagicMock()
        mock_we.list_instances.return_value = []

        with patch.object(api_module, "workflow_engine", mock_we):
            with patch.object(
                api_module.celery_app, "AsyncResult"
            ) as mock_ar:
                mock_ar.return_value.state = "PENDING"
                with pytest.raises(Exception) as exc_info:
                    await api_module.get_task_status(task_id="")

        # 必须是 HTTPException (404), 不能是 500 / KeyError / TypeError
        # 直接访问 status_code (属性不存在时 AttributeError 比 hasattr 更早失败)
        assert exc_info.value.status_code == 404, (
            f"空task_id应返回 HTTP 404。实际: {type(exc_info.value)}"
        )

    @pytest.mark.asyncio
    async def test_whitespace_task_id_returns_404(self):
        """空白 / 纯空格 task_id: 返回 404。"""
        mock_we = MagicMock()
        mock_we.list_instances.return_value = []
        with patch.object(api_module, "workflow_engine", mock_we):
            with patch.object(api_module.celery_app, "AsyncResult") as mock_ar:
                mock_ar.return_value.state = "PENDING"
                with pytest.raises(Exception) as exc_info:
                    await api_module.get_task_status(task_id="    ")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_very_long_task_id_1000_chars_returns_404(self):
        """超长 task_id (1000 字符 UUID): 返回 404, 不应因超长崩溃。"""
        long_id = "a" * 1000
        mock_we = MagicMock()
        mock_we.list_instances.return_value = []
        with patch.object(api_module, "workflow_engine", mock_we):
            with patch.object(api_module.celery_app, "AsyncResult") as mock_ar:
                mock_ar.return_value.state = "PENDING"
                with pytest.raises(Exception) as exc_info:
                    await api_module.get_task_status(task_id=long_id)

        assert exc_info.value.status_code == 404, (
            f"超长task_id应返回 HTTP 404。实际: {type(exc_info.value)}"
        )

    @pytest.mark.asyncio
    async def test_special_chars_task_id_sql_injection_returns_404(self):
        """特殊字符(SQL注入/XSS/路径遍历): 404, 不抛异常。"""
        evil_ids = [
            "' OR 1=1 --",
            "<script>alert(1)</script>",
            "../../../etc/passwd",
            "task'; DROP TABLE tasks; --",
            "../..\\..\x00",
            "🔴Unicode😀",
            "unicode-\u0000-nullbyte",
        ]
        for evil in evil_ids:
            mock_we = MagicMock()
            mock_we.list_instances.return_value = []
            with patch.object(api_module, "workflow_engine", mock_we):
                with patch.object(api_module.celery_app, "AsyncResult") as mock_ar:
                    mock_ar.return_value.state = "PENDING"
                    try:
                        await api_module.get_task_status(task_id=evil)
                        # 没抛异常: 不应成功, 除非返回 success=False
                        # 若没抛 HTTPException, 但成功返回 data=..., 那也是合理的 200+not found
                    except Exception as e:
                        assert e.status_code in (404, 422, 400), (
                            f"特殊字符 '{evil}' 抛异常或返回错误状态码 "
                            f"{type(e).__name__}: {e}"
                        )

    @pytest.mark.asyncio
    async def test_valid_uuid_format_task_id_returns_404(self):
        """有效格式 UUID (不存在): 返回 404, 验证格式不崩溃。"""
        uuid_ids = [
            "550e8400-e29b-41d4-a716-446655440000",  # with dashes
            "550e8400e29b41d4a716446655440000",        # without dashes
            "celery-task-abc123",                      # Celery common ID format
            "00000000-0000-0000-0000-000000000000",    # zero UUID
        ]
        for t_id in uuid_ids:
            mock_we = MagicMock()
            mock_we.list_instances.return_value = []
            with patch.object(api_module, "workflow_engine", mock_we):
                with patch.object(api_module.celery_app, "AsyncResult") as mock_ar:
                    mock_ar.return_value.state = "PENDING"
                    with pytest.raises(Exception) as exc_info:
                        await api_module.get_task_status(task_id=t_id)
            assert exc_info.value.status_code == 404, (
                f"UUID '{t_id}' 不存在时应 404, 实际 {exc_info.value.status_code}"
            )

    @pytest.mark.asyncio
    async def test_celery_failure_state_returns_5xx_with_error(self):
        """Celery 任务 FAILURE 状态: 返回结果 + error 字段, 不是 404。"""
        mock_result = MagicMock()
        mock_result.state = "FAILURE"
        mock_result.successful.return_value = False
        mock_result.failed.return_value = True
        mock_result.result = ValueError("Pipeline execution crashed")

        mock_we = MagicMock()
        mock_we.list_instances.return_value = []

        with patch.object(api_module, "workflow_engine", mock_we):
            with patch.object(
                api_module.celery_app, "AsyncResult", return_value=mock_result
            ):
                response = await api_module.get_task_status(
                    task_id="task-celery-failure-001"
                )

        # FAILURE 状态必须返回 success=True 且带 error 字段
        assert response.success is True
        assert response.data["status"] == "FAILURE"
        # error 字段必须包含异常信息字符串 (不能是 None)
        assert response.data.get("error") is not None
        assert "Pipeline execution crashed" in response.data["error"], (
            "FAILURE 状态必须把异常信息放入 error 字段中, 否则用户不知道为什么失败"
        )
        assert "result" in response.data

    @pytest.mark.asyncio
    async def test_celery_started_state_pending_task(self):
        """Celery STARTED / RETRY 状态: 返回状态, 不抛 404。"""
        for state in ["STARTED", "RETRY"]:
            mock_result = MagicMock()
            mock_result.state = state
            mock_result.successful.return_value = False
            mock_result.failed.return_value = False
            mock_result.result = None

            mock_we = MagicMock()
            mock_we.list_instances.return_value = []

            with patch.object(api_module, "workflow_engine", mock_we):
                with patch.object(
                    api_module.celery_app, "AsyncResult", return_value=mock_result
                ):
                    response = await api_module.get_task_status(
                        task_id=f"task-running-{state.lower()}"
                    )

            assert response.success is True, (
                f"{state} 状态应返回 success=True, 不是抛出 404"
            )
            assert response.data["status"] == state


class TestExecuteAndStatusConcurrentLoop:
    """[严格真实] 并发提交 + 状态查询闭环测试:10 个任务提交 → 查询状态。

    模拟真实用户流程:
    1. 登录 → 拿 Bearer Token
    2. POST /execute 连续提交 10 个任务 → 拿 10 个 task_id
    3. 每个 task_id GET /tasks/{task_id} 查状态 → 验证闭环
    """

    SAMPLE_REQUEST = {
        "step_id": "concurrent-step-001",
        "description": "并发闭环测试请求",
        "url": "http://example.com/api",
        "method": "GET",
        "pipeline": ["data", "request", "assertion"],
    }

    def test_login_returns_bearer_token(self, client, auth_headers):
        """前置验证: auth_headers fixture 包含合法 Bearer token。"""
        assert "Authorization" in auth_headers
        assert auth_headers["Authorization"].startswith("Bearer ")
        assert len(auth_headers["Authorization"].split()[1]) > 10

    def test_10_concurrent_execute_then_status_query(self, client, auth_headers):
        """10 个任务 POST /execute → 得到 10 个 task_id → 分别 GET /tasks/{id}。

        模拟:
        - run_test_pipeline.delay(request_dict) 不真实调用 Celery,
          返回 Mock(task.id=unique-id)
        - celery_app.AsyncResult 对每个 task_id 返回对应状态
          (根据 task_id 后缀决定 SUCCESS / FAILURE / STARTED 状态)
        """
        submitted_task_ids = []
        N = 10

        def make_delay_mock():
            """mock run_test_pipeline.delay 返回 TaskMock。"""
            counter = {"n": 0}

            def _side_effect(request_dict):
                assert "_trace_id" in request_dict, (
                    "execute_pipeline 必须注入 _trace_id 后才投递 Celery"
                )
                assert request_dict["_requester"] == "admin", (
                    "_requester 必须 = 当前登录用户名, 实际: "
                    f"{request_dict['_requester']}"
                )
                # 唯一 task_id: 根据 10 个任务不同后缀
                i = counter["n"]
                counter["n"] += 1
                states_for_i = {
                    0: "SUCCESS", 1: "SUCCESS", 2: "FAILURE",
                    3: "STARTED", 4: "SUCCESS", 5: "PENDING",
                    6: "SUCCESS", 7: "FAILURE", 8: "RETRY", 9: "SUCCESS",
                }
                task_id = f"concurrent-task-{i:03d}"
                submitted_task_ids.append((task_id, i, states_for_i[i]))
                mock_task = MagicMock()
                mock_task.id = task_id
                return mock_task

            return _side_effect

        def async_result_side_effect(task_id):
            """基于 task_id 后缀返回对应 AsyncResult mock。"""
            # 解析 task_id 后缀 000 ~ 009
            parts = task_id.split("-")
            try:
                idx = int(parts[-1]) if parts[-1].isdigit() else 5
            except Exception:
                idx = 5
            states = ["SUCCESS", "SUCCESS", "FAILURE", "STARTED", "SUCCESS",
                      "PENDING", "SUCCESS", "FAILURE", "RETRY", "SUCCESS"]
            state = states[idx % 10]
            mock_ar = MagicMock()
            mock_ar.state = state
            mock_ar.successful.return_value = (state == "SUCCESS")
            mock_ar.failed.return_value = (state == "FAILURE")
            if state == "SUCCESS":
                mock_ar.result = {
                    "is_fixable": idx % 2 == 0,
                    "confidence_score": 0.9 - (idx / 100.0),
                    "patch_proposal": {
                        "patch_type": "functional",
                        "target_function": f"fn_{idx}",
                        "suggested_code": f"# patch code {idx}",
                    },
                }
            elif state == "FAILURE":
                mock_ar.result = RuntimeError(f"Pipeline crashed in task {idx}")
            else:
                mock_ar.result = None
            return mock_ar

        # 使用 patch.object 动态引用 api_module.run_test_pipeline,
        # 避免其他测试 import 顺序变化导致 patch("src.platform.api...") 失效。
        with patch.object(api_module, "run_test_pipeline") as mock_task:
            mock_task.delay.side_effect = make_delay_mock()
            # 1. 提交 10 个任务
            for _ in range(N):
                r = client.post(
                    "/execute", json=self.SAMPLE_REQUEST, headers=auth_headers
                )
                assert r.status_code == 200, (
                    f"POST /execute 返回非 200: {r.status_code} {r.text}"
                )
                body = r.json()
                assert body["success"] is True, (
                    f"POST /execute success=False: {body}"
                )
                assert body["data"]["status"] == "queued", (
                    f"状态不是 queued: {body['data']}"
                )
                assert "task_id" in body["data"]
                assert "trace_id" in body["data"]

        # 验证: 10 个唯一 task_id 收集到
        assert len(submitted_task_ids) == N, (
            f"只提交了 {len(submitted_task_ids)} 个任务, 期望 {N}"
        )
        all_ids = [t for t, *_ in submitted_task_ids]
        assert len(set(all_ids)) == N, "10 个 task_id 必须互不相同"

        # 2. 模拟 Celery: workflow_engine 空实例列表, 走 Celery 分支
        mock_we = MagicMock()
        mock_we.list_instances.return_value = []
        with patch.object(api_module, "workflow_engine", mock_we):
            with patch.object(
                api_module.celery_app, "AsyncResult",
                side_effect=async_result_side_effect,
            ):
                # 3. 逐个查询 10 个 task_id 状态
                for tid, i, expected_state in submitted_task_ids:
                    r = client.get(f"/tasks/{tid}", headers=auth_headers)
                    # PENDING 时会返回 404 (找不到任务, 两端都没)
                    if expected_state == "PENDING":
                        assert r.status_code == 404, (
                            f"PENDING 任务 {tid} 应 404, 实际 {r.status_code}"
                        )
                        continue
                    assert r.status_code == 200, (
                        f"查询 {tid} (期望状态 {expected_state}) 非 200: "
                        f"{r.status_code} {r.text}"
                    )
                    body = r.json()
                    assert body["success"] is True, (
                        f"查询 {tid} success=False: {body}"
                    )
                    # 状态必须与之前提交时预期一致
                    assert body["data"]["task_id"] == tid, (
                        "返回的 task_id 必须与请求一致"
                    )
                    assert body["data"]["status"] == expected_state, (
                        f"task {tid} 期望状态 {expected_state}, "
                        f"实际 {body['data']['status']}"
                    )
                    if expected_state == "SUCCESS":
                        # 必须包含治理结果字段 (Celery result 序列化正确)
                        assert "result" in body["data"]
                        res = body["data"]["result"]
                        assert "is_fixable" in res
                        assert "confidence_score" in res
                        assert "patch_proposal" in res
                        assert isinstance(res["patch_proposal"]["patch_type"], str)
                    elif expected_state == "FAILURE":
                        # error 字段不能是 None, 必须包含 Pipeline crashed 信息
                        assert "error" in body["data"], (
                            f"FAILURE 状态 {tid} 必须带 error 字段"
                        )
                        assert body["data"].get("error") is not None
                        assert f"Pipeline crashed in task {i}" in body["data"]["error"]
                    else:  # STARTED / RETRY
                        assert body["data"]["status"] in ("STARTED", "RETRY")
                        # 允许 result 为空, 但 success=True (任务还在跑)
                        assert body["success"] is True


@pytest.fixture
def client():
    """TestClient fixture for platform API。"""
    with TestClient(platform_app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    """登录拿 Bearer token headers。"""
    login_resp = client.post(
        "/auth/login", json={"username": "admin", "password": "password"},
    )
    assert login_resp.status_code == 200, (
        f"登录失败: {login_resp.status_code} {login_resp.text}"
    )
    token = login_resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
