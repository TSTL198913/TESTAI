# src/core/context.py
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, ConfigDict

class ContextKeys:
    LAST_RESPONSE = "last_response"     

class ExecutionContext(BaseModel):
    """
    测试执行的上下文环境，作为流水线中传递的唯一数据载体。
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 【关键修复】：添加 case_id，并将其设为必填项
    case_id: str = Field(..., description="本次测试运行的唯一标识符 (UUID/TaskID)")

    # 环境配置 (例如 base_url, auth_token)
    env: Dict[str, Any] = Field(default_factory=dict)

    # 动态变量池 (存放测试过程中的中间变量)
    vars: Dict[str, Any] = Field(default_factory=dict)

    # 执行结果 (存放每一步的 response 或 error)
    results: Dict[str, Any] = Field(default_factory=dict)

    # 当前执行中的上下文引用
    current_step_id: Optional[str] = None

    # 扩展建议
    metadata: Dict[str, Any] = Field(default_factory=dict, description="执行任务的元数据，用于审计")