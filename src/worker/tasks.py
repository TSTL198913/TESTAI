import logging
import time

from src.core.loop_manager import AsyncLoopManager
from src.core.tracer import reset_trace_id, set_trace_id
from src.governance.orchestrator import GovernanceOrchestrator
from src.governance.models import DiagnosticContext
from src.worker.celery_app import celery_app


@celery_app.task(bind=True, name="tasks.run_test_pipeline")
def run_test_pipeline(self, request_dict: dict):
    token = set_trace_id(self.request.id)
    execution_context = None

    async def _execute():
        nonlocal execution_context

        # 隔离解耦: engine 模块 lazy import, 使治理核心不硬依赖测试执行引擎。
        # engine 不可用时 _execute() 抛 ImportError → except 块 → 走 governance 路径。
        from src.core.container import ResourceContainer
        from src.core.context import ExecutionContext
        from src.engine.pipeline import ExecutionPipeline
        from src.engine.registry import get_pipeline

        client = await ResourceContainer.get_client()
        repo = await ResourceContainer.get_repo()

        pipeline_config = request_dict.get("pipeline", ["data", "request", "assertion"])
        processors = get_pipeline(pipeline_config)
        pipeline = ExecutionPipeline(processors=processors)

        execution_context = ExecutionContext(
            case_id=request_dict.get("case_id", "default_case"),
            env=request_dict.get("env", {}),
            vars=request_dict.get("vars", {}),
            results={},
        )

        await pipeline.run(execution_context, request_dict.get("steps", []), client)
        await repo.save_execution(execution_context.case_id, execution_context.results)
        return "Success"

    try:
        future = AsyncLoopManager.run_coroutine(_execute())
        return future.result(timeout=60)
    except Exception as e:
        try:

            async def _governance(err):
                diag_context = DiagnosticContext(
                    step_id=request_dict.get("case_id", "unknown"),
                    component_name="pipeline",
                    input_data=request_dict,
                    actual_output=str(err),
                    expected_baseline=None,
                    exception_trace=str(err),
                )
                # P0 修复: 异常 fallback 走 orchestrator 六步闭环 (分类→诊断→审批→Git→补丁→收敛)
                # 而非只调 agent 做诊断。orchestrator 内部分类器作为触发策略:
                #   RETRY/MANUAL_REQUIRED → SKIPPED (轻量)
                #   AI_DIAGNOSE → 诊断 → 审批闸门 → 大部分 PENDING_APPROVAL (人工)
                orchestrator = GovernanceOrchestrator()
                governance_result = await orchestrator.execute_governance_flow(diag_context)
                return governance_result

            gov_future = AsyncLoopManager.run_coroutine(_governance(e))
            return gov_future.result(timeout=60)
        except Exception as ai_err:
            logging.error(f"AI Governance Failed: {ai_err}", exc_info=True)
            raise e
    finally:
        reset_trace_id(token)
