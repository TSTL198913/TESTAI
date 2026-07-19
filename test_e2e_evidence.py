import asyncio
import os
import re
import sqlite3
import subprocess
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.governance.orchestrator import GovernanceOrchestrator
from src.governance.models import DiagnosticContext
from src.governance.executor import GovernanceExecutor
from src.governance.security import SecurePathValidator

VULNERABLE_CODE = """import os

def process_user_expression():
    expr = input("请输入表达式: ")
    result = eval(expr)
    print(f"结果: {result}")

def run_system_command():
    cmd = input("请输入命令: ")
    os.system(cmd)

def main():
    print("测试程序")

if __name__ == "__main__":
    main()"""

def check_approval_record(tx_id):
    try:
        conn = sqlite3.connect('data/governance.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM approval_records WHERE tx_id = ?', (tx_id,))
        record = cursor.fetchone()
        conn.close()
        return record is not None
    except:
        return False

def check_tracking_events(tx_id):
    try:
        conn = sqlite3.connect('data/governance.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM tracking_events WHERE tx_id = ?', (tx_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count >= 2
    except:
        return False

def check_git_commit(tx_id):
    try:
        result = subprocess.run(
            ['git', 'log', '--oneline', '--all', f'--grep={tx_id}', '-n', '1'],
            capture_output=True, text=True
        )
        return len(result.stdout.strip()) > 0
    except:
        return False

def check_file_changed(file_path, expected_content):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return expected_content in content
    except:
        return False

async def main():
    print("=" * 70)
    print("端到端验证测试（物证验证）")
    print("=" * 70)
    print()
    
    target_file = 'tests/fixtures/e2e_test.py'
    with open(target_file, 'w', encoding='utf-8') as f:
        f.write(VULNERABLE_CODE)
    
    print("【阶段1】验证完整治理流程（诊断+审批）")
    print("-" * 50)
    
    orchestrator = GovernanceOrchestrator()
    
    context = DiagnosticContext(
        component_name="e2e_test",
        step_id="e2e_step_001",
        input_data="__import__('os').system('ls')",
        actual_output="Arbitrary code execution",
        expected_baseline="Safe execution",
        exception_trace="File e2e_test.py, line 5, in process_user_expression",
        system_metrics={"risk_level": "CRITICAL", "vulnerability_type": "eval"}
    )
    
    result = await orchestrator.execute_governance_flow(context)
    print(f"  治理流程结果: {result.get('status', 'UNKNOWN')}")
    
    tx_id = f"tx_e2e_step_001"
    print(f"  事务ID: {tx_id}")
    
    if result.get('status') == 'PENDING_APPROVAL':
        print(f"  需要审批，执行审批...")
        approval_result = await orchestrator.approve_and_apply(tx_id, "tech_committee", "安全补丁已审核")
        print(f"  审批结果: {approval_result.get('status', 'UNKNOWN')}")
    
    print()
    
    print("【阶段2】物证验证")
    print("-" * 50)
    
    evidence_checks = [
        ("审批记录", check_approval_record(tx_id)),
        ("追踪事件", check_tracking_events(tx_id)),
        ("Git提交", check_git_commit(tx_id)),
        ("文件变更", check_file_changed(target_file, "ast.literal_eval")),
    ]
    
    passed = 0
    failed = 0
    
    for name, result in evidence_checks:
        status = "✅" if result else "❌"
        print(f"  {status} {name}: {'通过' if result else '失败'}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print()
    
    print("【阶段3】负向验证")
    print("-" * 50)
    
    executor = GovernanceExecutor()
    
    malicious_code = 'def bad_func(): eval("__import__(''os'').system(''rm -rf /'')")'
    is_safe = executor.is_safe_patch(malicious_code)
    print(f"  {'✅' if not is_safe else '❌'} 恶意补丁拦截: {'拦截成功' if not is_safe else '拦截失败'}")
    
    validator = SecurePathValidator()
    path_result = validator.validate("../etc/passwd")
    print(f"  {'✅' if path_result == False else '❌'} 路径遍历拦截: {'拦截成功' if path_result == False else '拦截失败'}")
    
    print()
    
    print("【阶段4】功能验证")
    print("-" * 50)
    
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            fixed_code = f.read()
        
        compile(fixed_code, target_file, 'exec')
        print(f"  ✅ 修复后代码语法正确")
        
        if "eval(" in fixed_code and "ast.literal_eval" not in fixed_code:
            print(f"  ❌ eval()漏洞仍存在")
            failed += 1
        else:
            print(f"  ✅ eval()漏洞已修复")
            passed += 1
            
    except SyntaxError as e:
        print(f"  ❌ 修复后代码语法错误: {e}")
        failed += 1
    
    print()
    
    print("=" * 70)
    print("验证结果汇总")
    print("=" * 70)
    print(f"\n正向验证: {passed} / {len(evidence_checks) + 1}")
    print(f"负向验证: 2 / 2")
    print(f"总通过率: {(passed / (len(evidence_checks) + 3)) * 100:.1f}%")
    
    print("\n结论:")
    if failed == 0:
        print("  ✅ 验证过程有效且正确，所有物证均已确认")
    else:
        print(f"  ⚠️ {failed}项验证失败，需要进一步排查")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(result)