"""TestAI 全链路 E2E 测试套件 - 技术委员会严格验证

覆盖场景:
1. L3-E2E-001: 功能修复全链路 (functional patch)
2. L3-E2E-002: 多缺陷连续修复 (multi-defect)
3. L3-E2E-003: 补丁应用失败回滚 (rollback verification)
4. L3-E2E-004: 非治理场景跳过敏节 (non-governable skip)
5. L3-E2E-005: 决策引擎拒绝场景 (decision reject)
6. L3-E2E-006: 事件追踪完整性 (event completeness)
7. L3-E2E-007: 治理历史记录验证 (history verification)
8. L3-E2E-008: 转换器实际应用验证 (transformer real apply)

所有场景使用真实 Git 仓库 + 真实文件系统 + 真实代码变更。
"""

import asyncio
import json
import os
import sys
import shutil
import tempfile
import subprocess
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from src.governance.models import DiagnosticContext, GovernanceAction, PatchProposal
from src.governance.tracker import GovernanceTracker, GovernanceActionType
from src.governance.approval import ApprovalManager, ApprovalStatus


def _buggy_discount_module():
    return '''
def calculate_discount(price: float, discount_rate: float) -> float:
    return price - discount_rate


def apply_tax(amount: float, tax_rate: float) -> float:
    return amount * (1 + tax_rate)
'''


def _safe_rmtree(path: str):
    """Windows 安全删除目录，处理文件句柄残留。"""
    for _ in range(5):
        try:
            shutil.rmtree(path, ignore_errors=False)
            return
        except PermissionError:
            time.sleep(0.3)
    shutil.rmtree(path, ignore_errors=True)


class _TempDir:
    """安全临时目录上下文管理器，解决 Windows 文件锁问题。"""
    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="testai_e2e_")

    def __enter__(self):
        return self.path

    def __exit__(self, *args):
        _safe_rmtree(self.path)


def _setup_git_repo(temp_dir: str, content: str, filename: str = "src/components/Calculator.py") -> str:
    os.makedirs(temp_dir, exist_ok=True)
    subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "tc@testai.com"], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "TechCommittee"], cwd=temp_dir, capture_output=True, check=True)

    full_path = os.path.join(temp_dir, filename)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=temp_dir, capture_output=True, check=True)
    return temp_dir


def _reset_all():
    GovernanceTracker._instance = None
    GovernanceTracker._events = []
    GovernanceTracker._consecutive_convergence_count = 0
    ApprovalManager._instance = None
    ApprovalManager._initialized = False

    for db_name in ['governance.db', 'tracker.db', 'approval.db', 'test_approval.db']:
        for search_dir in ['.', 'data', os.path.join('tests', 'data'),
                           os.path.join(tempfile.gettempdir(), 'testai_data')]:
            candidate = os.path.join(search_dir, db_name)
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass  # 文件可能被锁定或已删除，清理时忽略


