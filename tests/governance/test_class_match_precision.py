"""
测试模块: ContextAwareTransformer
覆盖业务规则: BR-02

BR-02: ContextAwareTransformer必须精确匹配目标类中的方法
- 代码依据: transformer.py
- 位置: 第47行
- 说明: class_match条件为(target_class is None or current_class == target_class)
"""
import libcst as cst
import pytest

from src.governance.transformer import ContextAwareTransformer


class TestContextAwareTransformerClassMatch:
    """ContextAwareTransformer类匹配精确性测试"""

    def test_patches_method_in_target_class(self):
        """
        正向场景：正确类中的方法被修改
        验证：BR-02 精确匹配目标类中的方法
        """
        source_code = """
class TargetClass:
    def target_method(self):
        return "original"

class OtherClass:
    def target_method(self):
        return "other_original"
"""
        tree = cst.parse_module(source_code)
        transformer = ContextAwareTransformer(
            target_function="target_method",
            new_body='return "patched"',
            target_class="TargetClass"
        )

        tree = tree.visit(transformer)

        assert transformer.patched is True, "补丁标记应设为True"
        assert 'return "patched"' in tree.code, "TargetClass中的代码应被替换"
        assert 'return "other_original"' in tree.code, "OtherClass中的代码应保持不变"
        assert 'return "original"' not in tree.code, "TargetClass中的原代码应被移除"

    def test_rejects_method_in_wrong_class(self):
        """
        负向场景：错误类中的方法不被修改
        验证：BR-02 仅修改指定类中的方法
        """
        source_code = """
class TargetClass:
    def target_method(self):
        return "original"

class OtherClass:
    def target_method(self):
        return "other_original"
"""
        tree = cst.parse_module(source_code)
        transformer = ContextAwareTransformer(
            target_function="target_method",
            new_body='return "patched"',
            target_class="WrongClass"
        )

        tree = tree.visit(transformer)

        assert transformer.patched is False, "无匹配时补丁标记应保持False"
        assert 'return "original"' in tree.code, "TargetClass中的代码应保持不变"
        assert 'return "other_original"' in tree.code, "OtherClass中的代码应保持不变"
        assert 'return "patched"' not in tree.code, "不应有任何代码被替换"

    def test_handles_no_class_filter(self):
        """
        边界场景：无类过滤时仅匹配函数名
        验证：BR-02 class_match条件为None时匹配所有同名函数
        """
        source_code = """
class ClassA:
    def shared_method(self):
        return "a"

class ClassB:
    def shared_method(self):
        return "b"
"""
        tree = cst.parse_module(source_code)
        transformer = ContextAwareTransformer(
            target_function="shared_method",
            new_body='return "patched"',
            target_class=None
        )

        tree = tree.visit(transformer)

        assert transformer.patched is True, "补丁标记应设为True"
        assert tree.code.count('return "patched"') == 2, "所有同名方法都应被替换"
        assert 'return "a"' not in tree.code, "ClassA中的原代码应被移除"
        assert 'return "b"' not in tree.code, "ClassB中的原代码应被移除"

    def test_raises_error_on_invalid_syntax(self):
        """
        异常场景：无效源代码抛出解析错误
        验证：libcst解析失败时正确抛出异常
        """
        invalid_code = """
class TestClass:
    def target_method(self)
        return "invalid"
"""

        with pytest.raises(cst.ParserSyntaxError):
            cst.parse_module(invalid_code)

    def test_class_match_condition_broken(self):
        """
        依赖场景：class_match条件被破坏时的行为
        验证：测试能检测到业务规则BR-02被破坏
        """
        source_code = """
class TargetClass:
    def target_method(self):
        return "original"

class OtherClass:
    def target_method(self):
        return "other_original"
"""
        tree = cst.parse_module(source_code)
        transformer = ContextAwareTransformer(
            target_function="target_method",
            new_body='return "patched"',
            target_class="TargetClass"
        )

        tree = tree.visit(transformer)

        assert 'return "other_original"' in tree.code, "OtherClass不应被修改"
        assert transformer.patched is True, "补丁应成功应用"