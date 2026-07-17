import logging
import time

from src.core.container import ResourceContainer
from src.core.context import ExecutionContext
from src.core.loop_manager import AsyncLoopManager
from src.core.tracer import reset_trace_id, set_trace_id
from src.engine.pipeline import ExecutionPipeline
from src.engine.registry import get_pipeline
from src.governance.agent import AIGovernanceAgent
from src.governance.models import DiagnosticContext
from src.worker.celery_app import celery_app


@celery_app.task(bind=True, name="tasks.run_test_pipeline")
def run_test_pipeline(self, request_dict: dict):
    token = set_trace_id(self.request.id)
    execution_context = None

    async def _execute():
        nonlocal execution_context

        client = await ResourceContainer.get_client()
        repo = await ResourceContainer.get_repo()

        pipeline_config = request_dict.get("pipeline", ["data", "request", "assertion"])
        processors = get_pipeline(pipeline_config)
        pipeline = ExecutionPipeline(processors=processors)

        execution_context = ExecutionContext(
            case_id=request_dict.get("case_id", "default_case"),
            env=request_dict.get("env", {}),
            vars=request_dict.get("vars", {}),
            results={}
        )

        await pipeline.run(execution_context, request_dict.get("steps", []), client)
        await repo.save_execution(execution_context.case_id, execution_context.results)
        return "Success"

    try:
        future = AsyncLoopManager.run_coroutine(_execute())
        return future.result(timeout=60)
    except Exception as e:
        try:
            async def _governance():
                agent = AIGovernanceAgent()
                diag_context = DiagnosticContext(
                    step_id=request_dict.get("case_id", "unknown"),
                    component_name="pipeline",
                    input_data=request_dict,
                    actual_output=str(e),
                    expected_baseline=None,
                    exception_trace=str(e)
                )
                governance_result = await agent.analyze_with_context(diag_context)
                return governance_result.model_dump()

            gov_future = AsyncLoopManager.run_coroutine(_governance())
            return gov_future.result(timeout=60)
        except Exception as ai_err:
            logging.error(f"AI Governance Failed: {ai_err}", exc_info=True)
            raise e
    finally:
        reset_trace_id(token)
