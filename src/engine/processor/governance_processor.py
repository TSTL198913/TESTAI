# src/engine/processor/governance_processor.py
from src.engine.processor.base import BaseProcessor
from src.governance.models import DiagnosticContext
from src.governance.orchestrator import GovernanceOrchestrator


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

        # P2-4 修复: validation_result 是 dict，原 `validation_result.passed`
        # 将 dict 当对象访问，触发 AttributeError。改为 dict 访问（兼容对象形式）。
        if validation_result:
            if isinstance(validation_result, dict):
                passed = validation_result.get("passed", True)
            else:
                passed = getattr(validation_result, "passed", True)
            if not passed:
                should_trigger = True
                if isinstance(validation_result, dict):
                    errors = validation_result.get("errors", [])
                else:
                    errors = getattr(validation_result, "errors", [])
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
