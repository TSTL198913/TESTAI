# src/core/exceptions.py
class EngineError(Exception):
    """引擎基类异常 (治理范围)"""
    pass

class VariableMissingError(EngineError):
    """变量未定义异常"""
    pass

class ProcessorError(EngineError):
    """处理器通用异常"""
    pass

# --- 新增基础设施层 ---
class InfrastructureError(Exception):
    """底层基础设施异常 (重试范围)"""
    pass

class NetworkError(InfrastructureError):
    """网络请求失败"""
    pass