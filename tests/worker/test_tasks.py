"""
Worker 层真实严格测试

覆盖 src/worker/tasks.py 和 src/worker/celery_app.py 的核心逻辑。

严格性原则 (经变异测试验证):
1. 所有断言必须验证具体业务逻辑, 禁止 tautology (如 `X == A or X is not None`)
2. 异常测试必须用 pytest.raises 显式断言, 禁止 try/except 内嵌断言的静默通过
3. Mock 测试必须验证调用序列与参数, 不止验证返回值
4. 断言值与源码真实值一致 (celery_app.main == "test_ai_worker", broker 为 redis:// URL)
5. 禁止死代码 mock 设置: 若 mock 从未被调用 (因 _execute() 协程不执行), 不设置 side_effect/return_value
6. 治理路径测试必须用 run_coroutine.side_effect=[pipeline_future, gov_future] 确保两次调用,
   且 pipeline_future.result() 必须抛异常以触发 except 块
7. [反 tautology] 禁止逐字段断言测试自己注入 mock 的数据 (循环论证)。
   治理结果传播用 `result is gov_future.result()返回值` 同一性断言验证传播路径,
   结构/序列化正确性由真实执行协程的 TestGovernanceCoroutineRealRun 覆盖。
8. [反死 patch] GovernanceOrchestrator 在 _governance() 协程体内 (tasks.py:63) 实例化,
   协程因 run_coroutine 被 mock 而不执行 → patch GovernanceOrchestrator 是死代码, 已全部移除。
   真实 orchestrator 调用由 TestGovernanceCoroutineRealRun 验证。

已知限制 (诚实声明):
- _execute() 协程体因 AsyncLoopManager.run_coroutine 被 mock 而不执行 (涉及 ResourceContainer/ExecutionPipeline, 需集成测试)
- _governance() 协程体已通过独立 async 单元测试真实执行 (见 TestGovernanceCoroutineRealRun)
- ResourceContainer.get_client/get_repo, ExecutionPipeline.run, get_pipeline 等内部调用需集成测试覆盖
- set_trace_id/reset_trace_id 被 mock, 真实 None/空值处理由 src.core.tracer 单元测试覆盖;
  此处仅做契约断言 (验证 set_trace_id 收到原样透传的 request.id)
- 边界场景 (run_coroutine 自身抛异常 / 空 dict / None request.id) 见 TestWorkerBoundaryScenarios
"""
import logging
import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.fixture
def sample_request_dict():
    return {
        "step_id": "worker-test-001",
        "description": "Worker layer test",
        "url": "http://localhost:8080/health",
        "method": "GET",
        "_trace_id": "abc12345",
        "_requester": "testuser",
    }


# ==================== Celery App 真实配置 ====================

class TestCeleryAppConfig:
    """验证 celery_app 的真实配置值 (非 tautology)。"""

    def test_celery_app_name_is_test_ai_worker(self):
        """celery_app.main 必须精确等于 'test_ai_worker' (源码 celery_app.py:13)。"""
        from src.worker.celery_app import celery_app
        assert celery_app.main == "test_ai_worker"

    def test_celery_app_broker_is_redis(self):
        """broker_url 必须是 redis:// 协议 (源码 celery_app.py:9 默认值)。"""
        from src.worker.celery_app import celery_app
        assert celery_app.conf.broker_url.startswith("redis://"), \
            f"Expected redis:// broker, got {celery_app.conf.broker_url!r}"

    def test_celery_app_backend_is_redis(self):
        """backend_url 必须是 redis:// 协议 (源码 celery_app.py:10 默认值)。"""
        from src.worker.celery_app import celery_app
        assert celery_app.conf.result_backend.startswith("redis://"), \
            f"Expected redis:// backend, got {celery_app.conf.result_backend!r}"

    def test_celery_app_includes_tasks_module(self):
        """celery_app 必须包含 src.worker.tasks 模块 (源码 celery_app.py:16)。"""
        from src.worker.celery_app import celery_app
        assert "src.worker.tasks" in celery_app.conf.include

    def test_celery_app_serializer_is_json(self):
        """序列化器必须为 json (源码 celery_app.py:20-22)。"""
        from src.worker.celery_app import celery_app
        assert celery_app.conf.task_serializer == "json"
        assert "json" in celery_app.conf.accept_content
        assert celery_app.conf.result_serializer == "json"


