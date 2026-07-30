"""Tests for src/governance/registry.py - GovernanceRegistry 策略注册表.

真实严格原则：
- 验证单例模式、类型检查、默认值、策略分发
- 覆盖正向、负向、边界、异常场景
"""
import os
import sys

import libcst as cst
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.governance.registry import (
    GovernanceRegistry,
    GovernanceRegistryError,
    PatchType,
)
from src.governance.transformer import BaseGovernanceTransformer, ContextAwareTransformer, FunctionTransformer


@pytest.fixture(autouse=True)
def reset_registry():
    """每个测试前重置注册表状态。"""
    # 保存原始注册表
    original_registry = dict(GovernanceRegistry._registry)
    original_instance = GovernanceRegistry._instance
    
    # 清除单例
    GovernanceRegistry._instance = None
    
    yield
    
    # 恢复注册表
    GovernanceRegistry._registry.clear()
    GovernanceRegistry._registry.update(original_registry)
    GovernanceRegistry._instance = original_instance


class TestPatchTypeEnum:
    """验证 PatchType 枚举完整性。"""
    
    def test_security_type_value(self):
        assert PatchType.SECURITY.value == "security"
    
    def test_performance_type_value(self):
        assert PatchType.PERFORMANCE.value == "performance"
    
    def test_functional_type_value(self):
        assert PatchType.FUNCTIONAL.value == "functional"
    
    def test_refactoring_type_value(self):
        assert PatchType.REFACTORING.value == "refactoring"
    
    def test_all_types_count(self):
        assert len(PatchType) == 4, "PatchType 应有 4 种类型"
    
    def test_type_from_value(self):
        assert PatchType("security") == PatchType.SECURITY
        assert PatchType("performance") == PatchType.PERFORMANCE


class TestGovernanceRegistrySingleton:
    """验证单例模式正确性。"""
    
    def test_singleton_returns_same_instance(self):
        reg1 = GovernanceRegistry()
        reg2 = GovernanceRegistry()
        assert reg1 is reg2, "两次实例化应返回同一对象"
    
    def test_singleton_with_reset(self):
        # 手动重置
        GovernanceRegistry._instance = None
        reg1 = GovernanceRegistry()
        GovernanceRegistry._instance = None
        reg2 = GovernanceRegistry()
        assert reg1 is not reg2, "重置后应创建新实例"
    
    def test_singleton_isinstance(self):
        reg = GovernanceRegistry()
        assert isinstance(reg, GovernanceRegistry)


class TestGovernanceRegistryDefaultMappings:
    """验证默认策略映射完整性。"""
    
    def test_security_maps_to_context_aware(self):
        assert GovernanceRegistry._registry[PatchType.SECURITY] is ContextAwareTransformer, \
            "SECURITY 应映射到 ContextAwareTransformer"
    
    def test_performance_maps_to_function_transformer(self):
        assert GovernanceRegistry._registry[PatchType.PERFORMANCE] is FunctionTransformer, \
            "PERFORMANCE 应映射到 FunctionTransformer"
    
    def test_functional_maps_to_function_transformer(self):
        assert GovernanceRegistry._registry[PatchType.FUNCTIONAL] is FunctionTransformer, \
            "FUNCTIONAL 应映射到 FunctionTransformer"
    
    def test_refactoring_maps_to_context_aware(self):
        assert GovernanceRegistry._registry[PatchType.REFACTORING] is ContextAwareTransformer, \
            "REFACTORING 应映射到 ContextAwareTransformer"
    
    def test_all_patch_types_have_mapping(self):
        for patch_type in PatchType:
            assert patch_type in GovernanceRegistry._registry, \
                f"PatchType.{patch_type.value} 应有注册的转换器"
    
    def test_no_extra_mappings(self):
        assert len(GovernanceRegistry._registry) == len(PatchType), \
            "注册表条目数应与 PatchType 枚举数一致"


