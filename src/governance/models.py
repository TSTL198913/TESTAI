# src/governance/models.py
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from pydantic.dataclasses import dataclass

from src.governance import PatchType


# 1. 定义嵌套的修复方案结构，让代码更具可读性
class PatchProposal(BaseModel):
    target_function: str
    target_class: Optional[str] = None  # 新增：类名约束
    suggested_code: str
    # 【强制要求】：补丁必须显式声明依赖，否则拒绝执行
    required_imports: list[str] = Field(default_factory=list)
    patch_type: PatchType = PatchType.FUNCTIONAL  # 默认值防止 AI 遗漏


class AIGovernanceResult(BaseModel):
    is_fixable: bool
    reasoning: str
    root_cause: Optional[str] = None
    patch_proposal: Optional[PatchProposal] = None
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    # P0 修复: 标记诊断来源, 下游可区分 mock/llm/fallback, 防止假诊断触发自动批准
    source: Literal["llm", "mock", "fallback"] = "llm"


class DiagnosticContext(BaseModel):
    # 核心元数据
    step_id: str
    component_name: str

    # 逻辑上下文 (这是修复算法错误的关键)
    input_data: Any  # 评测平台的输入
    actual_output: Any  # 评测平台的实际运行结果
    expected_baseline: Any  # 预期基准结果

    # 运行时数据
    exception_trace: Optional[str] = None
    system_metrics: Dict[str, Any] = Field(default_factory=dict)


@dataclass
class PatchAction:
    file_path: str
    target_function: str
    target_class: str
    suggested_code: str
    required_imports: List[str]


class GovernanceAction(Enum):
    RETRY = "system_retry"
    AI_DIAGNOSE = "ai_diagnose"
    ABORT = "manual_intervention"
    FIXED = "fixed"
    MANUAL_REQUIRED = "manual_required"


class DecisionContextInput(BaseModel):
    """AutoDecisionEngine.evaluate 的跨模块通信强校验模型。

    规则: 跨模块通信必须引入 Pydantic 模型进行强校验, 禁止弱类型隐式转换。
    orchestrator 构造此模型实例 (强校验), 再 .model_dump() 传给 engine.evaluate()
    (engine 签名 Dict[str, Any] 保持不变, 向后兼容现有 40+ 测试)。

    字段语义对应 AutoDecisionEngine 的规则条件:
    - confidence: 诊断置信度, 触发 rule_auto_approve_high_confidence(>=0.9)/rule_reject_low_confidence(<0.5)
    - is_fixable: 是否可修复, 高置信自动批准要求 is_fixable=True
    - source: 诊断来源 llm/mock/fallback, mock/fallback 不自动批准 (P0 守卫)
    - patch_type: 补丁类型, 触发 rule_security_requires_manual
    - consecutive_failures: 连续失败次数, 触发 rule_escalate_multiple_failures(>=3)
    - patch_category: 补丁分类, 触发 rule_auto_approve_known_pattern
    - status: 流程状态, 触发 rule_auto_rollback_on_diverge(DIVERGED)
    """

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    is_fixable: bool = False
    source: Literal["llm", "mock", "fallback"] = "llm"
    patch_type: str = "functional"
    consecutive_failures: int = Field(default=0, ge=0)
    patch_category: str = ""
    status: str = ""