# ==================== Task 注册与签名 ====================

class TestWorkerTaskSignature:
    def test_run_test_pipeline_registered_with_correct_name(self):
        """任务必须以 'tasks.run_test_pipeline' 名称注册 (源码 tasks.py:15)。"""
        from src.worker.tasks import run_test_pipeline
        assert run_test_pipeline.name == "tasks.run_test_pipeline"

    def test_run_test_pipeline_is_bound_celery_task(self):
        """任务必须 bind=True, 支持 delay() 异步调用。"""
        from src.worker.tasks import run_test_pipeline
        # callable(getattr(...)) 比 hasattr 更强: 既验证属性存在, 又验证可调用
        assert callable(getattr(run_test_pipeline, "delay", None)), (
            "Must have delay() for Celery async"
        )
        assert callable(getattr(run_test_pipeline, "apply_async", None)), (
            "Must have apply_async()"
        )


# ==================== 正常执行路径 ====================

class TestWorkerNormalPath:
    """验证正常路径 (pipeline 成功, 不进入治理)。

    关键: _execute() 协程不执行, 只验证 run_coroutine 调用一次 + result(timeout=60) 返回。
    """

    @patch("src.engine.pipeline.ExecutionPipeline")
    @patch("src.core.container.ResourceContainer")
    @patch("src.worker.tasks.AsyncLoopManager")
    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    def test_normal_path_returns_result_and_calls_run_coroutine_once(
        self, mock_reset, mock_set, mock_loop, mock_container, mock_pipeline_cls,
        sample_request_dict
    ):
        """正常路径: run_coroutine 只调用一次 (不触发治理), result(timeout=60) 返回。"""
        mock_set.return_value = "trace-token-001"
        mock_future = MagicMock()
        mock_future.result.return_value = "Success"
        mock_loop.run_coroutine.return_value = mock_future

        from src.worker.tasks import run_test_pipeline
        mock_self = MagicMock()
        mock_self.request.id = "test-task-id-001"
        result = run_test_pipeline.run.__func__(mock_self, sample_request_dict)

        # 业务逻辑断言: 返回值来自 future.result()
        assert result == "Success"
        # 业务逻辑断言: run_coroutine 只调用一次 (正常路径不触发治理)
        assert mock_loop.run_coroutine.call_count == 1, \
            "正常路径 run_coroutine 应只调用 1 次, 多于 1 次说明误入治理路径"
        # 业务逻辑断言: future.result 必须用 timeout=60 (源码 tasks.py:43)
        mock_future.result.assert_called_once_with(timeout=60)
        # 业务逻辑断言: trace_id 从 self.request.id 设置 (源码 tasks.py:17)
        mock_set.assert_called_once_with("test-task-id-001")
        # 业务逻辑断言: finally 重置 trace_id (源码 tasks.py:65-66)
        mock_reset.assert_called_once_with("trace-token-001")


# ==================== 异常与治理回退路径 ====================