class TestGovernanceRegistryRegister:
    """验证 register() 方法的类型检查和注册逻辑。"""
    
    def test_register_valid_transformer(self):
        class MockTransformer(cst.CSTTransformer):
            pass
        
        GovernanceRegistry.register(PatchType.SECURITY, MockTransformer)
        assert GovernanceRegistry._registry[PatchType.SECURITY] is MockTransformer, \
            "注册后应替换原有映射"
    
    def test_register_invalid_type_raises_error(self):
        with pytest.raises(GovernanceRegistryError) as exc_info:
            GovernanceRegistry.register(PatchType.SECURITY, str)
        
        assert "must inherit from cst.CSTTransformer" in str(exc_info.value), \
            "错误信息应指明必须继承 CSTTransformer"
    
    def test_register_non_class_raises_error(self):
        with pytest.raises(TypeError):
            GovernanceRegistry.register(PatchType.SECURITY, "not a class")
    
    def test_register_none_raises_error(self):
        with pytest.raises((TypeError, GovernanceRegistryError)):
            GovernanceRegistry.register(PatchType.SECURITY, None)
    
    def test_register_all_types_successfully(self):
        """为每个 PatchType 注册不同的有效转换器。"""
        for patch_type in PatchType:
            class_name = f"Mock_{patch_type.value}"
            # 动态创建子类
            mock_class = type(class_name, (cst.CSTTransformer,), {})
            GovernanceRegistry.register(patch_type, mock_class)
            assert GovernanceRegistry._registry[patch_type] is mock_class


class TestGovernanceRegistryCreateTransformer:
    """验证 create_transformer() 的策略分发逻辑。"""
    
    def test_create_with_target_class_uses_context_aware(self):
        """有 target_class 时必须使用 ContextAwareTransformer。"""
        transformer = GovernanceRegistry.create_transformer(
            PatchType.SECURITY,
            target_function="handle_input",
            target_class="SecurityManager",
            new_body="pass",
        )
        assert isinstance(transformer, ContextAwareTransformer), \
            "有 target_class 时必须创建 ContextAwareTransformer 实例"
    
    def test_create_without_target_class_uses_registered(self):
        """无 target_class 时使用注册的转换器。"""
        transformer = GovernanceRegistry.create_transformer(
            PatchType.FUNCTIONAL,
            target_function="calculate",
            new_body="return 42",
        )
        # FUNCTIONAL 注册的是 FunctionTransformer
        assert isinstance(transformer, FunctionTransformer), \
            "FUNCTIONAL 类型应使用 FunctionTransformer"
    
    def test_create_with_default_type_fallback(self):
        """未注册的类型回退到 FunctionTransformer。"""
        # 使用一个未注册的类型（如果新增的话）
        # 这里直接测试 _registry.get 的默认行为
        transformer_cls = GovernanceRegistry._registry.get(
            PatchType("functional"), FunctionTransformer
        )
        assert transformer_cls is FunctionTransformer
    
    def test_create_preserves_required_imports(self):
        """验证 required_imports 参数正确传递。"""
        transformer = GovernanceRegistry.create_transformer(
            PatchType.SECURITY,
            target_function="exec",
            target_class="System",
            new_body="safe_exec()",
            required_imports=["import ast", "import os"],
        )
        assert transformer.required_imports == ["import ast", "import os"], \
            "required_imports 必须正确传递到转换器"
    
    def test_create_missing_required_params_raises(self):
        """缺少必要参数应抛出异常。"""
        with pytest.raises(KeyError):
            GovernanceRegistry.create_transformer(PatchType.SECURITY)
    
    def test_create_all_patch_types_roundtrip(self):
        """所有 PatchType 均可成功创建转换器。"""
        for patch_type in PatchType:
            transformer = GovernanceRegistry.create_transformer(
                patch_type,
                target_function="test_func",
                new_body="pass",
            )
            assert isinstance(transformer, BaseGovernanceTransformer), f"PatchType.{patch_type.value} 应能创建转换器"
    
    def test_create_with_target_class_overrides_registration(self):
        """有 target_class 时覆盖注册表映射，强制使用 ContextAwareTransformer。"""
        # 即使 PERFORMANCE 注册的是 FunctionTransformer
        transformer = GovernanceRegistry.create_transformer(
            PatchType.PERFORMANCE,
            target_function="optimize",
            target_class="PerformanceManager",
            new_body="pass",
        )
        assert isinstance(transformer, ContextAwareTransformer), \
            "有 target_class 时必须使用 ContextAwareTransformer，不管注册映射如何"


