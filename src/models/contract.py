from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, HttpUrl

from .assertion import Assertion


class BaseStep(BaseModel):
    """所有协议请求的抽象基类"""

    # 开启不可变性，确保系统状态一致性
    model_config = ConfigDict(frozen=True)

    step_id: str = Field(..., description="步骤唯一标识")
    description: str = Field(..., description="业务意图描述")
    variables: Dict[str, Any] = Field(default_factory=dict)
    assertions: List[Assertion] = Field(default_factory=list)
    # P3 预留：AI Governance 字段
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="AI 审计与追踪标签"
    )


class HttpRequest(BaseStep):
    protocol: Literal["http"] = "http"
    url: str
    method: Literal["GET", "POST", "PUT", "DELETE"]
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class GrpcRequest(BaseStep):
    protocol: Literal["grpc"] = "grpc"
    proto_file_path: str
    service: str
    method: str
    metadata: Dict[str, str] = Field(default_factory=dict)
    payload: Dict[str, Any]


# 判别式联合模型：这是唯一的入口
TestStep = Annotated[Union[HttpRequest, GrpcRequest], Field(discriminator="protocol")]


class ExecutionCase(BaseModel):
    case_id: str
    name: str
    steps: List[TestStep] = Field(..., description="测试步骤序列")
