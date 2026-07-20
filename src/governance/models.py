# src/governance/models.py
from enum import Enum
from typing import Any, Dict, List, Optional

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
