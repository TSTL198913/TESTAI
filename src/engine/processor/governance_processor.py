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

        if validation_result and not validation_result.passed:
            should_trigger = True
            errors = validation_result.errors
        elif is_failed and error:
            should_trigger = True
            errors = [str(error)]

        if should_trigger:
            self.logger.warning(f"Governance triggered for {step.step_id}")

            diagnostic_context = DiagnosticContext(
                step_id=step.step_id,
                component_name=step.processor if hasattr(step, 'processor') else 'pipeline',
                input_data=step.model_dump() if hasattr(step, 'model_dump') else str(step),
                actual_output=step_result.get("body"),
                expected_baseline=step_result.get("expected_baseline"),
                exception_trace="; ".join(errors)
            )

            insight = await self.engine.execute_governance_flow(diagnostic_context)
            context.results[step.step_id]["governance_insight"] = insight