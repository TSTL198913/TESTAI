"""/execute 主路径同步治理回退测试 (Gap 1 收敛)

背景 (代码实证):
  src/platform/api.py:1730 /execute 主路径原只调 run_test_pipeline.delay() 入队,
  broker 不可用时直接返回 TASK_SUBMISSION_FAILED, 治理闭环永不触发。
  这是 "平台叫治理但日常不治理" 的根因 — dev/无 Redis 环境治理不可达。

修复:
  /execute 改为 "异步优先 + 同步回退": delay() 成功 → queued;
  捕获 broker 不可用异常 (kombu.OperationalError / redis.ConnectionError) →
  run_test_pipeline.apply() 进程内 eager 执行任务体 (pipeline + 失败触发治理闭环)。
  apply() 运行任务体本身, 保证同步/异步走完全相同逻辑 (单一真相源), tasks.py 零改动。

严格性原则:
1. 禁止弱断言 — 不止验证 status_code, 必须验证 status/fallback/result.status 等业务字段
2. 真实治理触发测试 (TestExecuteSyncFallbackRealGovernance) 不 mock apply,
   让 apply() 真跑任务体, 断言响应含 orchestrator 治理结果 (status 字段)
3. apply 调用次数必须精确断言 (调用 1 次, 不多不少)
4. 异步路径必须验证 apply 未被调用 (不被回退污染)

变异守护: M5(删回退分支)/M6(回退不调apply) 由 _mutation_verify_tasks.py 验证捕获。
"""
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from kombu.exceptions import OperationalError


# /execute 合法请求体 (HttpRequest: step_id/description/url/method 必填)
def _execute_body(step_id: str = "exec-test-001") -> dict:
    return {
        "step_id": step_id,
        "description": "execute sync fallback test",
        "url": "http://localhost:8080/health",
        "method": "GET",
    }


# ==================== 异步优先路径 (不被回退污染) ====================

class TestExecuteAsyncPath:
    """broker 可用时必须走异步 delay, 不触发同步回退。"""

    def test_broker_available_returns_queued_and_does_not_call_apply(
        self, client, auth_headers
    ):
        """delay() 成功 → 响应 status='queued' + task_id; apply 不得被调用。

        反 fake-green: 不断言 status_code==200 即止, 必须验证 status='queued'
        且 apply.assert_not_called (证明未误入同步回退)。
        """
        fake_task = MagicMock()
        fake_task.id = "queued-task-001"

        with patch("src.platform.api.run_test_pipeline") as mock_task:
            mock_task.delay.return_value = fake_task
            r = client.post("/execute", json=_execute_body(), headers=auth_headers)

        assert r.status_code == 200, f"应 200, 实际 {r.status_code}: {r.text}"
        body = r.json()
        assert body["success"] is True
        data = body["data"]
        # 业务字段断言 (非弱断言)
        assert data["status"] == "queued", f"应 queued, 实际 {data['status']}"
        assert data["task_id"] == "queued-task-001"
        assert "trace_id" in data and data["trace_id"]
        # 关键: apply 不得被调用 (异步路径不应触发同步回退)
        mock_task.apply.assert_not_called()
        mock_task.delay.assert_called_once()

    def test_queued_response_has_no_fallback_marker(self, client, auth_headers):
        """异步路径响应不得带 fallback='sync' 标记 (该标记仅同步回退路径有)。"""
        fake_task = MagicMock(id="t2")
        with patch("src.platform.api.run_test_pipeline") as mock_task:
            mock_task.delay.return_value = fake_task
            r = client.post("/execute", json=_execute_body("exec-002"), headers=auth_headers)

        data = r.json()["data"]
        assert data.get("fallback") is None, "异步路径不应有 fallback 标记"


# ==================== 同步回退接线 (mock apply 返回值) ====================

