from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class Assertion(BaseModel):
    """
    定义测试执行后的验证逻辑，作为 TestStep 的组成部分。
    """
    check: str = Field(..., description="校验类型，例如: status_code, jsonpath, grpc_code")
    operator: Literal["eq", "contains", "regex", "gt", "lt"] = Field("eq", description="比较操作符")
    path: Optional[str] = None
    expected: Any = Field(..., description="预期的期望值")
    message: Optional[str] = Field(None, description="断言失败时的语义化提示，用于报告展示")

    model_config = ConfigDict(frozen=True)