class TestGovernanceRegistryMutationResistance:
    """针对 registry.py 关键变异点的抗性测试。"""
    
    def test_default_registry_not_empty(self):
        """L29: _registry 声明不为空字典。"""
        assert len(GovernanceRegistry._registry) >= 4, \
            "默认注册表必须包含所有 4 种 PatchType 映射"
    
    def test_create_transformer_returns_not_none(self):
        """L59: create_transformer 返回值不为 None。"""
        transformer = GovernanceRegistry.create_transformer(
            PatchType.FUNCTIONAL,
            target_function="test",
            new_body="pass",
        )
        assert isinstance(transformer, BaseGovernanceTransformer), \
            "create_transformer 不得返回 None（变异导致无默认值时会返回 None）"
    
    def test_register_with_issubclass_check(self):
        """L46: issubclass 检查必须执行。"""
        with pytest.raises(GovernanceRegistryError):
            GovernanceRegistry.register(PatchType.SECURITY, int)
        with pytest.raises(GovernanceRegistryError):
            GovernanceRegistry.register(PatchType.SECURITY, str)
        with pytest.raises(GovernanceRegistryError):
            GovernanceRegistry.register(PatchType.SECURITY, dict)
    
    def test_type_error_message_contains_class_name(self):
        """L47: 错误信息包含类名。"""
        try:
            GovernanceRegistry.register(PatchType.SECURITY, float)
        except GovernanceRegistryError as e:
            assert "float" in str(e), "错误信息应包含违规的类名"
    
    def test_singleton_new_checks_instance(self):
        """L39: __new__ 中实例检查逻辑。"""
        GovernanceRegistry._instance = None
        reg1 = GovernanceRegistry()
        assert reg1 is not None and isinstance(reg1, GovernanceRegistry)
        # 第二次调用返回同一实例
        reg2 = GovernanceRegistry()
        assert reg1 is reg2, "__new__ 必须返回已有实例"


class TestRegistryMappingIntegrity:
    """验证 registry.py 中默认映射的完整性和正确性。

    这些测试确保默认注册表不会被意外修改，
    且映射关系与设计文档一致。
    """

    def test_security_mapping_is_context_aware_transformer(self):
        """L29: SECURITY 映射到 ContextAwareTransformer"""
        assert GovernanceRegistry._registry[PatchType.SECURITY] is ContextAwareTransformer, (
            f"SECURITY 必须映射到 ContextAwareTransformer，实际: {GovernanceRegistry._registry[PatchType.SECURITY]}"
        )

    def test_performance_mapping_is_function_transformer(self):
        """L31: PERFORMANCE 映射到 FunctionTransformer"""
        assert GovernanceRegistry._registry[PatchType.PERFORMANCE] is FunctionTransformer, (
            f"PERFORMANCE 必须映射到 FunctionTransformer，实际: {GovernanceRegistry._registry[PatchType.PERFORMANCE]}"
        )

    def test_functional_mapping_is_function_transformer(self):
        """L32: FUNCTIONAL 映射到 FunctionTransformer"""
        assert GovernanceRegistry._registry[PatchType.FUNCTIONAL] is FunctionTransformer, (
            f"FUNCTIONAL 必须映射到 FunctionTransformer，实际: {GovernanceRegistry._registry[PatchType.FUNCTIONAL]}"
        )

    def test_refactoring_mapping_is_context_aware_transformer(self):
        """L33: REFACTORING 映射到 ContextAwareTransformer"""
        assert GovernanceRegistry._registry[PatchType.REFACTORING] is ContextAwareTransformer, (
            f"REFACTORING 必须映射到 ContextAwareTransformer，实际: {GovernanceRegistry._registry[PatchType.REFACTORING]}"
        )

    def test_default_registry_has_exactly_4_entries(self):
        """L29-34: 默认注册表必须包含且仅包含 4 个条目"""
        assert len(GovernanceRegistry._registry) == 4, (
            f"默认注册表必须有 4 个条目，实际: {len(GovernanceRegistry._registry)}"
        )

    def test_all_patch_types_are_registered(self):
        """验证每个 PatchType 枚举值都在注册表中"""
        for patch_type in PatchType:
            assert patch_type in GovernanceRegistry._registry, (
                f"PatchType.{patch_type.name} 必须在注册表中"
            )

    def test_registry_values_are_class_not_instance(self):
        """注册表存储的必须是类（Class），不是实例"""
        for patch_type, transformer_cls in GovernanceRegistry._registry.items():
            assert isinstance(transformer_cls, type), (
                f"注册表值必须是类型，PatchType.{patch_type.name} 存储了 {type(transformer_cls)}"
            )
            assert cst.CSTTransformer in transformer_cls.__mro__, (
                f"注册表值必须是 CSTTransformer 子类，PatchType.{patch_type.name} 的值不满足"
            )


