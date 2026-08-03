"""BUG (P0): Mock 诊断结果无来源标记, 且 confidence=0.95 可触发自动批准。

这是 AI 治理平台可信度的根基问题。

问题链 (代码实证):
1. src/governance/models.py:21-26 AIGovernanceResult 无 source 字段
   → 下游无法区分 mock 诊断 vs 真实 LLM 诊断
2. src/governance/sdk.py:190-200 get_mock_response 返回 confidence_score=0.95
   → mock 诊断以高置信度返回 (比失败更危险: 失败会被拒绝, mock 成功会被信任)
3. src/governance/auto_decision_engine.py:49-56 rule_auto_approve_high_confidence
   条件: confidence >= 0.9 AND is_fixable = True → action=AUTO_APPROVE
   → mock 诊断 (is_fixable=True, confidence=0.95) 满足条件
4. src/governance/auto_decision_engine.py:179-188 _evaluate_rule 不检查来源
   → 即使 AIGovernanceResult 有 source 字段, evaluate 也不读取它做决策

后果 (端到端):
  USE_MOCK_LLM=True (无 API Key 环境)
  → sdk.get_mock_response 返回 {is_fixable:True, confidence:0.95}
  → agent.analyze_with_context 解析为 AIGovernanceResult (无 source 标记)
  → AutoDecisionEngine.evaluate({confidence:0.95, is_fixable:True})
  → rule_auto_approve_high_confidence 触发 → AUTO_APPROVE
  → 假诊断获得真实代码补丁的自动批准

修复方向 (需 src/ 授权):
  - models.py AIGovernanceResult 加 source: Literal["llm","mock","fallback"] 字段
  - sdk.py get_mock_response 强制 source="mock", confidence 压低 (≤0.3)
  - auto_decision_engine.py evaluate 检查 source, mock 来源不自动批准

本测试断言"正确行为应该是什么":
  当前全 FAIL (红色) = 证明 BUG 存在
  src/ 修复后全 PASS (绿色) = 固化为回归网
"""
import asyncio
import json

import pytest

from src.governance.models import AIGovernanceResult, PatchProposal
from src.governance.sdk import GovernanceClientSDK
from src.governance.auto_decision_engine import AutoDecisionEngine
from src.governance.registry import PatchType


# ==================== 问题1: AIGovernanceResult 无 source 字段 ====================

class TestAIGovernanceResultMissingSource:
    """证明: AIGovernanceResult 缺少 source 字段, 无法区分 mock/真实诊断。"""

    def test_result_model_has_source_field(self):
        """AIGovernanceResult 必须有 source 字段区分诊断来源。

        当前缺失 → FAIL, 证明 BUG。
        修复后 (加 source 字段) → PASS。
        """
        fields = AIGovernanceResult.model_fields
        assert "source" in fields, (
            "AIGovernanceResult 缺少 source 字段 — "
            "下游无法区分 mock 诊断与真实 LLM 诊断, "
            "mock 假诊断会以相同结构进入治理决策链 (P0)"
        )

    def test_source_field_has_literal_constraint(self):
        """source 字段必须是 Literal 类型, 限定 llm/mock/fallback 三种来源。

        当前无该字段 → FAIL。
        """
        import typing

        fields = AIGovernanceResult.model_fields
        if "source" not in fields:
            pytest.fail(
                "AIGovernanceResult 无 source 字段 — 无法验证类型约束 (P0)"
            )
        # 修复后: source 应为 Literal["llm","mock","fallback"]
        annotation = fields["source"].annotation
        origin = typing.get_origin(annotation)
        assert origin is typing.Literal, (
            f"source 字段应为 Literal 类型, 实际: {annotation} — "
            "非 Literal 无法限定来源枚举"
        )


# ==================== 问题2: mock 返回 confidence=0.95 ====================