class TestExecuteSyncFallbackWiring:
    """broker 不可用时降级 apply 同步执行 — 接线层验证。"""

    def test_broker_unavailable_triggers_sync_apply_and_returns_governance_result(
        self, client, auth_headers
    ):
        """delay 抛 OperationalError → apply 被调 → 返回 completed_sync + 治理结果。

        严格: 验证 status='completed_sync'、fallback='sync'、result.status='PENDING_APPROVAL'
        且 apply 恰好调用 1 次。
        """
        gov_result = {
            "status": "PENDING_APPROVAL",
            "confidence_score": 0.3,
            "reasoning": "mock governance result",
        }
        fake_eager = MagicMock()
        fake_eager.successful.return_value = True
        fake_eager.result = gov_result

        with patch("src.platform.api.run_test_pipeline") as mock_task:
            mock_task.delay.side_effect = OperationalError("broker unreachable")
            mock_task.apply.return_value = fake_eager
            r = client.post("/execute", json=_execute_body("exec-003"), headers=auth_headers)

        assert r.status_code == 200, f"应 200, 实际 {r.status_code}: {r.text}"
        body = r.json()
        assert body["success"] is True
        data = body["data"]
        assert data["status"] == "completed_sync", f"应 completed_sync, 实际 {data['status']}"
        assert data["fallback"] == "sync", "同步回退响应必须带 fallback='sync' 标记"
        # 治理结果原样透传 (apply 返回的 result)
        assert data["result"] == gov_result
        assert data["result"]["status"] == "PENDING_APPROVAL"
        # apply 恰好调用 1 次 (不多不少)
        mock_task.apply.assert_called_once()
        mock_task.delay.assert_called_once()

    def test_sync_fallback_propagates_failure_when_governance_also_fails(
        self, client, auth_headers
    ):
        """delay 抛异常 + apply 返回失败 (治理也失败) → EXECUTION_FAILED 响应。

        场景: pipeline 失败 → 治理也失败 → 任务体重抛原始异常 →
        /execute 包装为 EXECUTION_FAILED (非 500 崩溃)。
        """
        fake_eager = MagicMock()
        fake_eager.successful.return_value = False
        fake_eager.result = RuntimeError("pipeline + governance both failed")

        with patch("src.platform.api.run_test_pipeline") as mock_task:
            mock_task.delay.side_effect = OperationalError("broker down")
            mock_task.apply.return_value = fake_eager
            r = client.post("/execute", json=_execute_body("exec-004"), headers=auth_headers)

        body = r.json()
        assert body["success"] is False, "治理也失败时响应 success 必须为 False"
        assert body["error_code"] == "EXECUTION_FAILED", (
            f"应 EXECUTION_FAILED, 实际 {body.get('error_code')}"
        )
        assert "trace_id" in body["data"]
        mock_task.apply.assert_called_once()

    def test_non_broker_exception_returns_task_submission_failed(
        self, client, auth_headers
    ):
        """delay 抛非 broker 异常 (如 ValueError) → TASK_SUBMISSION_FAILED, 不走同步回退。

        边界: 只有 broker 不可用异常才降级, 其他异常不应误触发同步回退
        (否则会掩盖真实提交错误)。
        """
        with patch("src.platform.api.run_test_pipeline") as mock_task:
            mock_task.delay.side_effect = ValueError("not a broker error")
            r = client.post("/execute", json=_execute_body("exec-005"), headers=auth_headers)

        body = r.json()
        assert body["success"] is False
        assert body["error_code"] == "TASK_SUBMISSION_FAILED", (
            "非 broker 异常应返回 TASK_SUBMISSION_FAILED, 不应走同步回退"
        )
        # 关键: 非 broker 异常不得触发 apply (不误降级)
        mock_task.apply.assert_not_called()


# ==================== 真实治理触发 (apply 真跑任务体) ====================

