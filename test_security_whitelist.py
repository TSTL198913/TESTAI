import sys
sys.path.insert(0, '.')

from src.governance.executor import SecurityVisitor
import libcst as cst

test_cases = [
    ('def safe_cmd(): subprocess.run(["ls"])', True, "白名单命令应该通过"),
    ('def unsafe_cmd(): subprocess.run(["rm", "-rf", "/"])', False, "危险命令应该被拦截"),
    ('def eval_cmd(): eval("__import__(''os'').system(''ls'')")', False, "eval应该被拦截"),
    ('def os_system(): os.system("ls")', False, "os.system应该被拦截"),
]

print("SecurityVisitor白名单测试")
print("-" * 50)

for code, expected_safe, description in test_cases:
    tree = cst.parse_module(code)
    visitor = SecurityVisitor()
    tree.visit(visitor)
    is_safe = not visitor.is_unsafe
    
    status = "✅" if is_safe == expected_safe else "❌"
    print(f"{status} {description}")
    print(f"   代码: {code}")
    print(f"   预期: {'安全' if expected_safe else '不安全'}, 实际: {'安全' if is_safe else '不安全'}")
    if visitor.vulnerabilities:
        print(f"   漏洞: {visitor.vulnerabilities}")
    
    if "subprocess.run" in code:
        import inspect
        print(f"   参数提取方法: {inspect.signature(visitor._extract_args)}")
        for node in tree.body:
            if isinstance(node, cst.FunctionDef):
                for stmt in node.body.body:
                    if isinstance(stmt, cst.Expr):
                        call_node = stmt.value
                        if isinstance(call_node, cst.Call):
                            args = visitor._extract_args(call_node)
                            print(f"   提取的参数: {args}")
                            print(f"   参数节点类型: {type(call_node.args[0].value)}")
                            if hasattr(call_node.args[0].value, 'elements'):
                                for i, elt in enumerate(call_node.args[0].value.elements):
                                    print(f"   元素{i}类型: {type(elt)}, 值: {repr(elt)}")
    print()