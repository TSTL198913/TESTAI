# src/engine/processor/governance_processor.py
from src.engine.processor.base import BaseProcessor
from src.governance.models import DiagnosticContext
from src.governance.orchestrator import GovernanceOrchestrator


def _get_validation_passed(validation_result) -> bool:
    """安全读取 validation_result 的 passed 字段。

    兼容两种形式:
    - dict: ``{"passed": True/False, ...}`` (来自 step_result.get, 最常见)
    - 对象: 具有 ``passed`` 属性 (兼容旧式对象形式)

    Args:
        validation_result: dict 或具有 passed 属性的对象

    Returns:
        bool: passed 值; 若无法读取则默认 True (不触发治理)
    """
    if validation_result is None:
        return True
    if isinstance(validation_result, dict):
        return validation_result.get("passed", True)
    return getattr(validation_result, "passed", True)


def _get_validation_errors(validation_result) -> list:
    """安全读取 validation_result 的 errors 字段, 兼容 dict/对象形式。"""
    if validation_result is None:
        return []
    if isinstance(validation_result, dict):
        return validation_result.get("errors", [])
    return list(getattr(validation_result, "errors", []) or [])


class GovernanceProcessor(BaseProcessor):
    def __init__(self):
        super().__init__()
        self.engine = GovernanceOrchestrator()

    async def process(self, context, step, client):
        step_result = context.results.get(step.step_id, {})

        validation_result = step_result.get("validation_result")
        is_failed = step_result.get("status") == "FAILED"
        error = step_result.get("error")

        should_trigger = False
        errors = []

        # P2-4 修复: validation_result 可能是 dict (来自 step_result.get),
        # 用 dict 访问代替 .passed 属性访问, 避免 AttributeError。
        # 同时兼容对象形式 (有 passed 属性)。
        if validation_result and not _get_validation_passed(validation_result):
            should_trigger = True
            errors = _get_validation_errors(validation_result)
        elif is_failed and error:
            should_trigger = True
            errors = [str(error)]

        if should_trigger:
            self.logger.warning(f"Governance triggered for {step.step_id}")

            diagnostic_context = DiagnosticContext(
                step_id=step.step_id,
                component_name=(
                    step.processor if hasattr(step, "processor") else "pipeline"
                ),
                input_data=(
                    step.model_dump() if hasattr(step, "model_dump") else str(step)
                ),
                actual_output=step_result.get("body"),
                expected_baseline=step_result.get("expected_baseline"),
                exception_trace="; ".join(errors),
            )

            insight = await self.engine.execute_governance_flow(diagnostic_context)
            context.results[step.step_id]["governance_insight"] = insight

        return step
