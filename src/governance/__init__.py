# src/governance/__init__.py
from src.governance.registry import GovernanceRegistry, PatchType
from src.governance.transformer import FunctionTransformer  # 引入你的 Transformer


# 自动注册策略
def bootstrap_governance():
    GovernanceRegistry.register(PatchType.FUNCTIONAL, FunctionTransformer)
    # 如果有新的 Transformer，只需在这里添加一行
    # GovernanceRegistry.register(PatchType.SECURITY, SecurityTransformer)

bootstrap_governance()

from .orchestrator import GovernanceOrchestrator

# ... 其他导出 ...
