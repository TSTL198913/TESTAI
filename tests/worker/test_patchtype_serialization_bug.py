"""
P0-BUG 回归测试: PatchType 序列化缺陷已修复

BUG 历史:
  src/worker/tasks.py 异常 fallback 曾使用 `governance_result.model_dump()` 返回治理结果。
  model_dump() 不转换枚举, 返回的 dict 中 patch_type 仍为 PatchType 枚举对象。
  Celery 结果后端使用 JSON 序列化存储结果时, 抛出:
    kombu.exceptions.EncodeError: Object of type PatchType is not JSON serializable

修复演进:
  v1: tasks.py 改为 `governance_result.model_dump(mode="json")` — 将枚举转为字符串值。
  v2 (当前): tasks.py 异常 fallback 改为调 GovernanceOrchestrator.execute_governance_flow()。
            orchestrator 返回纯 dict, 其中 patch_type 使用 `.value` 转为字符串 (orchestrator.py:167)。
            tasks.py 不再直接调 model_dump, 序列化责任下沉到 orchestrator。

真正的业务不变量 (与具体机制无关):
  tasks.py 治理路径的返回值必须可被 JSON 序列化 (Celery 后端要求)。
  无论用 model_dump(mode="json") 还是 orchestrator dict+.value, 都必须满足此不变量。

本测试验证:
  1. tasks.py 使用 GovernanceOrchestrator (而非直接 model_dump 或裸 agent 调用)
  2. tasks.py 不含裸 model_dump() (防止回退到危险模式)
  3. orchestrator 所有返回路径的 dict 可被 JSON 序列化, patch_type 为字符串
  4. model_dump(mode="json") 对所有 PatchType 枚举值均有效 (Pydantic 层面)
  5. model_dump() (无 mode) 仍返回枚举对象 — 作为为何需要序列化的文档
"""
import json
import inspect

import pytest

from src.governance.models import AIGovernanceResult, PatchProposal
from src.governance.registry import PatchType


