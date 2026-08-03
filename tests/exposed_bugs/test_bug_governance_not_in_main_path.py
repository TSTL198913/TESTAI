"""BUG (P0): 异常 fallback 只走 AI 诊断, 不走治理闭环。

这是 AI 治理平台核心能力在日常路径不存在的根本原因。

问题 (代码实证):
  src/worker/tasks.py:47-58 异常 fallback 调用 AIGovernanceAgent.analyze_with_context()
  而非 GovernanceOrchestrator.execute_governance_flow()

  tasks.py:10  `from src.governance.agent import AIGovernanceAgent`  ← 直接调 agent
  tasks.py:48  `agent = AIGovernanceAgent()`
  tasks.py:57  `governance_result = await agent.analyze_with_context(diag_context)`
  tasks.py:58  `return governance_result.model_dump(mode="json")`  ← 返回诊断结构

  而 orchestrator.execute_governance_flow (orchestrator.py:64) 才是完整六步闭环:
    分类(L73) → 诊断(L93) → 审批闸门(L161) → Git事务(L193) → 补丁(L202) → 收敛(L230)

后果:
  测试失败时只做"诊断"(返回 is_fixable/confidence), 不走六步闭环。
  AI 治理平台的核心能力(分类→审批→Git→补丁→收敛)在日常 /execute 路径上不存在。
  完整治理只能通过 /governance/execute API 主动触发, 非自治。

修复方向:
  tasks.py 异常 fallback 改为调 orchestrator.execute_governance_flow()。
  orchestrator 内部分类器(L73 _classify_exception)作为触发策略:
    - RETRY / MANUAL_REQUIRED → SKIPPED (轻量, 不触发 Git/补丁)
    - AI_DIAGNOSE → 诊断 → 审批闸门 → 大部分 PENDING_APPROVAL (人工确认)
    - 只有低风险+高置信度才自动走 Git+补丁
  即: orchestrator 自身已有触发策略, 不需要额外设计。

本测试断言"正确行为应该是什么":
  当前 FAIL (红色) = 证明 BUG 存在
  src/ 修复后 PASS (绿色) = 固化为回归网
"""
import inspect

import pytest


# ==================== 问题1: tasks.py 未导入 GovernanceOrchestrator ====================

class TestOrchestratorNotInMainPath:
    """证明: tasks.py 异常 fallback 走 agent 不走 orchestrator。"""

    def test_tasks_imports_governance_orchestrator(self):
        """tasks.py 必须 import GovernanceOrchestrator (当前只 import AIGovernanceAgent)。

        当前缺失 → FAIL, 证明异常路径不走治理闭环。
        修复后 (import orchestrator) → PASS。
        """
        from src.worker import tasks as tasks_module

        source = inspect.getsource(tasks_module)
        assert "GovernanceOrchestrator" in source, (
            "tasks.py 未导入 GovernanceOrchestrator — "
            "异常 fallback 只调 AIGovernanceAgent 做诊断, "
            "不走 orchestrator 六步闭环 (分类→审批→Git→补丁→收敛), "
            "AI 治理核心能力在日常路径不存在 (P0)"
        )

    def test_tasks_calls_orchestrator_not_agent_directly(self):
        """tasks.py 异常 fallback 应调 orchestrator.execute_governance_flow,
        而非直接调 agent.analyze_with_context。

        当前调 agent → FAIL。
        修复后调 orchestrator → PASS。
        """
        from src.worker import tasks as tasks_module

        source = inspect.getsource(tasks_module)
        assert "execute_governance_flow" in source, (
            "tasks.py 异常 fallback 未调用 orchestrator.execute_governance_flow — "
            "只调 agent.analyze_with_context 做诊断, "
            "不走审批/Git/补丁/收敛 (P0)"
        )
        # 修复后: 不应直接在 tasks.py 中实例化 AIGovernanceAgent 做诊断
        # (orchestrator 内部会调 agent, tasks.py 不应绕过 orchestrator)
        assert "AIGovernanceAgent()" not in source, (
            "tasks.py 直接实例化 AIGovernanceAgent — "
            "应通过 orchestrator.execute_governance_flow 间接调用, "
            "绕过 orchestrator = 绕过审批/Git/补丁/收敛 (P0)"
        )


# ==================== 问题2: 异常返回值是诊断结构而非治理结果 ====================