class TestMockConfidenceTooHigh:
    """证明: sdk.py:193 get_mock_response 返回 confidence=0.95, 过高。"""

    def _get_mock_response_content(self) -> dict:
        """调用 get_mock_response 并解析返回的 mock 诊断 JSON。"""
        sdk = GovernanceClientSDK()
        messages = [
            {
                "role": "user",
                "content": json.dumps({
                    "component_name": "transformer",
                    "target_function": "leave_FunctionDef",
                    "exception_trace": "AttributeError: patched",
                }),
            }
        ]
        response = asyncio.run(sdk.get_mock_response(messages))
        return json.loads(response.content)

    def test_mock_confidence_is_capped_low(self):
        """mock 诊断的 confidence 必须 ≤ 0.3, 防止触发自动批准。

        当前 sdk.py:193 返回 0.95 → FAIL, 证明 BUG。
        修复后 (压低 mock confidence) → PASS。
        """
        data = self._get_mock_response_content()
        assert data["confidence_score"] <= 0.3, (
            f"mock confidence={data['confidence_score']} 过高 — "
            "会触发 rule_auto_approve_high_confidence (≥0.9) 自动批准, "
            "导致假诊断获得真实代码补丁 (P0)"
        )

    def test_mock_response_is_marked_as_mock(self):
        """mock 诊断结果必须标记 source='mock'。

        当前无 source 字段 → KeyError → FAIL, 证明 BUG。
        修复后 (sdk.py 标记 source) → PASS。
        """
        data = self._get_mock_response_content()
        assert data.get("source") == "mock", (
            f"mock 诊断未标记 source='mock', 实际: {data.get('source')} — "
            "下游无法识别这是假诊断 (P0)"
        )


# ==================== 问题3: AutoDecisionEngine 不检查来源 ====================

class TestAutoDecisionEngineIgnoresSource:
    """证明: AutoDecisionEngine.evaluate 不检查诊断来源, mock 可触发 AUTO_APPROVE。"""

    def test_mock_source_does_not_get_auto_approved(self):
        """mock 来源的诊断不应触发 AUTO_APPROVE。

        当前 _evaluate_rule (L179-188) 不读 source → confidence=0.95 触发 AUTO_APPROVE
        → FAIL, 证明 BUG。
        修复后 (evaluate 检查 source) → PASS。
        """
        engine = AutoDecisionEngine()
        context = {
            "confidence": 0.95,
            "is_fixable": True,
            "patch_type": "functional",
            "source": "mock",  # 期望: mock 来源不被自动批准
        }
        decision = engine.evaluate(context, trace_id="test-mock-source-001")

        assert decision.decision != "AUTO_APPROVE", (
            f"mock 来源诊断被 AUTO_APPROVE (rule={decision.rule_triggered}) — "
            "AutoDecisionEngine 未检查 source, "
            "mock 假诊断可触发真实代码补丁自动批准 (P0)"
        )

    def test_llm_source_can_get_auto_approved(self):
        """真实 LLM 来源的高置信度诊断可以被自动批准 (正向对照)。

        此测试确保修复不会过度拦截: 只拦 mock, 不拦真实 LLM。
        当前: 不检查 source, LLM 也走同一规则 → PASS (但这是'不区分'的假阳性)。
        修复后: 检查 source, source='llm' + confidence≥0.9 → AUTO_APPROVE → PASS。
        """
        engine = AutoDecisionEngine()
        context = {
            "confidence": 0.95,
            "is_fixable": True,
            "patch_type": "functional",
            "source": "llm",  # 真实 LLM 诊断
        }
        decision = engine.evaluate(context, trace_id="test-llm-source-001")

        # 真实 LLM 高置信度应该可以被自动批准
        assert decision.decision == "AUTO_APPROVE", (
            f"真实 LLM 诊断 (source='llm', confidence=0.95) 未获 AUTO_APPROVE, "
            f"decision={decision.decision} — "
            "修复不应过度拦截真实诊断"
        )

    def test_fallback_source_does_not_get_auto_approved(self):
        """fallback 来源的诊断不应触发 AUTO_APPROVE。

        fallback 是规则降级诊断 (LLM 不可用时走规则推断), 与 mock 同等不可信,
        不应被自动批准。本测试验证 source 守卫覆盖 mock 与 fallback 两类降级来源。
        """
        engine = AutoDecisionEngine()
        context = {
            "confidence": 0.95,
            "is_fixable": True,
            "patch_type": "functional",
            "source": "fallback",  # 规则降级诊断, 期望不被自动批准
        }
        decision = engine.evaluate(context, trace_id="test-fallback-source-001")

        assert decision.decision != "AUTO_APPROVE", (
            f"fallback 来源诊断被 AUTO_APPROVE (rule={decision.rule_triggered}) — "
            "AutoDecisionEngine source 守卫未覆盖 fallback, "
            "规则降级诊断可触发真实代码补丁自动批准 (P0)"
        )