class TestPatchTypeSerializationFixed:
    """回归测试: 验证治理结果可被 JSON 序列化 (Celery 后端要求)。"""

    @pytest.fixture
    def governance_result_with_patch(self):
        """构造含 PatchType 的治理结果 (模拟 AI 分析成功且建议补丁)。"""
        return AIGovernanceResult(
            is_fixable=True,
            reasoning="Connection refused indicates network issue",
            root_cause="Missing retry logic",
            patch_proposal=PatchProposal(
                target_function="send_request",
                target_class="HTTPProcessor",
                suggested_code="def send_request(self): pass",
                required_imports=["import time"],
                patch_type=PatchType.FUNCTIONAL,
            ),
            confidence_score=0.9,
        )

    def test_tasks_py_uses_orchestrator_not_model_dump(self):
        """验证 tasks.py 治理路径不含裸 model_dump() (会返回枚举对象导致 Celery 崩溃)。

        P0 BUG 修复演进:
          v1: tasks.py 用 model_dump(mode="json") 序列化 AIGovernanceResult
          v2: tasks.py 调 orchestrator.execute_governance_flow(), 序列化责任下沉

        真正的不变量 (与具体机制无关, 见模块 docstring line 16-18):
          tasks.py 不含裸 model_dump() (无 mode 参数) — 会返回枚举对象导致 Celery 崩溃。
          机制可以是 orchestrator 或 model_dump(mode="json"), 都满足 JSON 可序列化要求。
          其余测试 (test_orchestrator_return_is_json_serializable_all_paths,
          test_governance_result_is_json_serializable_after_fix) 已验证返回值可序列化。
        """
        from src.worker import tasks as tasks_module

        source = inspect.getsource(tasks_module)
        # 不应存在裸 model_dump() (无 mode 参数) — 会返回枚举对象导致序列化崩溃
        assert ".model_dump()" not in source, (
            "tasks.py 不应使用裸 model_dump() — "
            "会返回枚举对象导致 Celery JSON 序列化失败 (P0 BUG 重现)"
        )
        # 必须使用以下两种机制之一 (都满足 JSON 可序列化不变量):
        #   - orchestrator.execute_governance_flow() (v2, 序列化责任下沉)
        #   - model_dump(mode="json") (v1, 直接序列化)
        uses_orchestrator = "GovernanceOrchestrator" in source and "execute_governance_flow" in source
        uses_json_mode = 'model_dump(mode="json")' in source or "model_dump(mode='json')" in source
        assert uses_orchestrator or uses_json_mode, (
            "tasks.py 治理路径必须使用 orchestrator 或 model_dump(mode='json') 之一, "
            "否则返回值含 PatchType 枚举对象导致 Celery 序列化失败 (P0)"
        )

    @pytest.mark.asyncio
    async def test_orchestrator_return_is_json_serializable_all_paths(self):
        """运行时验证: orchestrator 所有返回路径的 dict 可被 JSON 序列化。

        这是 P0 BUG 的真正业务不变量 (与具体序列化机制无关):
          tasks.py 返回 orchestrator 结果 → Celery JSON 后端序列化存储。
          若返回值含 PatchType 枚举对象 → kombu.exceptions.EncodeError → 所有异步治理任务失败。

        覆盖 orchestrator.py 的 4 条核心返回路径:
          1. SKIPPED (非治理动作, 如网络异常 RETRY)
          2. FAILED (agent 诊断异常)
          3. SKIPPED (诊断结果 is_fixable=False)
          4. PENDING_APPROVAL (需人工审批, 含 patch_type)
        """
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from src.governance.orchestrator import GovernanceOrchestrator
        from src.governance.models import (
            AIGovernanceResult,
            DiagnosticContext,
            PatchProposal,
        )
        from src.governance.registry import PatchType

        def _make_ctx(exception_trace: str) -> DiagnosticContext:
            return DiagnosticContext(
                step_id="serial-test",
                component_name="pipeline",
                input_data={},
                actual_output="error",
                expected_baseline=None,
                exception_trace=exception_trace,
            )

        # ---- 路径1: SKIPPED (网络异常 → RETRY → 非 AI_DIAGNOSE → SKIPPED) ----
        orch = GovernanceOrchestrator()
        ctx_network = _make_ctx("ConnectionRefusedError: connection refused")
        result_skipped = await orch.execute_governance_flow(ctx_network)
        assert isinstance(result_skipped, dict)
        assert result_skipped["status"] == "SKIPPED"
        # 必须可 JSON 序列化 (Celery 后端要求)
        json.dumps(result_skipped)  # 不抛 TypeError 即通过

        # ---- 路径2: FAILED (agent 抛异常) ----
        orch2 = GovernanceOrchestrator()
        orch2.agent = MagicMock()
        orch2.agent.analyze_with_context = AsyncMock(
            side_effect=RuntimeError("LLM service unavailable")
        )
        ctx_code = _make_ctx("TypeError: unsupported operand type(s)")
        result_failed = await orch2.execute_governance_flow(ctx_code)
        assert isinstance(result_failed, dict)
        assert result_failed["status"] == "FAILED"
        json.dumps(result_failed)  # 不抛 TypeError

        # ---- 路径3: SKIPPED (is_fixable=False) ----
        orch3 = GovernanceOrchestrator()
        orch3.agent = MagicMock()
        orch3.agent.analyze_with_context = AsyncMock(
            return_value=AIGovernanceResult(
                is_fixable=False,
                reasoning="Cannot auto-fix manually",
                confidence_score=0.2,
            )
        )
        result_not_fixable = await orch3.execute_governance_flow(ctx_code)
        assert isinstance(result_not_fixable, dict)
        assert result_not_fixable["status"] == "SKIPPED"
        json.dumps(result_not_fixable)

        # ---- 路径4: PENDING_APPROVAL (is_fixable=True, 需审批) ----
        # 这是最关键的路径: 返回值含 patch_type, 必须是字符串而非枚举
        orch4 = GovernanceOrchestrator()
        orch4.agent = MagicMock()
        orch4.agent.analyze_with_context = AsyncMock(
            return_value=AIGovernanceResult(
                is_fixable=True,
                reasoning="Missing retry logic",
                root_cause="No retry",
                patch_proposal=PatchProposal(
                    target_function="send_request",
                    target_class="HTTPProcessor",
                    suggested_code="def send_request(self): pass",
                    required_imports=["import time"],
                    patch_type=PatchType.FUNCTIONAL,
                ),
                confidence_score=0.95,
            )
        )
        # 审批管理器: create_approval 正常, requires_approval 返回 True
        orch4.approval_mgr = MagicMock()
        orch4.approval_mgr.create_approval = MagicMock(return_value=None)
        orch4.approval_mgr.requires_approval = MagicMock(return_value=True)

        result_pending = await orch4.execute_governance_flow(ctx_code)
        assert isinstance(result_pending, dict)
        assert result_pending["status"] == "PENDING_APPROVAL"

        # 核心断言: patch_type 必须是字符串, 不是 PatchType 枚举
        assert "patch_type" in result_pending, (
            "PENDING_APPROVAL 结果应包含 patch_type 字段"
        )
        patch_type_val = result_pending["patch_type"]
        assert isinstance(patch_type_val, str), (
            f"patch_type 必须是字符串 (Celery JSON 要求), 实际类型: {type(patch_type_val)} — "
            f"若为 PatchType 枚举则 P0 BUG 重现"
        )
        assert not isinstance(patch_type_val, PatchType), (
            "patch_type 不应是 PatchType 枚举实例 — orchestrator 应使用 .value 转字符串"
        )
        assert patch_type_val == "functional"

        # 核心: 整个返回 dict 可被 JSON 序列化 (Celery 后端存储要求)
        serialized = json.dumps(result_pending)
        roundtripped = json.loads(serialized)
        assert roundtripped["status"] == "PENDING_APPROVAL"
        assert roundtripped["patch_type"] == "functional"
        assert roundtripped["confidence_score"] == 0.95

    def test_governance_result_is_json_serializable_after_fix(
        self, governance_result_with_patch
    ):
        """修复验证: model_dump(mode='json') 的结果包含正确业务字段且可序列化。

        模拟 tasks.py:58 的返回路径:
          return governance_result.model_dump(mode="json")

        [M4-BUG 防逃逸] 验证字段结构完整, 防止任意 dict/字符串也能通过。
        """
        dumped = governance_result_with_patch.model_dump(mode="json")

        # 1. 关键字段必须存在 (防止返回任意 dict 或 {"type": "ClassName"} 逃逸)
        REQUIRED_TOP = {"is_fixable", "reasoning", "confidence_score", "patch_proposal"}
        missing = REQUIRED_TOP - set(dumped.keys())
        assert not missing, f"缺少关键字段: {missing} — 模型结构被破坏未被检测"

        REQUIRED_PROPOSAL = {"target_function", "suggested_code", "patch_type"}
        missing_prop = REQUIRED_PROPOSAL - set(dumped["patch_proposal"].keys())
        assert not missing_prop, f"patch_proposal 缺少字段: {missing_prop}"

        # 2. 字段类型/值必须正确
        assert isinstance(dumped["is_fixable"], bool), "is_fixable 必须是 bool"
        assert dumped["is_fixable"] is True
        assert isinstance(dumped["confidence_score"], (int, float)), "confidence_score 必须是数字"
        assert 0.0 <= dumped["confidence_score"] <= 1.0, "confidence_score 超出 0-1 范围"
        assert isinstance(dumped["reasoning"], str) and len(dumped["reasoning"]) > 0

        # 3. patch_type 是字符串, 不是枚举对象
        patch_type_value = dumped["patch_proposal"]["patch_type"]
        assert isinstance(patch_type_value, str), (
            f"patch_type 应为字符串, 实际: {type(patch_type_value)} — "
            "若为 PatchType 枚举则说明 BUG 重现"
        )
        assert patch_type_value == "functional"

        # 4. 可被 JSON 序列化 (Celery 后端要求)
        serialized = json.dumps(dumped)
        # 反序列化后结构一致 (证明不是畸形 JSON)
        roundtripped = json.loads(serialized)
        assert roundtripped["patch_proposal"]["patch_type"] == "functional"
        assert roundtripped["is_fixable"] is True
        assert roundtripped["confidence_score"] == 0.9

    def test_celery_backend_can_store_result(self, governance_result_with_patch):
        """端到端验证: 治理结果 dict 可存入 Celery Redis 后端 (JSON 序列化)。"""
        # 模拟 tasks.py:58 修复后的返回值
        task_result = governance_result_with_patch.model_dump(mode="json")

        # Celery 后端使用 json.dumps 存储结果
        stored = json.dumps({"status": "SUCCESS", "result": task_result})
        loaded = json.loads(stored)

        assert loaded["status"] == "SUCCESS"
        assert loaded["result"]["patch_proposal"]["patch_type"] == "functional"
        assert loaded["result"]["is_fixable"] is True
        assert loaded["result"]["confidence_score"] == 0.9

    @pytest.mark.parametrize("patch_type", list(PatchType))
    def test_all_patch_types_serializable_with_json_mode(self, patch_type):
        """所有 PatchType 枚举值在 mode='json' 下均可序列化。"""
        result = AIGovernanceResult(
            is_fixable=True,
            reasoning="test",
            patch_proposal=PatchProposal(
                target_function="f",
                suggested_code="pass",
                patch_type=patch_type,
            ),
            confidence_score=0.5,
        )

        dumped = result.model_dump(mode="json")
        # 可 JSON 序列化
        json.dumps(dumped)
        # patch_type 是字符串
        assert isinstance(dumped["patch_proposal"]["patch_type"], str)


