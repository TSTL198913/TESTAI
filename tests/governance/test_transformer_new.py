"""
Transformer模块测试 - Trae编写标准示例
"""

import libcst as cst
import pytest

from src.governance.transformer import (
    ContextAwareTransformer,
    FunctionTransformer,
    ImportApplier,
)


class TestContextAwareTransformer:

    def test_patches_correct_method_in_class(self):
        source_code = """
class MyClass:
    def target_method(self):
        return "original"
"""
        tree = cst.parse_module(source_code)
        transformer = ContextAwareTransformer(
            target_function="target_method",
            new_body='return "patched"',
            target_class="MyClass",
        )

        tree = tree.visit(transformer)

        assert transformer.patched is True, "补丁标记应设为True"
        assert 'return "patched"' in tree.code, "代码应被替换"
        assert 'return "original"' not in tree.code, "原代码应被移除"

    def test_rejects_wrong_class_name(self):
        source_code = """
class MyClass:
    def target_method(self):
        return "original"

class AnotherClass:
    def target_method(self):
        return "another_original"
"""
        tree = cst.parse_module(source_code)
        transformer = ContextAwareTransformer(
            target_function="target_method",
            new_body='return "patched"',
            target_class="AnotherClass",
        )

        tree = tree.visit(transformer)

        assert transformer.patched is True, "AnotherClass 中的方法应被匹配"
        assert 'return "patched"' in tree.code, "AnotherClass 中的代码应被替换"
        assert 'return "original"' in tree.code, "MyClass 中的代码应保持不变"

    def test_handles_empty_new_body(self):
        source_code = """
class MyClass:
    def target_method(self):
        return "original"
"""
        tree = cst.parse_module(source_code)
        transformer = ContextAwareTransformer(
            target_function="target_method", new_body="", target_class="MyClass"
        )

        tree = tree.visit(transformer)

        assert transformer.patched is True, "补丁标记应设为True"

    def test_raises_error_on_invalid_syntax(self):
        source_code = "def invalid("

        with pytest.raises(cst.ParserSyntaxError):
            cst.parse_module(source_code)

    def test_works_without_class_filter(self):
        source_code = """
def standalone_func():
    return "original"
"""
        tree = cst.parse_module(source_code)
        transformer = ContextAwareTransformer(
            target_function="standalone_func", new_body='return "patched"'
        )

        tree = tree.visit(transformer)

        assert transformer.patched is True, "补丁标记应设为True"
        assert 'return "patched"' in tree.code, "代码应被替换"
        assert 'return "original"' not in tree.code, "原代码应被移除"


class TestFunctionTransformer:

    def test_patches_standalone_function(self):
        source_code = """
def my_function():
    return 1
"""
        tree = cst.parse_module(source_code)
        transformer = FunctionTransformer(
            target_function="my_function", new_body="return 2"
        )

        tree = tree.visit(transformer)

        assert transformer.patched is True, "补丁标记应设为True"
        assert "return 2" in tree.code, "代码应被替换"
        assert "return 1" not in tree.code, "原代码应被移除"

    def test_ignores_non_matching_function(self):
        source_code = """
def other_function():
    return 1
"""
        tree = cst.parse_module(source_code)
        transformer = FunctionTransformer(
            target_function="my_function", new_body="return 2"
        )

        tree = tree.visit(transformer)

        assert transformer.patched is False, "补丁标记应保持False"
        assert "return 1" in tree.code, "代码应保持不变"


class TestImportApplier:

    def test_adds_imports_at_correct_position(self):
        source_code = """
import os

def func():
    pass
"""
        tree = cst.parse_module(source_code)
        applier = ImportApplier(["import sys"])

        tree = tree.visit(applier)

        lines = tree.code.strip().split("\n")
        assert "import sys" in lines[:3], "import应添加在文件开头"

    def test_handles_no_existing_imports(self):
        source_code = """
def func():
    pass
"""
        tree = cst.parse_module(source_code)
        applier = ImportApplier(["import sys"])

        tree = tree.visit(applier)

        assert tree.code.strip().startswith("import sys"), "import应添加在文件最开头"

    def test_handles_empty_imports_list(self):
        source_code = """
import os
"""
        tree = cst.parse_module(source_code)
        applier = ImportApplier([])

        tree = tree.visit(applier)

        assert tree is not None, "应正常返回"
        assert "import os" in tree.code, "原代码应保持不变"