class TestExceptionReturnsGovernanceResult:
    """证明: 异常 fallback 返回 AIGovernanceResult 结构(诊断), 非治理结果(有status)。

    orchestrator.execute_governance_flow 返回:
      {"status": "SKIPPED/DIAGNOSED/PENDING_APPROVAL/FIXED", ...}
    当前 tasks.py 返回:
      {"is_fixable": bool, "confidence_score": float, ...}  (AIGovernanceResult)
    两者结构完全不同。
    """

    def test_exception_fallback_returns_status_field(self):
        """异常 fallback 返回值必须有 'status' 字段 (orchestrator 返回结构)。

        当前返回 AIGovernanceResult.model_dump() 无 'status' → FAIL。
        修复后返回 orchestrator 结果有 'status' → PASS。
        """
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock

        request_dict = {
            "step_id": "gov-path-test-001",
            "url": "http://localhost:8080/health",
            "method": "GET",
            "_trace_id": "abc12345",
            "_requester": "testuser",
        }

        with patch("src.engine.pipeline.ExecutionPipeline") as mock_pipe_cls, \
             patch("src.core.container.ResourceContainer") as mock_container_cls, \
             patch("src.worker.tasks.AsyncLoopManager") as mock_loop_cls, \
             patch("src.worker.tasks.set_trace_id", return_value="trace-gov"), \
             patch("src.worker.tasks.reset_trace_id"), \
             patch("src.engine.registry.get_pipeline", return_value=[]):

            mock_client = MagicMock()
            mock_repo = MagicMock()
            mock_repo.save_execution = AsyncMock()
            mock_container_cls.get_client = AsyncMock(return_value=mock_client)
            mock_container_cls.get_repo = AsyncMock(return_value=mock_repo)

            mock_pipe_inst = MagicMock()
            mock_pipe_inst.run = AsyncMock(side_effect=RuntimeError("Pipeline failed"))
            mock_pipe_cls.return_value = mock_pipe_inst

            def _run_coro_side_effect(coro):
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(coro)
                finally:
                    loop.close()
                fut = MagicMock()
                fut.result.return_value = result
                return fut

            mock_loop_cls.run_coroutine.side_effect = _run_coro_side_effect

            from src.worker.tasks import run_test_pipeline
            mock_self = MagicMock()
            mock_self.request.id = "gov-path-task-001"
            result = run_test_pipeline.run.__func__(mock_self, request_dict)

            # orchestrator 返回的治理结果必须有 'status' 字段
            assert isinstance(result, dict), f"结果应是 dict, 实际: {type(result)}"
            assert "status" in result, (
                f"异常 fallback 返回值缺 'status' 字段 — "
                f"返回的是 AIGovernanceResult 诊断结构 (is_fixable/confidence), "
                f"非 orchestrator 治理结果 (status: SKIPPED/DIAGNOSED/FIXED/...)。 "
                f"证明异常路径不走治理闭环 (P0)。 "
                f"实际返回: {list(result.keys())}"
            )

    def test_exception_fallback_does_not_return_is_fixable_only(self):
        """异常 fallback 不应只返回诊断字段 (is_fixable), 应返回治理结果 (status)。

        当前返回 is_fixable 无 status → FAIL。
        """
        import asyncio
        from unittest.mock import patch, MagicMock, AsyncMock

        request_dict = {
            "step_id": "gov-path-test-002",
            "url": "http://localhost:8080/health",
            "method": "GET",
        }

        with patch("src.engine.pipeline.ExecutionPipeline") as mock_pipe_cls, \
             patch("src.core.container.ResourceContainer") as mock_container_cls, \
             patch("src.worker.tasks.AsyncLoopManager") as mock_loop_cls, \
             patch("src.worker.tasks.set_trace_id", return_value="t"), \
             patch("src.worker.tasks.reset_trace_id"), \
             patch("src.engine.registry.get_pipeline", return_value=[]):

            mock_client = MagicMock()
            mock_repo = MagicMock()
            mock_repo.save_execution = AsyncMock()
            mock_container_cls.get_client = AsyncMock(return_value=mock_client)
            mock_container_cls.get_repo = AsyncMock(return_value=mock_repo)

            mock_pipe_inst = MagicMock()
            mock_pipe_inst.run = AsyncMock(side_effect=RuntimeError("Pipeline failed"))
            mock_pipe_cls.return_value = mock_pipe_inst

            def _run_coro_side_effect(coro):
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(coro)
                finally:
                    loop.close()
                fut = MagicMock()
                fut.result.return_value = result
                return fut

            mock_loop_cls.run_coroutine.side_effect = _run_coro_side_effect

            from src.worker.tasks import run_test_pipeline
            mock_self = MagicMock()
            mock_self.request.id = "gov-path-task-002"
            result = run_test_pipeline.run.__func__(mock_self, request_dict)

            # 如果返回的是 AIGovernanceResult 结构 (有 is_fixable 无 status) = 诊断 only
            has_diagnosis_fields = "is_fixable" in result and "status" not in result
            assert not has_diagnosis_fields, (
                f"异常 fallback 返回诊断结构 (is_fixable={result.get('is_fixable')}) "
                f"而非治理结果 — 只做了诊断, 没走六步闭环 (P0)"
            )
