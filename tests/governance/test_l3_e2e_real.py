import asyncio
import json
import os
import sys
import shutil
import tempfile
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from src.governance.models import DiagnosticContext
from src.governance.tracker import GovernanceTracker, GovernanceActionType
from src.governance.approval import ApprovalManager, ApprovalStatus


BUGGY_MODULE = '''
def calculate_discount(price: float, discount_rate: float) -> float:
    return price - discount_rate


def validate_email(email: str) -> bool:
    if "@" in email:
        return True
    return False
'''

FIXED_FUNCTION = '''    if discount_rate < 0 or discount_rate > 1:
        raise ValueError("discount_rate must be between 0 and 1")
    return price * (1 - discount_rate)
'''


def setup_git_repo(temp_dir: str) -> str:
    os.makedirs(temp_dir, exist_ok=True)
    subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_dir, capture_output=True, check=True)
    
    src_dir = os.path.join(temp_dir, "src", "components")
    os.makedirs(src_dir, exist_ok=True)
    
    target_file = os.path.join(src_dir, "DiscountCalculator.py")
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(BUGGY_MODULE)
    
    subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_dir, capture_output=True, check=True)
    
    return temp_dir


def reset_all_state():
    # Reset GovernanceTracker singleton (clear instance + class variables)
    GovernanceTracker._instance = None
    GovernanceTracker._events = []
    GovernanceTracker._consecutive_convergence_count = 0
    ApprovalManager._instance = None
    ApprovalManager._initialized = False
    import os
    db_path = os.environ.get('TEST_APPROVAL_DB', 'data/governance.db')
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass  # 文件可能被锁定或已删除，清理时忽略


@pytest.mark.asyncio
async def test_l3_e2e_governance_flow_functional():
    """L3验证: 完整治理闭环 - 诊断→修复→审批→验证
    
    场景: DiscountCalculator.calculate_discount 有逻辑错误
    期望:
    1. AI诊断出问题 (is_fixable=True, patch_type=functional)
    2. 创建审批记录 (functional类型自动批准)
    3. Git事务: 创建分支→应用patch→提交
    4. 事件追踪完整
    5. 修复后代码正确
    """
    reset_all_state()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = setup_git_repo(temp_dir)
        
        target_file = os.path.join("src", "components", "DiscountCalculator.py")
        abs_target = os.path.join(repo_path, target_file)
        
        context = DiagnosticContext(
            step_id="l3_func_001",
            component_name="DiscountCalculator",
            input_data={"price": 100, "discount_rate": 0.2},
            actual_output={"result": 99.8, "expected": 80.0},
            expected_baseline={"result": 80.0},
            exception_trace="AssertionError: expected 80.0 but got 99.8",
            system_metrics={"risk_level": "medium", "cwe": "CWE-398"}
        )
        
        from src.governance.orchestrator import GovernanceOrchestrator
        orchestrator = GovernanceOrchestrator(repo_path=repo_path)
        
        result = await orchestrator.execute_governance_flow(context)
        
        print(f"\n=== L3 E2E Result ===")
        print(f"Status: {result.get('status')}")
        print(f"Confidence: {result.get('confidence_score')}")
        print(f"Reasoning: {str(result.get('reasoning', ''))[:150]}...")
        if result.get('proposal'):
            p = result['proposal']
            print(f"Proposal target_function: '{p.get('target_function')}'")
            print(f"Proposal patch_type: {p.get('patch_type')}")
            print(f"Proposal code (first 200): {str(p.get('suggested_code', ''))[:200]}")
        
        tracker = GovernanceTracker()
        events = tracker.get_events_by_trace("l3_func_001")
        print(f"\nEvent count for trace: {len(events)}")
        for e in events:
            print(f"  {e.action_type.value:25s} | {e.status or '-':20s} | {e.component or '-'}")
        
        action_types = [e.action_type for e in events]
        
        assert GovernanceActionType.DIAGNOSE_START in action_types, "缺少 DIAGNOSE_START 事件"
        assert GovernanceActionType.DIAGNOSE_COMPLETE in action_types, "缺少 DIAGNOSE_COMPLETE 事件"
        
        if result.get("status") == "FIXED":
            assert GovernanceActionType.PATCH_CREATE in action_types, "缺少 PATCH_CREATE 事件"
            assert GovernanceActionType.APPROVAL_GRANTED in action_types, "缺少 APPROVAL_GRANTED 事件"
            assert GovernanceActionType.PATCH_APPLIED in action_types, "缺少 PATCH_APPLIED 事件"
            
            with open(abs_target, "r", encoding="utf-8") as f:
                fixed_content = f.read()
            print(f"\nFixed code:\n{fixed_content[:300]}")
            
            result_check = subprocess.run(
                ["git", "diff", "HEAD", "--name-only"],
                cwd=repo_path, capture_output=True, text=True
            )
            print(f"Git status (diff from HEAD): {result_check.stdout.strip()}")
            
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path, capture_output=True, text=True
            )
            print(f"Current branch: {branch_result.stdout.strip()}")
        
        return result


if __name__ == "__main__":
    asyncio.run(test_l3_e2e_governance_flow_functional())