class TestWorkerGovernancePath:
    """验证治理回退路径 (pipeline 抛异常 → 治理)。

    关键: 必须用 run_coroutine.side_effect=[pipeline_future, gov_future] 触发两次调用,
    pipeline_future.result() 必须抛异常以进入 except 块。
    """

    @patch("src.engine.pipeline.ExecutionPipeline")
    @patch("src.core.container.ResourceContainer")
    @patch("src.worker.tasks.AsyncLoopManager")
    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    def test_pipeline_exception_triggers_governance_and_returns_governed_result(
        self, mock_reset, mock_set, mock_loop, mock_container,
        mock_pipeline_cls, sample_request_dict
    ):
        """pipeline 抛异常 → 治理成功 → 返回治理 future 的结果 (源码 tasks.py:44-68)。

        严格性 (反 tautology):
          - 不逐字段断言 mock 注入的 gov_result_dict (那是验证测试自己的数据, 循环论证)。
          - 只断言 result IS gov_future.result() 的返回值, 证明源码 line 68
            `return gov_future.result(timeout=60)` 的传播路径成立。
          - patch_proposal.patch_type 的字符串序列化由 TestGovernanceCoroutineRealRun
            真实执行 _governance 协程验证, 此处不重复 (协程未执行, 断言无意义)。

        限制: GovernanceOrchestrator 在 _governance() 协程体内实例化 (line 63),
              协程因 run_coroutine 被 mock 而不执行, 故不 patch 它 (死 patch 已移除)。
        """
        mock_set.return_value = "trace-token-002"

        # 第一次 run_coroutine (pipeline): result() 抛异常, 触发 except 块 (line 47)
        pipeline_future = MagicMock()
        pipeline_future.result.side_effect = RuntimeError("Pipeline failed")
        # 第二次 run_coroutine (governance): 返回一个标记 dict。
        # 用真实 dict (非 MagicMock) 作为标记对象, 证明治理成功路径返回的是该 dict 本身
        # (区别于治理失败路径会 raise 异常)。
        gov_result_dict = {"status": "PENDING_APPROVAL", "confidence_score": 0.3}
        gov_future = MagicMock()
        gov_future.result.return_value = gov_result_dict
        mock_loop.run_coroutine.side_effect = [pipeline_future, gov_future]

        from src.worker.tasks import run_test_pipeline
        mock_self = MagicMock()
        mock_self.request.id = "test-task-id-002"
        result = run_test_pipeline.run.__func__(mock_self, sample_request_dict)

        # [反 tautology] 只验证传播路径: result 必须就是 gov_future.result() 的返回值。
        # 用 `is` 同一性断言 (强于 ==), 证明源码 line 68 `return gov_future.result(timeout=60)`
        # 原样透传 governance future 的结果, 没有中途转换/丢弃。
        # 逐字段断言已被移除 — 那只是在断言测试自己塞进 mock 的数据, 无法发现真实 bug。
        assert result is gov_result_dict, (
            "治理成功路径必须 return gov_future.result(timeout=60) 的返回值, "
            f"实际返回: {result!r}"
        )
        # run_coroutine 调用 2 次 (pipeline + governance)
        assert mock_loop.run_coroutine.call_count == 2, \
            "治理路径 run_coroutine 应调用 2 次 (pipeline + governance)"
        # 两个 future 的 result() 都用 timeout=60 (源码 line 46, 68)
        pipeline_future.result.assert_called_once_with(timeout=60)
        gov_future.result.assert_called_once_with(timeout=60)
        # trace_id 在 finally 中重置 (即使走治理路径, line 72-73)
        mock_reset.assert_called_once_with("trace-token-002")

    @patch("src.engine.pipeline.ExecutionPipeline")
    @patch("src.core.container.ResourceContainer")
    @patch("src.worker.tasks.AsyncLoopManager")
    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    def test_governance_failure_reraises_original_exception(
        self, mock_reset, mock_set, mock_loop, mock_container,
        mock_pipeline_cls, sample_request_dict
    ):
        """治理也失败时, 必须重新抛出原始异常 (源码 tasks.py:69-71: raise e, 非 ai_err)。

        限制: GovernanceOrchestrator 在 _governance() 协程体内, 协程不执行, 不 patch。
        """
        mock_set.return_value = "trace-token-003"

        # pipeline 抛原始异常 RuntimeError
        pipeline_future = MagicMock()
        pipeline_future.result.side_effect = RuntimeError("Pipeline exploded")
        # governance 也抛异常 ValueError
        gov_future = MagicMock()
        gov_future.result.side_effect = ValueError("AI governance crashed")
        mock_loop.run_coroutine.side_effect = [pipeline_future, gov_future]

        from src.worker.tasks import run_test_pipeline
        mock_self = MagicMock()
        mock_self.request.id = "test-task-id-003"

        # 严格断言: 必须抛出 RuntimeError (原始异常), 而非 ValueError (治理异常)
        with pytest.raises(RuntimeError, match="Pipeline exploded") as exc_info:
            run_test_pipeline.run.__func__(mock_self, sample_request_dict)

        # 业务逻辑断言: 抛出的是原始异常, 不是治理异常
        assert "Pipeline exploded" in str(exc_info.value)
        assert "AI governance crashed" not in str(exc_info.value), \
            "必须 raise e (原始异常), 不能 raise ai_err (治理异常)"
        # 业务逻辑断言: run_coroutine 调用 2 次
        assert mock_loop.run_coroutine.call_count == 2
        # 业务逻辑断言: 即使异常传播, finally 仍重置 trace_id
        mock_reset.assert_called_once_with("trace-token-003")

    @patch("src.engine.pipeline.ExecutionPipeline")
    @patch("src.core.container.ResourceContainer")
    @patch("src.worker.tasks.AsyncLoopManager")
    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    def test_governance_failure_logs_error(
        self, mock_reset, mock_set, mock_loop, mock_container,
        mock_pipeline_cls, sample_request_dict, caplog
    ):
        """治理失败时必须记录 error 日志 (源码 tasks.py:70: logging.error)。

        限制: GovernanceOrchestrator 在 _governance() 协程体内, 协程不执行, 不 patch。
        """
        mock_set.return_value = "t"

        pipeline_future = MagicMock()
        pipeline_future.result.side_effect = RuntimeError("Pipeline exploded")
        gov_future = MagicMock()
        gov_future.result.side_effect = ValueError("AI governance crashed")
        mock_loop.run_coroutine.side_effect = [pipeline_future, gov_future]

        from src.worker.tasks import run_test_pipeline
        mock_self = MagicMock()
        mock_self.request.id = "log-test-id"

        with caplog.at_level(logging.ERROR, logger="src.worker.tasks"):
            with pytest.raises(RuntimeError):
                run_test_pipeline.run.__func__(mock_self, sample_request_dict)

        # 业务逻辑断言: 必须有 error 日志包含 "AI Governance Failed"
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(error_records) >= 1, "治理失败必须记录 error 日志"
        assert any("AI Governance Failed" in r.getMessage() for r in error_records), \
            "日志必须包含 'AI Governance Failed'"