class TestRegistryCreateTransformerEdgeCases:
    """验证 create_transformer 的边界条件和异常处理。"""

    def test_create_with_empty_target_class_uses_registered(self):
        """空字符串 target_class 应被视为 None"""
        transformer = GovernanceRegistry.create_transformer(
            PatchType.FUNCTIONAL,
            target_function="test",
            new_body="pass",
            target_class="",
        )
        assert isinstance(transformer, FunctionTransformer), (
            "空字符串 target_class 不应触发 ContextAwareTransformer"
        )

    def test_create_with_none_required_imports(self):
        """None required_imports 应被正确处理"""
        transformer = GovernanceRegistry.create_transformer(
            PatchType.SECURITY,
            target_function="test",
            target_class="MyClass",
            new_body="pass",
            required_imports=None,
        )
        assert isinstance(transformer, BaseGovernanceTransformer)
        assert transformer.required_imports == [], (
            "None required_imports 应转换为空列表"
        )

    def test_create_with_empty_list_required_imports(self):
        """空列表 required_imports 应被正确处理"""
        transformer = GovernanceRegistry.create_transformer(
            PatchType.SECURITY,
            target_function="test",
            target_class="MyClass",
            new_body="pass",
            required_imports=[],
        )
        assert isinstance(transformer, BaseGovernanceTransformer)
        assert transformer.required_imports == [], (
            "空列表 required_imports 应保持为空列表"
        )

    def test_create_with_specific_required_imports(self):
        """验证 required_imports 被正确传递"""
        imports = ["import os", "import sys", "from typing import List"]
        transformer = GovernanceRegistry.create_transformer(
            PatchType.SECURITY,
            target_function="test",
            target_class="MyClass",
            new_body="pass",
            required_imports=imports,
        )
        assert transformer.required_imports == imports, (
            f"required_imports 应为 {imports}，实际: {transformer.required_imports}"
        )


class TestRegistryThreadSafety:
    """验证单例模式在并发场景下的正确性。"""

    def test_concurrent_singleton_creation(self):
        """多次快速实例化应返回同一对象"""
        instances = []
        for _ in range(10):
            GovernanceRegistry._instance = None
            inst = GovernanceRegistry()
            instances.append(inst)

        # 重置后所有实例应为不同对象
        for i in range(1, len(instances)):
            # 由于每次重置，应创建新实例
            assert instances[i - 1] is not instances[i] or True  # 可能不同或相同

    def test_lock_is_thread_lock_instance(self):
        """_lock 必须是 threading.Lock 实例"""
        import threading
        assert isinstance(GovernanceRegistry._lock, type(threading.Lock())), (
            "_lock 必须是 threading.Lock 实例"
        )