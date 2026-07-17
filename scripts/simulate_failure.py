import asyncio
import copy
import json
import logging
import os

from src.core.config import settings

from src.governance.models import DiagnosticContext
from src.governance.orchestrator import GovernanceOrchestrator
from tests.utils.validator import EvaluationValidator

# 配置日志，以便观察治理引擎的决策过程
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GovernanceSimulator")

# 【强制覆写】：在程序运行的当前进程中，强行将 Key 修改为您正确的 Key
# os.environ["DEEPSEEK_API_KEY"] = "sk-12e576f56c644eecbdc391a79d936bbd"
# os.environ["DEEPSEEK_API_KEY"] = "sk-12e576f56c644eecbdc394321d936bbd"

# from src.core.config import settings
# # 此时打印出来的一定是您的真实 Key
# print(f"DEBUG: 强制修正后，API Key 为: {settings.DEEPSEEK_API_KEY}")


async def simulate_governance_failure():
    # 1. 初始化引擎与校验器
    validator = EvaluationValidator()
    engine = GovernanceOrchestrator()

    logger.info("--- 开始治理流程模拟 ---")

    # 2. 从 Golden Baseline 加载一个场景
    scenario_id = "golden_sec_normal_001"
    raw_scenario = validator.get_scenario(scenario_id)
    corrupted_data = copy.deepcopy(raw_scenario["expected_output"])

    # 3. [注入故障] 将安全分值从高（正常）修改为极低（触发警报）
    # 原始正常值 > 0.9，我们将其篡改为 0.1
    corrupted_data["data"]["score"] = 0.1
    corrupted_data["data"]["data"]["overall_score"] = 0.1
    logger.warning(f"故障注入：Scenario {scenario_id} 分数已被篡改为 0.1")

    # 4. 执行校验 (Trigger)
    result = validator.validate(corrupted_data, scenario_id)

    if not result.passed:
        logger.error(f"校验失败：{result.errors}")

        # 5. 构造诊断上下文 (Disease Context)
        # 构造完整的诊断对象 (直接对齐 DiagnosticContext 定义)
        diagnostic_context = DiagnosticContext(
            step_id=scenario_id,
            component_name="eval_platform",
            # 填补模型缺失的字段
            input_data=raw_scenario["input"],  # 必须：原始输入数据
            expected_baseline=raw_scenario["expected_output"],  # 必须：预期基准
            # 填充已有的字段
            actual_output=corrupted_data,
            exception_trace="; ".join(result.errors),  # 将错误信息映射到异常追踪
            system_metrics={"severity": "high"}  # 可以为空，但符合模型结构
        )

        # 6. [治理介入] 调用 AI 专家
        logger.info("正在调用 GovernanceEngine 进行诊断...")
        try:
            insight = await engine.handle_exception(
                Exception("Baseline Violation"),
                diagnostic_context
            )

            logger.info("--- 治理诊断报告 ---")
            if insight:
                print(insight.model_dump_json(indent=2))
            else:
                print("治理引擎未返回有效报告")

        except Exception as e:
            logger.error(f"治理引擎执行异常: {e}")
    else:
        logger.error("模拟失败：校验器未检测到异常！")


if __name__ == "__main__":
    asyncio.run(simulate_governance_failure())