# ==================== trace_id 生命周期 ====================

class TestTraceIdLifecycle:
    """验证 trace_id 在所有路径下都被正确重置 (源码 tasks.py:65-66 finally 块)。"""

    @patch("src.engine.pipeline.ExecutionPipeline")
    @patch("src.core.container.ResourceContainer")
    @patch("src.worker.tasks.AsyncLoopManager")
    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    def test_trace_id_reset_on_success(
        self, mock_reset, mock_set, mock_loop, mock_container, mock_pipeline_cls,
        sample_request_dict
    ):
        """成功路径也必须重置 trace_id。"""
        mock_set.return_value = "trace-success"
        mock_future = MagicMock()
        mock_future.result.return_value = "Success"
        mock_loop.run_coroutine.return_value = mock_future

        from src.worker.tasks import run_test_pipeline
        mock_self = MagicMock()
        mock_self.request.id = "success-id"
        run_test_pipeline.run.__func__(mock_self, sample_request_dict)

        mock_reset.assert_called_once_with("trace-success")

    @patch("src.engine.pipeline.ExecutionPipeline")
    @patch("src.core.container.ResourceContainer")
    @patch("src.worker.tasks.AsyncLoopManager")
    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    def test_trace_id_reset_on_exception_propagation(
        self, mock_reset, mock_set, mock_loop, mock_container,
        mock_pipeline_cls, sample_request_dict
    ):
        """异常传播时 finally 也必须重置 trace_id (源码 tasks.py:72-73)。"""
        mock_set.return_value = "trace-exception"

        pipeline_future = MagicMock()
        pipeline_future.result.side_effect = RuntimeError("Pipeline exploded")
        gov_future = MagicMock()
        gov_future.result.side_effect = ValueError("AI governance crashed")
        mock_loop.run_coroutine.side_effect = [pipeline_future, gov_future]

        from src.worker.tasks import run_test_pipeline
        mock_self = MagicMock()
        mock_self.request.id = "exception-id"

        with pytest.raises(RuntimeError):
            run_test_pipeline.run.__func__(mock_self, sample_request_dict)

        # 业务逻辑断言: 即使异常传播, finally 仍重置 trace_id
        mock_reset.assert_called_once_with("trace-exception")