class TestExecuteSyncFallbackRealGovernance:
    """[真实严格] apply() 真实运行任务体, 验证治理闭环真触发。

    不 mock apply — 让 Celery eager 执行真实 run_test_pipeline 任务体。
    mock pipeline 依赖使 pipeline 失败 → 任务体 except 分支 → _governance →
    orchestrator.execute_governance_flow。断言响应 result 含治理 status 字段,
    且 orchestrator 真实被 await (证明六步闭环触发, 非只返回错误)。

    参照 tests/worker/test_tasks.py::TestGovernanceCoroutineRealRun 的 _run_coro_side_effect 模式。
    """

    def test_sync_fallback_actually_triggers_governance_closed_loop(
        self, client, auth_headers
    ):
        """broker 不可用 → apply 真跑 → pipeline 失败 → 治理闭环触发 → 响应含治理结果。

        这是 Gap 1 的核心证明: 主路径在 broker 不可用时仍能触发治理闭环,
        而非只返回 TASK_SUBMISSION_FAILED。
        """
        gov_result_dict = {
            "status": "PENDING_APPROVAL",
            "confidence_score": 0.3,
            "reasoning": "真实同步执行后的治理分析结果",
        }

        def _run_coro_side_effect(coro):
            """真实运行传入的协程 (与 TestGovernanceCoroutineRealRun 一致)。"""
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(coro)
            finally:
                loop.close()
            fut = MagicMock()
            fut.result.return_value = result
            return fut

        # 只 patch delay (让 apply 保持真实), patch pipeline 依赖使 pipeline 失败
        with patch("src.platform.api.run_test_pipeline.delay",
                    side_effect=OperationalError("broker down")), \
             patch("src.worker.tasks.AsyncLoopManager") as mock_loop_cls, \
             patch("src.worker.tasks.set_trace_id", return_value="trace-sync-gov"), \
             patch("src.worker.tasks.reset_trace_id"), \
             patch("src.worker.tasks.GovernanceOrchestrator") as mock_orch_cls, \
             patch("src.engine.pipeline.ExecutionPipeline") as mock_pipe_cls, \
             patch("src.core.container.ResourceContainer") as mock_container_cls, \
             patch("src.engine.registry.get_pipeline", return_value=[]):

            # ResourceContainer (Mongo) — mock 使 get_client/get_repo 不真连
            mock_client = MagicMock()
            mock_repo = MagicMock()
            mock_repo.save_execution = AsyncMock()
            mock_container_cls.get_client = AsyncMock(return_value=mock_client)
            mock_container_cls.get_repo = AsyncMock(return_value=mock_repo)

            # ExecutionPipeline.run 抛错 → _execute 真实执行到抛错 → 触发 _governance
            mock_pipe_inst = MagicMock()
            mock_pipe_inst.run = AsyncMock(
                side_effect=RuntimeError("pipeline 失败 → 触发治理闭环")
            )
            mock_pipe_cls.return_value = mock_pipe_inst

            # GovernanceOrchestrator.execute_governance_flow → 返回治理结果 dict
            mock_orch_inst = MagicMock()
            mock_orch_inst.execute_governance_flow = AsyncMock(return_value=gov_result_dict)
            mock_orch_cls.return_value = mock_orch_inst

            # AsyncLoopManager.run_coroutine → 真实执行传入的协程
            mock_loop_cls.run_coroutine.side_effect = _run_coro_side_effect

            r = client.post(
                "/execute", json=_execute_body("exec-real-gov-001"), headers=auth_headers
            )

        # ====== 严格真实断言 ======
        assert r.status_code == 200, f"/execute 应 200, 实际 {r.status_code}: {r.text}"
        body = r.json()
        assert body["success"] is True
        data = body["data"]
        # 走了同步回退
        assert data["status"] == "completed_sync", (
            f"应 completed_sync (broker 不可用降级), 实际 {data['status']}"
        )
        assert data["fallback"] == "sync"
        # 核心证明: result 含治理 status 字段 → 治理闭环真触发 (非只返回错误)
        result = data["result"]
        assert isinstance(result, dict), f"result 应是治理 dict, 实际: {type(result)}"
        assert "status" in result, (
            f"result 缺 'status' 字段 — 治理闭环未触发, 实际字段: {list(result.keys())}"
        )
        assert result["status"] == "PENDING_APPROVAL"
        # orchestrator 真实被 await (证明 _governance 走了 orchestrator 六步闭环)
        mock_orch_inst.execute_governance_flow.assert_awaited_once()
        # pipeline 真实执行并失败 (证明 _execute 真跑了, 非空跳过)
        mock_pipe_inst.run.assert_awaited_once()
        # run_coroutine 调用 2 次 (_execute + _governance)
        assert mock_loop_cls.run_coroutine.call_count == 2, (
            "run_coroutine 应调用 2 次 (_execute + _governance), "
            f"实际 {mock_loop_cls.run_coroutine.call_count}"
        )
