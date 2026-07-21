# tests/governance/test_effectiveness_gate.py
"""
测试有效性反向验证门控

本测试验证测试体系能否检测到已知bug。如果本测试失败，说明测试体系无效。
"""

import os

import pytest


class TestEffectivenessGate:
    """验证测试体系能检测到已知bug"""

    def test_can_detect_patched_flag_missing(self):
        """
        验证测试体系能检测到 NEW-003 问题：
        ContextAwareTransformer 缺失 patched=True
        """
        transformer_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "src", "governance", "transformer.py"
        )

        with open(transformer_path, "r", encoding="utf-8") as f:
            content = f.read()

        has_active_patched = "self.patched = True" in content and "# self.patched = True" not in content

        if has_active_patched:
            import importlib
            import sys

            if "src.governance.transformer" in sys.modules:
                del sys.modules["src.governance.transformer"]

            from src.governance.transformer import ContextAwareTransformer
            import libcst as cst

            source_code = """
class TargetClass:
    def my_method():
        return 1
"""
            tree = cst.parse_module(source_code)
            transformer = ContextAwareTransformer(
                target_function="my_method", new_body="return 2", target_class="TargetClass"
            )
            tree = tree.visit(transformer)

            assert transformer.patched is True, (
                "测试体系无法检测到 NEW-003 bug！\n"
                "当前代码中 self.patched = True 已存在，但测试应该验证它被正确设置。\n"
                "这意味着测试体系无效。"
            )
            print("✅ 测试体系有效性验证通过：self.patched = True 已正确设置")
        else:
            pytest.fail(
                "测试体系无法检测到 NEW-003 bug！\n"
                "当前代码中 self.patched = True 已被注释/删除，但这是一个生产环境问题。\n"
                "请修复 src/governance/transformer.py 中的第32行和第69行。"
            )

    def test_can_detect_missing_governance_processor(self):
        """
        验证测试体系能检测到 NEW-004 问题：
        GovernanceProcessor 未注册到 _PROCESSOR_MAP
        """
        from src.engine.registry import _PROCESSOR_MAP

        assert "governance" in _PROCESSOR_MAP, (
            "测试体系无法检测到 NEW-004 bug！\n"
            "governance 处理器未注册到 _PROCESSOR_MAP。\n"
            "请修复 src/engine/registry.py。"
        )
        print("✅ 测试体系有效性验证通过：governance 处理器已正确注册")
