import libcst as cst
import pytest

from src.governance.transformer import FunctionTransformer, ImportApplier


def test_import_and_function_patching():
    source_code = """
import os

def process(data):
    print("Old logic")
    return data
"""
    # 1. 准备补丁
    new_body = """
import json
print("New logic")
return json.dumps(data)
"""
    # 2. 应用 Import (模拟 Agent 给出的 import)
    required_imports = ["import json"]

    # 3. 运行转换器
    tree = cst.parse_module(source_code)

    # 应用 Import
    import_applier = ImportApplier(required_imports)
    tree = tree.visit(import_applier)

    # 应用 Function Patch
    transformer = FunctionTransformer("process", new_body)
    tree = tree.visit(transformer)

    result = tree.code

    # 4. 断言检查
    assert "import json" in result
    assert "import os" in result  # 原有的 import 不能丢
    assert "json.dumps(data)" in result
    assert "Old logic" not in result

    assert transformer.patched is True, "FunctionTransformer 补丁标记应设为True"

    print("\n[Test Passed] Transformer logic is correct!")


if __name__ == "__main__":
    pytest.main([__file__])
