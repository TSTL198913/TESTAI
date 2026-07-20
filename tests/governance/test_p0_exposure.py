import os
import pytest


class TestContextAwareTransformerPatchedFlag:
    """测试 ContextAwareTransformer 的 patched=True 标记"""

    def test_patched_flag_is_set(self):
        import libcst as cst
        from src.governance.transformer import ContextAwareTransformer

        source_code = """
class TargetClass:
    def my_method():
        return 1
"""
        tree = cst.parse_module(source_code)
        transformer = ContextAwareTransformer(
            target_function="my_method",
            new_body="return 2",
            target_class="TargetClass"
        )

        tree = tree.visit(transformer)

        assert transformer.patched is True, "ContextAwareTransformer 补丁标记应设为True"
        assert "return 2" in tree.code, "代码应被替换"


class TestGovernanceProcessorRegistration:
    """测试 GovernanceProcessor 是否正确注册"""

    def test_governance_processor_registered(self):
        from src.engine.registry import _PROCESSOR_MAP

        assert "governance" in _PROCESSOR_MAP, "governance 处理器应注册到 _PROCESSOR_MAP"
        assert _PROCESSOR_MAP["governance"] == "src.engine.processor.governance_processor.GovernanceProcessor", \
            "governance 处理器注册路径不正确"

    def test_governance_processor_can_be_loaded(self):
        from src.engine.registry import get_processor_class

        processor_class = get_processor_class("governance")
        assert processor_class is not None, "governance 处理器类应能被加载"
        assert processor_class.__name__ == "GovernanceProcessor", "加载的处理器类类型不正确"