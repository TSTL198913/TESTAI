import libcst as cst
import pytest

from src.governance.transformer import ContextAwareTransformer  # 确保您已经更新了这个类


def test_namespace_isolation():
    source_code = """
class ClassA:
    def run(self):
        return "Legacy A"

class ClassB:
    def run(self):
        return "Legacy B"
"""
    # 目标：只修改 ClassA.run，ClassB.run 必须保持原样
    new_logic = 'return "Patched A"'

    # 初始化 Transformer，明确指定 target_class
    transformer = ContextAwareTransformer(
        target_function="run", target_class="ClassA", new_body=new_logic
    )

    # 执行转换
    tree = cst.parse_module(source_code)
    modified_tree = tree.visit(transformer)
    result = modified_tree.code
    # 将 result 重新解析为 CST，进行结构化校验
    tree_result = cst.parse_module(result)

    # 辅助工具：提取特定类的代码片段作为字符串（忽略缩进差异）
    # 我们可以简单通过校验 ClassB.run 的逻辑是否还是 "Legacy B"
    # 或者直接查找 'return "Legacy B"' 是否在 ClassB 定义的范围内

    # 更稳妥的办法：直接检查 ClassB 的结构
    class_b_code = [
        n
        for n in tree_result.body
        if isinstance(n, cst.ClassDef) and n.name.value == "ClassB"
    ][0]

    assert "Legacy B" in cst.Module(body=[class_b_code]).code
    assert "Patched A" not in cst.Module(body=[class_b_code]).code

    assert transformer.patched is True, "ContextAwareTransformer 补丁标记应设为True"

    print("\n✅ [Namespace Isolation Passed] 结构化验证通过：ClassB 逻辑未被侵染！")


# 将此片段加入您的测试文件末尾运行
def test_visual_verification():
    source_code = """
class ClassA:
    def run(self):
        return "Legacy A"

class ClassB:
    def run(self):
        return "Legacy B"
"""
    new_logic = 'return "Patched A"'
    # 【修复后】：使用关键字参数，确保代码意图清晰且不会出现参数位置偏移
    transformer = ContextAwareTransformer(
        target_function="run", target_class="ClassA", new_body=new_logic
    )

    # 转换
    modified_tree = cst.parse_module(source_code).visit(transformer)

    # 【可视化输出】
    print("\n--- 治理引擎输出的代码 ---")
    print(modified_tree.code)
    print("--------------------------")

    # 强制校验
    assert "Patched A" in modified_tree.code
    assert "Legacy A" not in modified_tree.code
    assert "Legacy B" in modified_tree.code
    assert transformer.patched is True, "ContextAwareTransformer 补丁标记应设为True"

    print("✅ 验证确认：ClassA 已变异，ClassB 保持原始逻辑。")


if __name__ == "__main__":
    test_visual_verification()
    pytest.main([__file__])