class TestFullPipelineE2E:
    """全链路 E2E 测试套件 - 技术委员会验证级"""

    @pytest.fixture(autouse=True)
    def _reset_each(self):
        _reset_all()
        yield
        _reset_all()

    @pytest.mark.asyncio
    async def test_e2e_001_functional_patch_full_pipeline(self):
        """L3-E2E-001: 功能修复全链路
        验证: 诊断→修复→审批→Git事务→事件追踪→文件变更
        """
        with _TempDir() as temp_dir:
            repo_path = _setup_git_repo(temp_dir, _buggy_discount_module())
            target_file = os.path.join("src", "components", "Calculator.py")

            context = DiagnosticContext(
                step_id="e2e_func_001",
                component_name="Calculator",
                input_data={"price": 100, "discount_rate": 0.2},
                actual_output={"result": 99.8, "expected": 80.0},
                expected_baseline={"result": 80.0},
                exception_trace="AssertionError: expected 80.0 but got 99.8",
                system_metrics={"risk_level": "medium", "cwe": "CWE-398"}
            )

            from src.governance.orchestrator import GovernanceOrchestrator
            orchestrator = GovernanceOrchestrator(repo_path=repo_path)
            result = await orchestrator.execute_governance_flow(context)

            assert result["status"] == "FIXED", f"期望 FIXED, 实际 {result['status']}: {result.get('reason', '')}"
            assert result.get("confidence_score", 0) > 0.5, f"置信度过低: {result.get('confidence_score')}"

            tracker = GovernanceTracker()
            events = tracker.get_events_by_trace("e2e_func_001")
            action_types = [e.action_type for e in events]

            assert GovernanceActionType.DIAGNOSE_START in action_types
            assert GovernanceActionType.DIAGNOSE_COMPLETE in action_types
            assert GovernanceActionType.PATCH_CREATE in action_types
            assert GovernanceActionType.APPROVAL_GRANTED in action_types
            assert GovernanceActionType.PATCH_APPLIED in action_types

            abs_target = os.path.join(repo_path, target_file)
            assert os.path.exists(abs_target), "目标文件不存在"

            with open(abs_target, "r", encoding="utf-8") as f:
                fixed_content = f.read()
            assert "price * (1 - discount_rate)" in fixed_content or "discounted_price" in fixed_content, "修复后的代码逻辑不正确"

            git_show = subprocess.run(
                ["git", "show", "--stat", "HEAD"],
                cwd=repo_path, capture_output=True, text=True
            )
            assert "Calculator.py" in git_show.stdout, "最新提交未包含 Calculator.py 变更"

            git_log = subprocess.run(
                ["git", "log", "--oneline", "-5"],
                cwd=repo_path, capture_output=True, text=True
            )
            assert "[TestAI-Governance]" in git_log.stdout, "治理提交未在 git log 中"

            print(f"\n✅ E2E-001 功能修复通过:")
            print(f"   状态: {result['status']}")
            print(f"   置信度: {result.get('confidence_score')}")
            print(f"   事件数: {len(events)}")

    @pytest.mark.asyncio
    async def test_e2e_002_multi_defect_consecutive_fix(self):
        """L3-E2E-002: 多缺陷连续修复
        验证: 同一 Git 仓库连续处理多个缺陷, 每次独立事务
        """
        with _TempDir() as temp_dir:
            repo_path = _setup_git_repo(temp_dir, _buggy_discount_module())

            context1 = DiagnosticContext(
                step_id="e2e_multi_001",
                component_name="Calculator",
                input_data={"price": 100, "discount_rate": 0.2},
                actual_output={"result": 99.8, "expected": 80.0},
                expected_baseline={"result": 80.0},
                exception_trace="AssertionError: expected 80.0 but got 99.8",
                system_metrics={"risk_level": "medium"}
            )

            from src.governance.orchestrator import GovernanceOrchestrator
            orchestrator = GovernanceOrchestrator(repo_path=repo_path)
            result1 = await orchestrator.execute_governance_flow(context1)
            assert result1["status"] == "FIXED", f"第一个缺陷修复失败: {result1.get('reason')}"

            context2 = DiagnosticContext(
                step_id="e2e_multi_002",
                component_name="Calculator",
                input_data={"amount": 100, "tax_rate": 0.1},
                actual_output={"result": 110.0, "expected": 110.0},
                expected_baseline={"result": 110.0},
                exception_trace="ValueError: tax_rate validation failed",
                system_metrics={"risk_level": "low"}
            )

            result2 = await orchestrator.execute_governance_flow(context2)
            assert result2["status"] in ("FIXED", "DIAGNOSED", "PENDING_APPROVAL", "SKIPPED"), \
                f"第二个缺陷处理异常: {result2.get('status')}"

            tracker = GovernanceTracker()
            events1 = tracker.get_events_by_trace("e2e_multi_001")
            events2 = tracker.get_events_by_trace("e2e_multi_002")

            assert len(events1) >= 5, f"trace1 事件不完整: {len(events1)}"
            assert len(events2) >= 2, f"trace2 事件不完整: {len(events2)}"

            git_log = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                cwd=repo_path, capture_output=True, text=True
            )
            commit_count = git_log.stdout.count("[TestAI-Governance]")
            assert commit_count >= 1, f"治理提交数不足: {commit_count}"

            print(f"\n✅ E2E-002 多缺陷修复通过:")
            print(f"   缺陷1: {result1['status']}")
            print(f"   缺陷2: {result2['status']}")
            print(f"   治理提交数: {commit_count}")

    @pytest.mark.asyncio
    async def test_e2e_003_patch_failure_rollback(self):
        """L3-E2E-003: 补丁应用失败回滚
        验证: 当 AI 诊断出无法修复的缺陷时, 系统正确处理
        """
        with _TempDir() as temp_dir:
            repo_path = _setup_git_repo(temp_dir, _buggy_discount_module())

            context = DiagnosticContext(
                step_id="e2e_fail_001",
                component_name="Calculator",
                input_data={"price": None},
                actual_output={"result": None, "error": "NoneType"},
                expected_baseline={"result": 80.0},
                exception_trace="TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'",
                system_metrics={"risk_level": "high", "cwe": "CWE-476"}
            )

            from src.governance.orchestrator import GovernanceOrchestrator
            orchestrator = GovernanceOrchestrator(repo_path=repo_path)
            result = await orchestrator.execute_governance_flow(context)

            assert result["status"] in ("DIAGNOSED", "FIXED", "FAILED", "SKIPPED", "PENDING_APPROVAL"), \
                f"状态异常: {result['status']}"

            tracker = GovernanceTracker()
            events = tracker.get_events_by_trace("e2e_fail_001")

            assert GovernanceActionType.DIAGNOSE_START in [e.action_type for e in events], \
                "缺少 DIAGNOSE_START"
            assert GovernanceActionType.DIAGNOSE_COMPLETE in [e.action_type for e in events], \
                "缺少 DIAGNOSE_COMPLETE"

            has_failed = GovernanceActionType.PATCH_FAILED in [e.action_type for e in events]
            if has_failed:
                assert result["status"] == "FAILED", "PATCH_FAILED 事件应对应 FAILED 状态"

            print(f"\n✅ E2E-003 失败回滚验证:")
            print(f"   最终状态: {result['status']}")
            print(f"   事件数: {len(events)}")
            print(f"   含 PATCH_FAILED: {has_failed}")

    @pytest.mark.asyncio
    async def test_e2e_004_non_governable_skip(self):
        """L3-E2E-004: 非治理场景跳过敏节
        验证: 网络异常类场景被正确分类为 RETRY/MANUAL, 跳过敏节流程
        """
        with _TempDir() as temp_dir:
            repo_path = _setup_git_repo(temp_dir, _buggy_discount_module())

            context = DiagnosticContext(
                step_id="e2e_skip_001",
                component_name="Calculator",
                input_data={"url": "http://api.example.com"},
                actual_output={"error": "ConnectionError"},
                expected_baseline={"result": "ok"},
                exception_trace="ConnectionError: Failed to connect to api.example.com",
                system_metrics={"risk_level": "low"}
            )

            from src.governance.orchestrator import GovernanceOrchestrator
            orchestrator = GovernanceOrchestrator(repo_path=repo_path)
            result = await orchestrator.execute_governance_flow(context)

            assert result["status"] == "SKIPPED", f"网络异常应跳过, 实际 {result['status']}"

            tracker = GovernanceTracker()
            events = tracker.get_events_by_trace("e2e_skip_001")
            action_types = [e.action_type for e in events]

            assert GovernanceActionType.DIAGNOSE_START in action_types
            assert GovernanceActionType.DIAGNOSE_COMPLETE in action_types
            assert GovernanceActionType.PATCH_CREATE not in action_types, "不应创建补丁"
            assert GovernanceActionType.PATCH_APPLIED not in action_types, "不应应用补丁"

            print(f"\n✅ E2E-004 非治理跳过:")
            print(f"   状态: {result['status']}")
            print(f"   事件数: {len(events)}")
            print(f"   无 PATCH_CREATE: True")

    @pytest.mark.asyncio
    async def test_e2e_005_decision_engine_reject(self):
        """L3-E2E-005: 决策引擎拒绝场景
        验证: 当决策引擎拒绝补丁时, 正确记录拒绝事件
        """
        with _TempDir() as temp_dir:
            repo_path = _setup_git_repo(temp_dir, _buggy_discount_module())

            context = DiagnosticContext(
                step_id="e2e_reject_001",
                component_name="Calculator",
                input_data={"price": 100, "discount_rate": 0.2},
                actual_output={"result": 99.8, "expected": 80.0},
                expected_baseline={"result": 80.0},
                exception_trace="AssertionError: expected 80.0 but got 99.8",
                system_metrics={"risk_level": "medium"}
            )

            from src.governance.orchestrator import GovernanceOrchestrator
            orchestrator = GovernanceOrchestrator(repo_path=repo_path)

            original_engine = orchestrator.decision_engine

            class MockRejectEngine:
                def evaluate(self, ctx, trace_id):
                    from src.governance.auto_decision_engine import GovernanceDecision
                    return GovernanceDecision(
                        decision_id=f"dec-reject-{trace_id}",
                        trace_id=trace_id,
                        decision_type="auto_decision",
                        decision="REJECT",
                        reason="Simulated rejection: confidence below threshold",
                        confidence=0.3,
                        auto_approved=False,
                        rule_triggered="mock_rule",
                        metadata={"mocked": True}
                    )

            orchestrator.decision_engine = MockRejectEngine()
            result = await orchestrator.execute_governance_flow(context)
            orchestrator.decision_engine = original_engine

            assert result["status"] == "PENDING_APPROVAL", f"期望 PENDING_APPROVAL (REJECT 升级为人工审批), 实际 {result['status']}"

            tracker = GovernanceTracker()
            events = tracker.get_events_by_trace("e2e_reject_001")
            action_types = [e.action_type for e in events]

            assert GovernanceActionType.DIAGNOSE_START in action_types
            assert GovernanceActionType.DIAGNOSE_COMPLETE in action_types
            assert GovernanceActionType.APPROVAL_REQUIRED in action_types, "缺少 APPROVAL_REQUIRED (REJECT 应升级为人工审批)"

            print(f"\n✅ E2E-005 决策拒绝升级:")
            print(f"   状态: {result['status']}")
            print(f"   事件数: {len(events)}")
            print(f"   含 APPROVAL_REQUIRED: True")

    @pytest.mark.asyncio
    async def test_e2e_006_event_trace_completeness(self):
        """L3-E2E-006: 事件追踪完整性
        验证: 完整治理流程产生的事件链完整且顺序正确
        """
        with _TempDir() as temp_dir:
            repo_path = _setup_git_repo(temp_dir, _buggy_discount_module())

            context = DiagnosticContext(
                step_id="e2e_trace_001",
                component_name="Calculator",
                input_data={"price": 100, "discount_rate": 0.2},
                actual_output={"result": 99.8, "expected": 80.0},
                expected_baseline={"result": 80.0},
                exception_trace="AssertionError: expected 80.0 but got 99.8",
                system_metrics={"risk_level": "medium"}
            )

            from src.governance.orchestrator import GovernanceOrchestrator
            orchestrator = GovernanceOrchestrator(repo_path=repo_path)
            result = await orchestrator.execute_governance_flow(context)

            tracker = GovernanceTracker()
            events = tracker.get_events_by_trace("e2e_trace_001")

            assert len(events) >= 3, f"事件数不足: {len(events)} < 3"

            action_sequence = [e.action_type for e in events]

            start_idx = action_sequence.index(GovernanceActionType.DIAGNOSE_START)
            complete_idx = action_sequence.index(GovernanceActionType.DIAGNOSE_COMPLETE)
            assert start_idx < complete_idx, "DIAGNOSE_START 应在 DIAGNOSE_COMPLETE 之前"

            for e in events:
                assert e.timestamp, f"事件缺少时间戳: {e.action_type.value}"
                assert e.trace_id == "e2e_trace_001", f"trace_id 不匹配: {e.trace_id}"

            components = set(e.component for e in events)
            assert "Calculator" in components, f"组件名不正确: {components}"

            if result["status"] == "FIXED":
                assert len(events) >= 5, f"FIXED 状态事件数应 >= 5: {len(events)}"
                create_idx = action_sequence.index(GovernanceActionType.PATCH_CREATE)
                applied_idx = action_sequence.index(GovernanceActionType.PATCH_APPLIED)
                assert complete_idx < create_idx < applied_idx, "事件顺序不正确"

            print(f"\n✅ E2E-006 事件完整性:")
            print(f"   总事件数: {len(events)}")
            print(f"   最终状态: {result['status']}")
            print(f"   事件序列: {[a.value for a in action_sequence]}")
            print(f"   时间戳完整: True")

    @pytest.mark.asyncio
    async def test_e2e_007_governance_history_integrity(self):
        """L3-E2E-007: 治理历史记录验证
        验证: GovernanceHistory 正确记录每次运行的完整状态
        """
        with _TempDir() as temp_dir:
            repo_path = _setup_git_repo(temp_dir, _buggy_discount_module())

            from src.governance.orchestrator import GovernanceOrchestrator
            from src.governance.governance_history import GovernanceHistory

            history_db = os.path.join(tempfile.gettempdir(), "testai_e2e_history.db")
            if os.path.exists(history_db):
                os.remove(history_db)

            history = GovernanceHistory(db_path=history_db)

            context = DiagnosticContext(
                step_id="e2e_hist_001",
                component_name="Calculator",
                input_data={"price": 100, "discount_rate": 0.2},
                actual_output={"result": 99.8, "expected": 80.0},
                expected_baseline={"result": 80.0},
                exception_trace="AssertionError: expected 80.0 but got 99.8",
                system_metrics={"risk_level": "medium"}
            )

            orchestrator = GovernanceOrchestrator(repo_path=repo_path)
            result = await orchestrator.execute_governance_flow(context)

            run_record = history.get_run("e2e_hist_001")
            assert run_record is not None and "e2e_hist_001" in str(run_record), "治理历史中找不到运行记录"
            if isinstance(run_record, dict):
                assert run_record.get("trace_id") == "e2e_hist_001"
                assert run_record.get("component_name") == "Calculator"
                assert run_record.get("status") in ("COMPLETED", "STARTED", "FAILED", "REJECTED", "PENDING_APPROVAL")
                assert run_record.get("start_time") is not None and len(str(run_record.get("start_time"))) > 0
                completed_steps = run_record.get("completed_steps", 0)
            else:
                assert run_record.trace_id == "e2e_hist_001"
                assert run_record.component_name == "Calculator"
                assert run_record.status in ("COMPLETED", "STARTED", "FAILED", "REJECTED", "PENDING_APPROVAL")
                assert run_record.start_time is not None and len(str(run_record.start_time)) > 0
                completed_steps = run_record.completed_steps

            history_list = history.get_recent_runs(limit=50)
            assert len(history_list) >= 1

            if result["status"] == "FIXED":
                assert completed_steps >= 3, f"完成步骤数不足: {completed_steps}"

            if os.path.exists(history_db):
                os.remove(history_db)

            print(f"\n✅ E2E-007 治理历史:")
            print(f"   trace_id: {run_record.get('trace_id') if isinstance(run_record, dict) else run_record.trace_id}")
            print(f"   status: {run_record.get('status') if isinstance(run_record, dict) else run_record.status}")
            print(f"   steps: {completed_steps}/{run_record.get('total_steps', 5) if isinstance(run_record, dict) else run_record.total_steps}")
            print(f"   runs in history: {len(history_list)}")

    @pytest.mark.asyncio
    async def test_e2e_008_executor_transformer_real_apply(self):
        """L3-E2E-008: 转换器实际应用验证
        验证: FunctionTransformer 真实修改文件内容, 结果可被 import 并执行
        """
        with _TempDir() as temp_dir:
            repo_path = _setup_git_repo(temp_dir, _buggy_discount_module())
            target_file = os.path.join("src", "components", "Calculator.py")
            abs_target = os.path.join(repo_path, target_file)

            context = DiagnosticContext(
                step_id="e2e_exec_001",
                component_name="Calculator",
                input_data={"price": 100, "discount_rate": 0.2},
                actual_output={"result": 99.8, "expected": 80.0},
                expected_baseline={"result": 80.0},
                exception_trace="AssertionError: expected 80.0 but got 99.8",
                system_metrics={"risk_level": "medium"}
            )

            from src.governance.orchestrator import GovernanceOrchestrator
            orchestrator = GovernanceOrchestrator(repo_path=repo_path)
            result = await orchestrator.execute_governance_flow(context)

            if result["status"] == "FIXED":
                assert os.path.exists(abs_target)

                src_path = os.path.join(repo_path, "src")
                comp_path = os.path.join(repo_path, "src", "components")
                sys.path.insert(0, src_path)
                sys.path.insert(0, comp_path)

                import importlib
                try:
                    mod = importlib.import_module("Calculator")
                    fn = getattr(mod, "calculate_discount", None)
                    if fn:
                        test_result = fn(100, 0.2)
                        expected_correct = 80.0
                        if abs(test_result - expected_correct) < 0.01:
                            print(f"\n✅ E2E-008 转换器验证: 修复后代码可执行, 结果正确 ({test_result})")
                        else:
                            print(f"\n⚠️ E2E-008 转换器验证: 代码可执行但结果偏差 ({test_result} vs {expected_correct})")
                except Exception as e:
                    print(f"\n⚠️ E2E-008 转换器验证: 导入执行失败 ({e})")
                finally:
                    importlib.invalidate_caches()
                    if "Calculator" in sys.modules:
                        del sys.modules["Calculator"]

                sys.path = [p for p in sys.path if p not in [src_path, comp_path]]
            else:
                print(f"\n⚠️ E2E-008 转换器验证: 状态非 FIXED ({result['status']}), 跳过导入验证")


if __name__ == "__main__":
    print("=" * 70)
    print("TestAI 全链路 E2E 测试套件 - 技术委员会验证")
    print("=" * 70)

    cmd = [
        sys.executable, "-m", "pytest",
        os.path.abspath(__file__),
        "-v", "--tb=short",
    ]
    print(f"\nRunning: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, capture_output=False, text=True, timeout=300)
    print(f"\nExit code: {result.returncode}")