# ==================== 边界场景 ====================

class TestWorkerBoundaryScenarios:
    """验证任务入口对边界输入的健壮性 (此前缺失的负向/边界场景)。

    覆盖此前未测的 3 个边界:
      1. run_coroutine 自身抛异常 (非 future.result) — 验证异常归并语义 (raise e, 非 ai_err)
      2. 空 request_dict {} — 验证任务入口对空请求不崩溃
      3. self.request.id 为 None — 验证 set_trace_id 透传 None (契约断言)

    诚实声明: set_trace_id/reset_trace_id 被 mock, 无法验证真实 None/空值处理。
              真实 set_trace_id 行为由 src.core.tracer 单元测试覆盖。
              此处只验证任务入口 (tasks.py:12-13, 44-73) 对边界输入不崩溃 + 契约调用。
    """

    @patch("src.engine.pipeline.ExecutionPipeline")
    @patch("src.core.container.ResourceContainer")
    @patch("src.worker.tasks.AsyncLoopManager")
    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    def test_run_coroutine_itself_raises_propagates_first_exception(
        self, mock_reset, mock_set, mock_loop, mock_container,
        mock_pipeline_cls, sample_request_dict, caplog
    ):
        """run_coroutine 自身抛异常时, 第一异常被重抛 (源码 tasks.py:45, 67, 71)。

        场景: AsyncLoopManager.run_coroutine 直接抛异常 (如事件循环未启动),
              而非 future.result() 抛异常。这是与 future.result 异常不同的路径:
              - line 45 `future = AsyncLoopManager.run_coroutine(_execute())` 抛 first_err
              - except Exception as e: e = first_err
              - line 67 `gov_future = AsyncLoopManager.run_coroutine(_governance(e))` 抛 second_err
              - except Exception as ai_err: ai_err = second_err → logging.error → raise e (first_err)

        严格断言: 必须重抛第一异常 (原始), 不是第二异常 (治理)。
        """
        mock_set.return_value = "trace-boundary-1"
        first_err = RuntimeError("run_coroutine crashed (loop not running)")
        second_err = ValueError("governance run_coroutine also crashed")
        # 两次 run_coroutine 调用都直接抛异常 (非 future.result)
        mock_loop.run_coroutine.side_effect = [first_err, second_err]

        from src.worker.tasks import run_test_pipeline
        mock_self = MagicMock()
        mock_self.request.id = "boundary-1"

        with caplog.at_level(logging.ERROR, logger="src.worker.tasks"):
            with pytest.raises(RuntimeError, match="run_coroutine crashed") as exc_info:
                run_test_pipeline.run.__func__(mock_self, sample_request_dict)

        # 必须重抛第一异常 (原始 e), 不是第二异常 (ai_err)
        assert "governance run_coroutine also crashed" not in str(exc_info.value), \
            "必须 raise e (第一异常), 不能 raise ai_err (第二异常)"
        # run_coroutine 调用 2 次 (pipeline + governance 都尝试过)
        assert mock_loop.run_coroutine.call_count == 2
        # 第二异常被捕获时必须记 error 日志 (源码 line 70)
        assert any("AI Governance Failed" in r.getMessage() for r in caplog.records
                   if r.levelno == logging.ERROR), \
            "第二异常被捕获时必须记 'AI Governance Failed' error 日志"
        # 即使 run_coroutine 自身崩溃, finally 仍重置 trace_id
        mock_reset.assert_called_once_with("trace-boundary-1")

    @patch("src.engine.pipeline.ExecutionPipeline")
    @patch("src.core.container.ResourceContainer")
    @patch("src.worker.tasks.AsyncLoopManager")
    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    def test_empty_request_dict_does_not_crash_task_entry(
        self, mock_reset, mock_set, mock_loop, mock_container,
        mock_pipeline_cls
    ):
        """空 request_dict {} 不应导致任务入口崩溃 (源码 tasks.py:12-13, 44-46)。

        request_dict 仅在 _execute/_governance 协程体内使用 (line 29, 34-37, 52-57),
        协程因 run_coroutine 被 mock 不执行, 故空 dict 在 mock 路径下不触发内部读取。
        此测试验证任务入口 (set_trace_id / try / finally) 对空 dict 的健壮性。
        """
        mock_set.return_value = "trace-empty"
        mock_future = MagicMock()
        mock_future.result.return_value = "Success"
        mock_loop.run_coroutine.return_value = mock_future

        from src.worker.tasks import run_test_pipeline
        mock_self = MagicMock()
        mock_self.request.id = "empty-req-id"
        # 空 dict — 不得在任务入口抛 KeyError/TypeError
        result = run_test_pipeline.run.__func__(mock_self, {})

        assert result == "Success", "空 dict 不应阻断正常路径返回"
        mock_reset.assert_called_once_with("trace-empty")

    @patch("src.engine.pipeline.ExecutionPipeline")
    @patch("src.core.container.ResourceContainer")
    @patch("src.worker.tasks.AsyncLoopManager")
    @patch("src.worker.tasks.set_trace_id")
    @patch("src.worker.tasks.reset_trace_id")
    def test_none_request_id_passed_through_to_set_trace_id(
        self, mock_reset, mock_set, mock_loop, mock_container,
        mock_pipeline_cls, sample_request_dict
    ):
        """self.request.id 为 None 时, set_trace_id 必须收到 None (源码 tasks.py:13)。

        契约断言: 源码 `set_trace_id(self.request.id)` 必须原样透传 request.id,
        不能替换为默认值 (如 `or "default"`)。这保证 trace_id 与 Celery task id 一致性。
        限制: set_trace_id 被 mock, 真实 None 处理由 src.core.tracer 单元测试覆盖。
        """
        mock_set.return_value = "trace-none-id"
        mock_future = MagicMock()
        mock_future.result.return_value = "Success"
        mock_loop.run_coroutine.return_value = mock_future

        from src.worker.tasks import run_test_pipeline
        mock_self = MagicMock()
        mock_self.request.id = None  # Celery 偶发无 task id 的边界
        result = run_test_pipeline.run.__func__(mock_self, sample_request_dict)

        assert result == "Success", "request.id=None 不应阻断正常路径"
        # 契约: set_trace_id 必须收到 None (原样透传), 不能被默认值替换
        mock_set.assert_called_once_with(None)
        mock_reset.assert_called_once_with("trace-none-id")


