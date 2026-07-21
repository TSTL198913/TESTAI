import libcst as cst
import pytest

from src.governance.transformer import FunctionTransformer


def test_complex_class_and_decorator_patch():
    # 场景：一个带有装饰器的类方法
    source_code = """
import functools

def my_decorator(func):
    return func

class Processor:
    @my_decorator
    @staticmethod
    def run(data):
        # 错误逻辑
        return data - 1

    def cleanup(self):
        pass
"""
    # AI 期望的修复逻辑
    new_logic = "return data + 100"

    # 执行转换
    tree = cst.parse_module(source_code)
    transformer = FunctionTransformer("run", new_logic)
    modified_tree = tree.visit(transformer)

    result = modified_tree.code

    # 1. 核心验证：装饰器是否还在？
    assert "@my_decorator" in result
    assert "@staticmethod" in result

    # 2. 核心验证：逻辑是否更新？
    assert "return data + 100" in result
    assert "return data - 1" not in result

    # 3. 完整性验证：其他方法是否受影响？
    assert "def cleanup(self):" in result

    assert transformer.patched is True, "FunctionTransformer 补丁标记应设为True"

    print("\n✅ [Hard Mode Passed] 装饰器与类结构保持完整！")


if __name__ == "__main__":
    pytest.main([__file__])
