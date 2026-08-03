"""P2-4 GovernanceProcessor AttributeError 修复测试。

业务规则（基于代码梳理）：
- governance_processor.process 原用 `validation_result.passed` / `.errors`，
  但 validation_result 是 dict（来自 step_result.get），dict 无 .passed 属性，
  触发 AttributeError。当前因 validation_result 键无写入（死分支）未暴露，
  一旦上游写入 dict 即崩溃。
- 修复后：用 dict 访问（isinstance 兼容对象形式），不抛 AttributeError。

覆盖：正向(dict失败触发)/边界(passed True/空dict/None+FAILED)/异常/兼容(对象形式)。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.engine.processor.governance_processor import GovernanceProcessor


def _make_processor():
    p = GovernanceProcessor()
    p.engine = MagicMock()
    p.engine.execute_governance_flow = AsyncMock(return_value={"status": "DIAGNOSED"})
    return p


def _make_step(step_id="s1"):
    step = MagicMock()
    step.step_id = step_id
    step.processor = "TestProcessor"
    step.model_dump = MagicMock(return_value={})
    return step


class TestGovernanceProcessorAttributeError:
    """AttributeError 修复：覆盖正向/边界/异常/依赖"""

    @pytest.mark.asyncio
    async def test_dict_validation_failed_triggers_governance(self):
        """正向：dict {passed:False} 触发治理，不抛 AttributeError"""
        processor = _make_processor()
        context = MagicMock()
        context.results = {
            "s1": {"validation_result": {"passed": False, "errors": ["assertion failed"]}}
        }
        step = _make_step()

        await processor.process(context, step, None)

        processor.engine.execute_governance_flow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dict_validation_passed_does_not_trigger(self):
        """边界：dict {passed:True} 不触发治理"""
        processor = _make_processor()
        context = MagicMock()
        context.results = {"s1": {"validation_result": {"passed": True}}}
        step = _make_step()

        await processor.process(context, step, None)

        processor.engine.execute_governance_flow.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dict_without_passed_key_does_not_trigger(self):
        """边界：dict 无 passed 键（默认 True）不触发"""
        processor = _make_processor()
        context = MagicMock()
        context.results = {"s1": {"validation_result": {"errors": []}}}
        step = _make_step()

        await processor.process(context, step, None)

        processor.engine.execute_governance_flow.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_none_validation_with_failed_status_triggers(self):
        """边界：无 validation_result + status FAILED + error → 触发（is_failed 分支）"""
        processor = _make_processor()
        context = MagicMock()
        context.results = {"s1": {"status": "FAILED", "error": "boom"}}
        step = _make_step()

        await processor.process(context, step, None)

        processor.engine.execute_governance_flow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passed_status_no_trigger(self):
        """边界：status PASSED 不触发"""
        processor = _make_processor()
        context = MagicMock()
        context.results = {"s1": {"status": "PASSED"}}
        step = _make_step()

        await processor.process(context, step, None)

        processor.engine.execute_governance_flow.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_object_form_validation_compatible(self):
        """兼容：对象形式 validation_result（有 passed 属性）也能触发"""
        processor = _make_processor()
        context = MagicMock()

        class VR:
            passed = False
            errors = ["obj error"]

        context.results = {"s1": {"validation_result": VR()}}
        step = _make_step()

        await processor.process(context, step, None)

        processor.engine.execute_governance_flow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_errors_passed_to_diagnostic_context(self):
        """依赖：validation errors 正确传入 DiagnosticContext.exception_trace"""
        processor = _make_processor()
        context = MagicMock()
        context.results = {
            "s1": {"validation_result": {"passed": False, "errors": ["errA", "errB"]}}
        }
        step = _make_step()

        await processor.process(context, step, None)

        call_args = processor.engine.execute_governance_flow.call_args
        diag_ctx = call_args.args[0]
        # errors 被拼接进 exception_trace
        assert "errA" in diag_ctx.exception_trace
        assert "errB" in diag_ctx.exception_trace