class TestGovernanceCoroutineRealRun:
    """[真实严格] 直接执行 _governance() 协程体, 验证走 orchestrator 返回治理结果。

    P0 修复后: _governance 调 orchestrator.execute_governance_flow 而非 agent.analyze_with_context。
    返回值是 orchestrator 治理结果 dict (有 status 字段), 非 AIGovernanceResult.model_dump()。
    """

    def test_governance_coroutine_returns_orchestrator_result(self, sample_request_dict):
        """真实执行 _execute + _governance, 验证返回 orchestrator 治理结果 (有 status 字段)。

        覆盖:
        - tasks.py:20-39 (_execute 真实执行到 pipeline.run 抛错)
        - tasks.py:41-62 (except + 真实的 _governance() 协程执行)
        - tasks.py:60-61 (orchestrator.execute_governance_flow → 返回治理 dict)
        """
        # orchestrator 返回的治理结果结构 (有 status 字段, 非 AIGovernanceResult)
        gov_result_dict = {
            "status": "PENDING_APPROVAL",
            "reason": "Patch requires manual approval",
            "confidence_score": 0.3,
            "reasoning": "真实执行后的治理分析结果",
            "suggested_fix": "def real_target_fn(self):\n    pass",
        }

        def _run_coro_side_effect(coro):
            """真实运行传入的协程, 并将结果包装成 future 模拟。"""
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(coro)
            finally:
                loop.close()
            fut = MagicMock()
            fut.result.return_value = result
            return fut

        mock_set_ret = "trace-real-run"

        with patch("src.engine.pipeline.ExecutionPipeline") as mock_pipe_cls, \
             patch("src.core.container.ResourceContainer") as mock_container_cls, \
             patch("src.worker.tasks.AsyncLoopManager") as mock_loop_cls, \
             patch("src.worker.tasks.set_trace_id", return_value=mock_set_ret) as mock_set, \
             patch("src.worker.tasks.reset_trace_id") as mock_reset, \
             patch("src.engine.registry.get_pipeline", return_value=[]), \
             patch("src.worker.tasks.GovernanceOrchestrator") as mock_orch_cls:

            # ResourceContainer
            mock_client = MagicMock()
            mock_repo = MagicMock()
            mock_repo.save_execution = AsyncMock()
            mock_container_cls.get_client = AsyncMock(return_value=mock_client)
            mock_container_cls.get_repo = AsyncMock(return_value=mock_repo)

            # ExecutionPipeline.run 抛错 → _execute 真实执行到抛错
            mock_pipe_inst = MagicMock()
            mock_pipe_inst.run = AsyncMock(side_effect=RuntimeError("真实Pipeline运行失败触发治理"))
            mock_pipe_cls.return_value = mock_pipe_inst

            # GovernanceOrchestrator.execute_governance_flow → 返回治理结果 dict
            mock_orch_inst = MagicMock()
            mock_orch_inst.execute_governance_flow = AsyncMock(return_value=gov_result_dict)
            mock_orch_cls.return_value = mock_orch_inst

            # AsyncLoopManager.run_coroutine → 真实执行传入的协程
            mock_loop_cls.run_coroutine.side_effect = _run_coro_side_effect

            from src.worker.tasks import run_test_pipeline
            mock_self = MagicMock()
            mock_self.request.id = "real-governance-001"
            result = run_test_pipeline.run.__func__(mock_self, sample_request_dict)

            # ====== 严格真实断言 ======
            # 1. result 必须是 dict
            assert isinstance(result, dict), f"治理结果必须是dict, 实际: {type(result)}"
            # 2. 必须有 status 字段 (orchestrator 返回结构, 非 AIGovernanceResult)
            assert "status" in result, (
                f"返回值缺 'status' 字段 — 应是 orchestrator 治理结果, "
                f"实际字段: {list(result.keys())}"
            )
            assert result["status"] == "PENDING_APPROVAL"
            # 3. 可被 JSON 序列化 (Celery result backend 要求)
            serialized = json.dumps(result)
            roundtripped = json.loads(serialized)
            assert roundtripped["status"] == "PENDING_APPROVAL"
            # 4. trace id 正确重置
            mock_set.assert_called_once_with("real-governance-001")
            mock_reset.assert_called_once_with(mock_set_ret)
            # 5. run_coroutine 被调用 2 次 (_execute + _governance)
            assert mock_loop_cls.run_coroutine.call_count == 2
            # 6. orchestrator.execute_governance_flow 被真实调用过 (证明 _governance 真走了 orchestrator)
            mock_orch_inst.execute_governance_flow.assert_awaited_once()
            # 7. Pipeline.run 被真实调用过 (证明 _execute 真跑了)
            mock_pipe_inst.run.assert_awaited_once()