class TestWhyJsonModeIsRequired:
    """文档性测试: 解释为何必须使用 mode='json'。

    这些测试不验证修复, 而是文档化 Pydantic 的默认行为,
    说明为何 tasks.py 必须使用 mode="json"。
    """

    def test_model_dump_without_mode_returns_enum_object(self):
        """Pydantic 默认行为: model_dump() 返回枚举对象 (非字符串)。

        这就是为何 tasks.py 不能使用裸 model_dump() —
        Celery 的 JSON 序列化器无法处理枚举对象。
        """
        result = AIGovernanceResult(
            is_fixable=True,
            reasoning="test",
            patch_proposal=PatchProposal(
                target_function="f",
                suggested_code="pass",
                patch_type=PatchType.SECURITY,
            ),
            confidence_score=0.5,
        )

        dumped = result.model_dump()
        patch_type_value = dumped["patch_proposal"]["patch_type"]

        # Pydantic 默认返回枚举对象 (这是危险行为)
        assert isinstance(patch_type_value, PatchType)

    def test_model_dump_without_mode_not_json_serializable(self):
        """Pydantic 默认行为: model_dump() 结果无法 JSON 序列化。"""
        result = AIGovernanceResult(
            is_fixable=True,
            reasoning="test",
            patch_proposal=PatchProposal(
                target_function="f",
                suggested_code="pass",
                patch_type=PatchType.PERFORMANCE,
            ),
            confidence_score=0.5,
        )

        dumped = result.model_dump()
        with pytest.raises(TypeError, match="not JSON serializable"):
            json.dumps(dumped)

    @pytest.mark.parametrize("patch_type", list(PatchType))
    def test_all_patch_types_fail_without_json_mode(self, patch_type):
        """所有 PatchType 值在无 mode 参数时均无法 JSON 序列化。"""
        result = AIGovernanceResult(
            is_fixable=True,
            reasoning="test",
            patch_proposal=PatchProposal(
                target_function="f",
                suggested_code="pass",
                patch_type=patch_type,
            ),
            confidence_score=0.5,
        )

        dumped = result.model_dump()
        with pytest.raises(TypeError, match="not JSON serializable"):
            json.dumps(dumped)
