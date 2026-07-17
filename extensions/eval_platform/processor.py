import logging
from extensions.eval_platform.models import EvalRequestContract
from extensions.eval_platform.client import EvalPlatformClient
from src.engine.processor.base import BaseProcessor
# 引入治理组件
from src.governance.dispatcher import ErrorDispatcher, GovernanceAction
from src.governance.agent import AIGovernanceAgent  # 假设这是您的 AI 诊断执行者

logger = logging.getLogger(__name__)


class EvalPlatformProcessor(BaseProcessor):
    def __init__(self):
        super().__init__()
        self.client = EvalPlatformClient()
        self.agent = AIGovernanceAgent()  # 负责执行 AI_DIAGNOSE

    async def process(self, context, step, client):
        contract = EvalRequestContract(request_body=step.payload)

        try:
            # 正常执行路径...
            result = await self.client.evaluate(contract)
            context.results[step.step_id] = {"status": "COMPLETED", "data": result.dict()}
            return result

        except Exception as e:
            # 【治理分发闭环】
            # 1. 询问 Dispatcher 该怎么办？
            action = ErrorDispatcher.classify(e)
            logger.warning(f"Governance Action Requested: {action.value} for step {step.step_id}")

            # 2. 根据行动指南执行
            if action == GovernanceAction.AI_DIAGNOSE:
                # 只有这里才会调用 AI 进行分析和修复
                diagnosis_result = await self.agent.diagnose_and_repair(
                    exception=e,
                    context_data={"contract": contract.dict()}
                )
                context.results[step.step_id] = {
                    "status": "GOVERNANCE_DIAGNOSED",
                    "action_taken": diagnosis_result
                }

            elif action == GovernanceAction.RETRY:
                # 执行系统重试逻辑...
                pass

            else:
                # 手动介入或 Abort
                context.results[step.step_id] = {"status": "FAILED", "error": str(e)}

            return {"status": "GOVERNANCE_TRIGGERED", "action": action.value}