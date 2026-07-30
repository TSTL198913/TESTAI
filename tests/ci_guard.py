import ast
import os
import sys
import io
from typing import List, Dict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


EXCLUDED_FILES = [
    'test_strict_validation.py',
    'ci_guard.py',
    'conftest.py',
    # 元测试需要 Mock 构造"修复版"返回值以反向证伪,可能触发弱断言误报
    'test_meta_inverse_proof.py',
]

EXCLUDED_DIRS = [
    'utils',
    'exposed_bugs',
]


def _should_exclude_file(filepath: str) -> bool:
    basename = os.path.basename(filepath)
    if basename in EXCLUDED_FILES:
        return True
    for excl_dir in EXCLUDED_DIRS:
        if excl_dir in filepath.replace('\\', '/').split('/'):
            return True
    return False


def _log_warning(message: str):
    print(f"⚠️  [WARNING] {message}", file=sys.stderr)


def scan_for_weak_assertions(directory: str) -> List[Dict]:
    violations = []
    for root, _, files in os.walk(directory):
        for filename in files:
            if not filename.endswith('.py'):
                continue
            filepath = os.path.join(root, filename)
            if _should_exclude_file(filepath):
                continue
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    source = f.read()
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assert):
                        if isinstance(node.test, (ast.NameConstant, ast.Constant)):
                            violations.append({
                                'file': filepath,
                                'line': node.lineno,
                                'type': 'weak_assertion',
                                'message': f'Weak assertion at line {node.lineno}: assert {ast.dump(node.test)}',
                            })
                        elif isinstance(node.test, ast.Call):
                            func_name = ''
                            if isinstance(node.test.func, ast.Name):
                                func_name = node.test.func.id
                            elif isinstance(node.test.func, ast.Attribute):
                                func_name = node.test.func.attr

                            if func_name in ['hasattr', 'issubclass']:
                                violations.append({
                                    'file': filepath,
                                    'line': node.lineno,
                                    'type': 'weak_assertion',
                                    'message': f'Weak assertion at line {node.lineno}: assert {func_name}(...)',
                                })
            except SyntaxError as e:
                _log_warning(f"Syntax error in {filepath}: {e}")
            except Exception as e:
                _log_warning(f"Failed to parse {filepath}: {e}")
    return violations


def _check_pytest_skip_in_decorators(decorator_list, filepath, lineno, violations):
    for deco in decorator_list:
        if isinstance(deco, ast.Call):
            deco = deco.func
        if isinstance(deco, ast.Attribute):
            if (isinstance(deco.value, ast.Attribute)
                    and isinstance(deco.value.value, ast.Name)
                    and deco.value.value.id == 'pytest'
                    and deco.value.attr == 'mark'
                    and deco.attr == 'skip'):
                violations.append({
                    'file': filepath,
                    'line': lineno,
                    'type': 'pytest_skip',
                    'message': f'pytest.mark.skip found in {filepath} at line {lineno}',
                })


def scan_for_pytest_skip(directory: str) -> List[Dict]:
    violations = []
    for root, _, files in os.walk(directory):
        for filename in files:
            if not filename.endswith('.py'):
                continue
            filepath = os.path.join(root, filename)
            if _should_exclude_file(filepath):
                continue
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    source = f.read()
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        func = node.func
                        if isinstance(func, ast.Attribute):
                            if (isinstance(func.value, ast.Name)
                                    and func.value.id == 'pytest'
                                    and func.attr == 'skip'):
                                violations.append({
                                    'file': filepath,
                                    'line': node.lineno,
                                    'type': 'pytest_skip',
                                    'message': f'pytest skip found in {filepath} at line {node.lineno}',
                                })
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        _check_pytest_skip_in_decorators(
                            node.decorator_list, filepath, node.lineno, violations
                        )
            except SyntaxError as e:
                _log_warning(f"Syntax error in {filepath}: {e}")
            except Exception as e:
                _log_warning(f"Failed to parse {filepath}: {e}")
    return violations


def scan_for_exception_pass(directory: str) -> List[Dict]:
    violations = []
    for root, _, files in os.walk(directory):
        for filename in files:
            if not filename.endswith('.py'):
                continue
            filepath = os.path.join(root, filename)
            if _should_exclude_file(filepath):
                continue
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    source = f.read()
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ExceptHandler):
                        if node.type is None or (
                            isinstance(node.type, ast.Name) and node.type.id == 'Exception'
                        ):
                            body_stmts = []
                            for stmt in node.body:
                                if isinstance(stmt, ast.Pass):
                                    body_stmts.append('pass')
                                elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Str):
                                    continue
                                else:
                                    body_stmts.append('other')
                                    break
                            if body_stmts == ['pass']:
                                violations.append({
                                    'file': filepath,
                                    'line': node.lineno,
                                    'type': 'exception_pass',
                                    'message': f'except Exception: pass at line {node.lineno} in {filepath}',
                                })
            except SyntaxError as e:
                _log_warning(f"Syntax error in {filepath}: {e}")
            except Exception as e:
                _log_warning(f"Failed to parse {filepath}: {e}")
    return violations


if __name__ == '__main__':
    violations = scan_for_weak_assertions('tests') + \
                 scan_for_pytest_skip('tests') + \
                 scan_for_exception_pass('tests')
    if violations:
        for v in violations:
            print(f"❌ {v['message']}")
        print(f"\nTotal violations: {len(violations)}")
        exit(1)
    else:
        print("✅ CI Guard passed - no violations found")
