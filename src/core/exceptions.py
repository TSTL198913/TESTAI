# src/core/exceptions.py
from typing import List

class EngineError(Exception):
    """引擎基类异常 (治理范围)"""

    pass


class VariableMissingError(EngineError):
    """变量未定义异常"""

    pass


class ProcessorError(EngineError):
    """处理器通用异常"""

    pass


class PipelineError(EngineError):
    """Pipeline执行异常，包含所有子异常"""

    def __init__(self, message: str, errors: List[Exception]):
        super().__init__(message)
        self.errors = errors


# --- 新增基础设施层 ---
class InfrastructureError(Exception):
    """底层基础设施异常 (重试范围)"""

    pass


class NetworkError(InfrastructureError):
    """网络请求失败"""

    pass
