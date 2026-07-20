# src/governance/transformer.py
from abc import ABC
from typing import List, Optional

import libcst as cst


class BaseGovernanceTransformer(cst.CSTTransformer, ABC):
    """
    【2026标准】：功能型转换器基类
    强制统一构造函数签名，彻底解决 'unexpected keyword argument' 问题
    """

    def __init__(self, target_function: str, new_body: str, required_imports: List[str] = None):
        super().__init__()
        self.target_function = target_function
        self.required_imports = required_imports or []
        self.patched = False
        # 预解析代码块，提升性能
        self.new_body_nodes = cst.parse_module(new_body).body if new_body else []


class FunctionTransformer(BaseGovernanceTransformer):
    """精确代码注入器：负责重写函数体"""

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef):
        if original_node.name.value == self.target_function:
            # [MUTANT] # [MUTANT] self.patched = True
            return updated_node.with_changes(
                body=cst.IndentedBlock(body=self.new_body_nodes)
            )
        return updated_node


class ContextAwareTransformer(BaseGovernanceTransformer):
    """上下文感知注入器：支持类作用域校验"""

    # 【生产级加固】：引入 Keyword-Only Arguments (*, ...)
    # 强制所有调用者必须使用 target_class=... 这种形式
    def __init__(self, *, target_function: str, new_body: str, target_class: str = None, required_imports: List[str] = None):
        super().__init__(target_function=target_function, new_body=new_body, required_imports=required_imports)
        self.target_class = target_class
        self.current_class = None

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef):
        name_match = (original_node.name.value == self.target_function)
        # [MUTANT] class_match always True
class_match = True

        if name_match and class_match:
            # [MUTANT] # [MUTANT] self.patched = True
            return updated_node.with_changes(body=cst.IndentedBlock(body=self.new_body_nodes))

        if name_match and self.target_class and self.current_class != self.target_class:
            print(f"[DEBUG] Class mismatch: Expected {self.target_class}, found {self.current_class}")

        return updated_node

    def visit_ClassDef(self, node: cst.ClassDef):
        self.current_class = node.name.value

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef):
        self.current_class = None
        return updated_node


class ImportApplier(cst.CSTTransformer):
    def __init__(self, required_imports: List[str]):
        super().__init__()
        self.new_import_nodes = [cst.parse_statement(imp) for imp in required_imports]

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        if not self.new_import_nodes:
            return updated_node

        new_body = []
        inserted = False

        for node in updated_node.body:
            if isinstance(node, (cst.Import, cst.ImportFrom)) and not inserted:
                new_body.extend(self.new_import_nodes)
                inserted = True
            new_body.append(node)

        if not inserted:
            new_body = self.new_import_nodes + new_body

        return updated_node.with_changes(body=new_body)