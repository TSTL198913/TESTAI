# src/engine/processor/grpc.py
from src.core.exceptions import EngineError, InfrastructureError
from src.engine.processor.base import BaseProcessor
from src.models.contract import GrpcRequest
from src.models.result import StepResult

# src/engine/processor/grpc.py
# ... imports 保持不变 ...


class GrpcProcessor(BaseProcessor):  # 修改类名
    _channels = {}

    @classmethod
    def _get_channel(cls, host: str, port: int):
        # ... 逻辑保持不变 ...
        pass

    # 必须接收 client 参数（尽管 gRPC 可能使用单独的 Channel 管理，但为了接口统一，保留 client 位）
    async def process(self, context, step: GrpcRequest, client=None) -> GrpcRequest:
        host = context.env.get("grpc_host", "localhost")
        port = int(context.env.get("grpc_port", 50051))
        channel = self._get_channel(host, port)

        try:
            # ... 执行逻辑 ...
            result = {"message": "Success", "data": step.payload}
            context.results[step.step_id] = StepResult(
                status="PASSED", status_code=200, body=result, error=None
            ).model_dump()
        except Exception as e:
            raise InfrastructureError(f"GRPC Error: {str(e)}") from e

        return step  # 必须返回 step
