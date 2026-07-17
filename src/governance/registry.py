# src/governance/registry.py
import logging
import threading
from enum import Enum
from typing import Dict, Type, Any, Optional
import libcst as cst

from src.governance.transformer import ContextAwareTransformer, FunctionTransformer


# 1. 明确的分类：基于策略模式 (Strategy Pattern)
class PatchType(Enum):
    SECURITY = "security"
    PERFORMANCE = "performance"
    FUNCTIONAL = "functional"
    REFACTORING = "refactoring"


class GovernanceRegistryError(Exception):
    """治理注册表异常"""
    pass


class GovernanceRegistry:
    _instance = None
    _lock = threading.Lock()
    _registry: Dict[PatchType, Type[cst.CSTTransformer]] = {}

    def __new__(cls):
        """单例模式：确保治理策略在全局唯一"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GovernanceRegistry, cls).__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, patch_type: PatchType, transformer_cls: Type[cst.CSTTransformer]):
        """注册策略：加入严苛的类型检查"""
        if not issubclass(transformer_cls, cst.CSTTransformer):
            raise GovernanceRegistryError(f"Class {transformer_cls.__name__} must inherit from cst.CSTTransformer")

        with cls._lock:
            cls._registry[patch_type] = transformer_cls
            logging.info(f"Governance Policy Registered: {patch_type.value} -> {transformer_cls.__name__}")

    @staticmethod
    def create_transformer(patch_type: PatchType, **kwargs):
        # 如果提供了 target_class，强制使用 ContextAwareTransformer
        if kwargs.get('target_class'):
            return ContextAwareTransformer(
                target_function=kwargs['target_function'],
                target_class=kwargs['target_class'],
                new_body=kwargs['new_body'],
                required_imports=kwargs.get('required_imports')
            )
        # 默认回退到标准 FunctionTransformer
        return FunctionTransformer(
            target_function=kwargs['target_function'],
            new_body=kwargs['new_body'],
            required_imports=kwargs.get('required_imports')
        )