# ==================== 问题4: 端到端链路证明 ====================

class TestMockToAutoApprovalEndToEnd:
    """端到端证明: mock 诊断 → AutoDecisionEngine → 当前会 AUTO_APPROVE (BUG)。"""

    def test_full_chain_mock_diagnosis_gets_auto_approved_currently(self):
        """完整链路: sdk.get_mock_response → AutoDecisionEngine.evaluate。

        当前: mock(confidence=0.95) → AUTO_APPROVE → FAIL (证明假诊断获批准)。
        修复后: mock 被识别 → 不 AUTO_APPROVE → PASS。
        """
        # Step1: 获取 mock 诊断 (模拟 USE_MOCK_LLM=True 环境)
        sdk = GovernanceClientSDK()
        messages = [
            {
                "role": "user",
                "content": json.dumps({
                    "component_name": "transformer",
                    "target_function": "leave_FunctionDef",
                    "exception_trace": "AttributeError: patched",
                }),
            }
        ]
        response = asyncio.run(sdk.get_mock_response(messages))
        mock_data = json.loads(response.content)

        # Step2: mock 诊断送入 AutoDecisionEngine (模拟治理决策)
        engine = AutoDecisionEngine()
        context = {
            "confidence": mock_data["confidence_score"],
            "is_fixable": mock_data["is_fixable"],
            "patch_type": mock_data["patch_proposal"]["patch_type"],
            "source": mock_data.get("source", "mock"),  # 若无 source 字段则默认 mock
        }
        decision = engine.evaluate(context, trace_id="test-e2e-mock-001")

        # Step3: 断言 mock 诊断不应被自动批准
        assert decision.decision != "AUTO_APPROVE", (
            f"端到端链路证明 BUG: \n"
            f"  sdk.get_mock_response → confidence={mock_data['confidence_score']}, "
            f"is_fixable={mock_data['is_fixable']}\n"
            f"  → AutoDecisionEngine.evaluate → {decision.decision} "
            f"(rule={decision.rule_triggered})\n"
            f"  → 假诊断获得了真实代码补丁的自动批准 (P0)\n"
            f"  修复: mock 结果须标记 source='mock' 且不触发 AUTO_APPROVE"
        )

    def test_mock_and_real_diagnosis_are_distinguishable(self):
        """mock 诊断与真实诊断必须可通过 source 字段区分。

        当前 AIGovernanceResult 无 source → 两者结构相同 → FAIL。
        修复后 → source 字段不同 → PASS。
        """
        # 构造 mock 诊断 (模拟 sdk.get_mock_response 的输出, 修复后标记 source='mock')
        mock_result = AIGovernanceResult(
            is_fixable=True,
            reasoning="mock reasoning",
            confidence_score=0.95,
            patch_proposal=PatchProposal(
                target_function="fn",
                suggested_code="pass",
                patch_type=PatchType.FUNCTIONAL,
            ),
            source="mock",  # 修复后: mock 诊断标记来源
        )

        # 构造真实 LLM 诊断
        llm_result = AIGovernanceResult(
            is_fixable=True,
            reasoning="real llm reasoning",
            confidence_score=0.92,
            patch_proposal=PatchProposal(
                target_function="fn",
                suggested_code="pass",
                patch_type=PatchType.FUNCTIONAL,
            ),
        )

        mock_dump = mock_result.model_dump()
        llm_dump = llm_result.model_dump()

        # 两者必须可通过 source 字段区分
        assert mock_dump.get("source") != llm_dump.get("source"), (
            f"mock 与 llm 诊断不可区分: mock.source={mock_dump.get('source')}, "
            f"llm.source={llm_dump.get('source')} — "
            "AIGovernanceResult 缺 source 字段, 下游无法区分真假诊断 (P0)"
        )
        assert mock_dump.get("source") == "mock", (
            f"mock 诊断 source 应为 'mock', 实际: {mock_dump.get('source')}"
        )
