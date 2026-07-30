# src/engine/processor/grpc.py
from typing import Any
from src.core.exceptions import EngineError, InfrastructureError
from src.engine.processor.base import BaseProcessor
from src.models.contract import GrpcRequest
from src.models.result import StepResult

# src/engine/processor/grpc.py
# ... imports 保持不变 ...


class GrpcProcessor(BaseProcessor):
    _channels: dict[tuple[str, int], Any] = {}

    @classmethod
    def _get_channel(cls, host: str, port: int):
        key = (host, port)
        if key not in cls._channels:
            # P0-5 修复: 不返回空实现，抛出 NotImplementedError
            # gRPC 生产环境未实现，诚实报错而非假成功
            raise NotImplementedError(
                f"gRPC channel not implemented for {host}:{port}. "
                f"GrpcProcessor requires actual gRPC infrastructure. "
                f"If you need gRPC support, implement _get_channel() with grpc.insecure_channel()."
            )
        return cls._channels[key]

    async def process(self, context, step: GrpcRequest, client=None) -> GrpcRequest:
        host = context.env.get("grpc_host", "localhost")
        port = int(context.env.get("grpc_port", 50051))
        
        # P0-5 修复: 当 gRPC 不可用时抛出异常，而非假成功
        try:
            channel = self._get_channel(host, port)
        except NotImplementedError as e:
            raise EngineError(
                f"gRPC step '{step.step_id}' failed: {str(e)}"
            ) from e

        try:
            # 真实 gRPC 调用应在此处执行
            # 当前未实现，抛出异常而非返回假成功
            raise NotImplementedError(
                f"gRPC call not implemented for method '{step.method}'. "
                f"GrpcProcessor.process() requires actual gRPC stub implementation."
            )
        except NotImplementedError:
            # 转换为业务异常
            raise
        except Exception as e:
            raise InfrastructureError(f"GRPC Error: {str(e)}") from e
