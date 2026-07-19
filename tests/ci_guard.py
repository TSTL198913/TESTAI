# tests/ci_guard.py
"""
CI 自动守卫 - 防止测试体系退化

本脚本在 CI 中运行，检测以下反模式：
1. 新增 assert hasattr(...) 弱断言
2. 新增 pytest.skip(...) 失败跳过
3. 新增 except Exception: pass 异常吞没

如果检测到反模式，CI 失败。
"""
import os
import subprocess
import sys


def scan_for_weak_assertions(directory: str, exclude_files: list = None) -> list:
    violations = []
    exclude_files = exclude_files or []
    
    for root, dirs, files in os.walk(directory):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            if filename in exclude_files:
                continue
            
            filepath = os.path.join(root, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                in_docstring = False
                docstring_char = None
                for line_num, line in enumerate(f, 1):
                    stripped = line.strip()
                    
                    # 跳过空行
                    if not stripped:
                        continue
                    
                    # 检测 docstring 边界
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        if not in_docstring:
                            in_docstring = True
                            docstring_char = stripped[0:3]
                            if stripped.endswith(docstring_char) and len(stripped) >= 6:
                                in_docstring = False
                                docstring_char = None
                        elif stripped.endswith(docstring_char):
                            in_docstring = False
                            docstring_char = None
                        continue
                    
                    # 如果在 docstring 中，跳过
                    if in_docstring:
                        continue
                    
                    # 跳过注释行
                    if stripped.startswith("#"):
                        continue
                    
                    # 检测弱断言（排除注释中的内容）
                    code_part = line.split("#")[0]
                    if "assert hasattr(" in code_part and "CircuitBreaker" not in code_part:
                        violations.append(f"{filepath}:{line_num}: {line.strip()}")
    
    return violations


def scan_for_pytest_skip(directory: str, exclude_files: list = None) -> list:
    violations = []
    exclude_files = exclude_files or []
    
    for root, dirs, files in os.walk(directory):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            if filename in exclude_files:
                continue
            
            filepath = os.path.join(root, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                in_docstring = False
                docstring_char = None
                for line_num, line in enumerate(f, 1):
                    stripped = line.strip()
                    
                    if not stripped:
                        continue
                    
                    if stripped.startswith('"""') or stripped.startswith("'''"):
                        if not in_docstring:
                            in_docstring = True
                            docstring_char = stripped[0:3]
                            if stripped.endswith(docstring_char) and len(stripped) >= 6:
                                in_docstring = False
                                docstring_char = None
                        elif stripped.endswith(docstring_char):
                            in_docstring = False
                            docstring_char = None
                        continue
                    
                    if in_docstring:
                        continue
                    
                    if stripped.startswith("#"):
                        continue
                    
                    code_part = line.split("#")[0]
                    if "pytest.skip(" in code_part:
                        violations.append(f"{filepath}:{line_num}: {line.strip()}")
    
    return violations


def scan_for_exception_pass(directory: str, exclude_files: list = None) -> list:
    violations = []
    exclude_files = exclude_files or []
    
    for root, dirs, files in os.walk(directory):
        for filename in files:
            if not filename.endswith(".py"):
                continue
            if filename in exclude_files:
                continue
            
            filepath = os.path.join(root, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line_num, line in enumerate(lines, 1):
                    if "except Exception:" in line or "except Exception as" in line:
                        # 检查下一行是否是 pass
                        if line_num < len(lines):
                            next_line = lines[line_num].strip()
                            if next_line == "pass":
                                violations.append(f"{filepath}:{line_num}: {line.strip()}")
    
    return violations


def run():
    tests_dir = os.path.join(os.path.dirname(__file__))
    this_file = os.path.basename(__file__)
    exclude_files = [
        this_file,
        "test_strict_validation.py",
    ]
    
    print("🔍 扫描 CI 守卫规则...")
    
    violations = []
    
    print("\n1. 扫描 assert hasattr(...) 弱断言...")
    hasattr_violations = scan_for_weak_assertions(tests_dir, exclude_files=exclude_files)
    if hasattr_violations:
        print(f"   ❌ 发现 {len(hasattr_violations)} 处违反：")
        for v in hasattr_violations:
            print(f"      {v}")
        violations.extend(hasattr_violations)
    else:
        print("   ✅ 未发现违反")
    
    print("\n2. 扫描 pytest.skip(...) 失败跳过...")
    skip_violations = scan_for_pytest_skip(tests_dir, exclude_files=exclude_files)
    if skip_violations:
        print(f"   ❌ 发现 {len(skip_violations)} 处违反：")
        for v in skip_violations:
            print(f"      {v}")
        violations.extend(skip_violations)
    else:
        print("   ✅ 未发现违反")
    
    print("\n3. 扫描 except Exception: pass 异常吞没...")
    exception_violations = scan_for_exception_pass(tests_dir, exclude_files=exclude_files)
    if exception_violations:
        print(f"   ❌ 发现 {len(exception_violations)} 处违反：")
        for v in exception_violations:
            print(f"      {v}")
        violations.extend(exception_violations)
    else:
        print("   ✅ 未发现违反")
    
    # 运行测试有效性门控
    print("\n4. 运行测试有效性门控...")
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/governance/test_effectiveness_gate.py", "-v", "--tb=short", "--no-header"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print("   ❌ 测试有效性门控失败")
        print(result.stdout)
        print(result.stderr)
        violations.append("TEST_EFFECTIVENESS_GATE_FAILED")
    else:
        print("   ✅ 测试有效性门控通过")
    
    print("\n" + "="*60)
    
    if violations:
        print(f"❌ CI 守卫失败：发现 {len(violations)} 处违反")
        sys.exit(1)
    else:
        print("✅ CI 守卫通过：所有规则符合要求")
        sys.exit(0)


if __name__ == "__main__":
    run()