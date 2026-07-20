# src/engine/processor/dispatcher.py
from src.engine.processor.base import BaseProcessor
from src.engine.registry import get_processor_instance


class DispatchProcessor(BaseProcessor):
    """
    智能分发器：
    不执行具体逻辑，只负责根据 step.protocol
    动态路由到对应的协议 Processor。
    """

    async def process(self, context, step, client):
        # 1. 动态获取处理器
        # 假设 step.protocol 就是 'http' 或 'grpc'
        protocol = step.protocol.lower()

        try:
            processor = get_processor_instance(protocol)
        except ValueError:
            raise ValueError(f"未找到协议 {protocol} 对应的 Processor")

        # 2. 调用该 Processor 的 process 方法
        # 保持 Pipeline 的链式调用
        return await processor.process(context, step, client)
