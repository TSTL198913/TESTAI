"""
端到端治理闭环测试: 异常→分类→诊断→审批→Git→补丁→收敛

测试目标: 验证 GovernanceOrchestrator 的完整六步治理闭环在真实集成下可用。

真实组件 (非 mock):
  - GitTransactionManager (临时 git 仓库, 真实 branch/commit)
  - GovernanceExecutor (真实 libcst 补丁应用, 真实安全检查 is_safe_patch)
  - ApprovalManager (真实审批逻辑: requires_approval 基于 patch_type + 代码行数, 临时 SQLite)
  - GovernanceTracker (真实事件记录, 临时 SQLite)
  - GovernanceOrchestrator (真实六步编排)

Mock 组件 (per 用户规则: 测试环境强制 mock LLM):
  - AIGovernanceAgent.analyze_with_context (返回预设诊断结果, 不调真实 LLM)

唯一 mock 的非业务逻辑 (有独立单元测试, 此处不重复):
  - SecurePathValidator (路径校验, 因 tmp_path 不在项目 ALLOWED_DIRS 下)
  - Orchestrator._resolve_file_path (文件路径映射, 指向临时文件)

覆盖场景:
  1. 正向: TypeError → 完整六步闭环 → FIXED (补丁应用 + Git 提交 + 收敛记录)
  2. 边界: PatchType.SECURITY → PENDING_APPROVAL (审批闸门拦截, 不自动应用)
  3. 负向: 网络异常 → SKIPPED (分类为 RETRY, 不触发 AI 诊断)
  4. 异常: Agent 崩溃 → FAILED (异常兜底, 不崩溃, 返回错误信息)
"""
import json
import logging
import subprocess
import threading
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.governance.approval import ApprovalManager
from src.governance.models import AIGovernanceResult, DiagnosticContext, PatchProposal
from src.governance.orchestrator import GovernanceOrchestrator
from src.governance.registry import PatchType
from src.governance.tracker import GovernanceActionType, GovernanceTracker


# ==================== 测试夹具与辅助函数 ====================

BUGGY_CODE = """def calculate_score(a, b):
    return a - b
"""

FIXED_BODY = "return a + b"


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """创建临时 git 仓库, 含一个有 bug 的 Python 文件。

    返回目标文件路径。仓库包含一个初始提交 (master 或 main 分支)。
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init"], cwd=str(tmp_path), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "TestAI-E2E"],
        cwd=str(tmp_path), check=True, capture_output=True,
    )

    target_file = tmp_path / "calculator.py"
    target_file.write_text(BUGGY_CODE, encoding="utf-8")

    subprocess.run(
        ["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "initial: buggy calculator"],
        cwd=str(tmp_path), check=True, capture_output=True,
    )
    return target_file


def _create_fresh_tracker(tmp_path: Path) -> GovernanceTracker:
    """创建非单例 GovernanceTracker 实例 (避免污染全局单例和 data/governance.db)。

    使用 object.__new__ 绕过单例 __new__, 创建完全独立的实例。
    """
    tracker = object.__new__(GovernanceTracker)
    tracker._events = []
    tracker._db_path = tmp_path / "test_tracker.db"
    tracker._db_lock = threading.Lock()
    tracker._lock = threading.RLock()
    tracker._consecutive_convergence_count = 0
    tracker._consecutive_convergence_threshold = 3
    tracker._init_db()
    return tracker


def _create_fresh_approval_mgr(tmp_path: Path) -> ApprovalManager:
    """创建非单例 ApprovalManager 实例 (避免污染全局单例和 data/governance.db)。"""
    mgr = object.__new__(ApprovalManager)
    mgr._approvals = {}
    mgr._db_path = tmp_path / "test_approval.db"
    mgr._db_lock = threading.Lock()
    mgr._lock = threading.RLock()
    mgr._initialized = True
    mgr._init_db()
    return mgr


def _make_mock_agent_result(patch_type: PatchType = PatchType.FUNCTIONAL) -> AIGovernanceResult:
    """创建 mock agent 诊断结果。

    per 用户规则: 测试环境强制 mock LLM API 调用。
    source="llm" 标记为 LLM 诊断 (非 mock/fallback), 使审批引擎正常评估。
    """
    return AIGovernanceResult(
        is_fixable=True,
        reasoning="Function uses subtraction instead of addition",
        root_cause="Operator error: '-' should be '+'",
        patch_proposal=PatchProposal(
            target_function="calculate_score",
            suggested_code=FIXED_BODY,
            patch_type=patch_type,
            required_imports=[],
        ),
        confidence_score=0.95,
        source="llm",
    )


def _build_orchestrator(tmp_path: Path, target_file: Path) -> GovernanceOrchestrator:
    """构建一个使用真实组件 + mock LLM 的 orchestrator。

    - GitTransactionManager: 真实, repo_path=tmp_path
    - GovernanceExecutor: 真实 (libcst 补丁应用), 仅 mock 路径校验
    - ApprovalManager: 真实 (非单例, 临时 db)
    - GovernanceTracker: 真实 (非单例, 临时 db)
    - AIGovernanceAgent: mock (返回预设诊断)
    - _resolve_file_path: mock (指向临时文件)
    """
    orch = GovernanceOrchestrator(repo_path=str(tmp_path))

    # 替换单例为独立实例 (避免污染全局状态)
    orch.tracker = _create_fresh_tracker(tmp_path)
    orch.approval_mgr = _create_fresh_approval_mgr(tmp_path)

    # Mock LLM agent
    orch.agent = MagicMock()
    orch.agent.analyze_with_context = AsyncMock(
        return_value=_make_mock_agent_result()
    )

    # Mock 路径解析 (指向临时文件, 非业务逻辑)
    orch._resolve_file_path = MagicMock(return_value=str(target_file))

    # Mock 路径校验 (tmp_path 不在项目 ALLOWED_DIRS 下, 路径校验有独立单元测试)
    orch.executor._path_validator.validate_path = MagicMock(
        return_value=(True, "test mode: path validation bypassed for E2E")
    )

    return orch


def _git_log(tmp_path: Path) -> str:
    """获取 git log (所有分支)。"""
    result = subprocess.run(
        ["git", "log", "--oneline", "--all"],
        cwd=str(tmp_path), capture_output=True, text=True, check=True,
    )
    return result.stdout


# ==================== 测试用例 ====================


class TestE2EGovernanceClosedLoop:
    """端到端治理闭环: 异常→分类→诊断→审批→Git→补丁→收敛。

    使用真实 Git 仓库 + 真实 executor + 真实 tracker, 仅 mock LLM agent。
    """

    @pytest.mark.asyncio
    async def test_full_flow_typeerror_to_fixed(self, tmp_path):
        """正向: TypeError → 分类(AI_DIAGNOSE) → 诊断 → 自动审批 → Git提交 → 补丁应用 → 收敛记录。

        验证 7 个维度:
        1. 分类正确: TypeError → AI_DIAGNOSE (orchestrator._classify_exception)
        2. 诊断调用: agent.analyze_with_context 被调用一次
        3. 审批闸门: PatchType.FUNCTIONAL + <20行 → 自动批准 (非 PENDING_APPROVAL)
        4. Git事务: governance 分支有提交记录
        5. 补丁应用: 目标文件函数体从 'a - b' 改为 'a + b'
        6. 收敛记录: tracker 记录 PATCH_APPLIED + CONVERGED/DIVERGED
        7. 返回值: status=FIXED, 可 JSON 序列化 (Celery 后端要求)
        """
        trace_id = f"e2e-fixed-{uuid.uuid4().hex[:8]}"
        target_file = _create_temp_git_repo(tmp_path)
        orch = _build_orchestrator(tmp_path, target_file)

        context = DiagnosticContext(
            step_id=trace_id,
            component_name="Calculator",
            input_data={"args": [1, 2]},
            actual_output="TypeError: unsupported operand type(s)",
            expected_baseline=None,
            exception_trace="TypeError: unsupported operand type(s) for -: 'int' and 'str'",
        )

        # ---- Act: 触发治理流程 ----
        result = await orch.execute_governance_flow(context)

        # ---- Assert 1: 返回值 status=FIXED ----
        assert isinstance(result, dict), f"结果应是 dict, 实际: {type(result)}"
        assert result["status"] == "FIXED", (
            f"完整治理流程应返回 FIXED, 实际: {result.get('status')} — "
            f"说明某步骤失败 (分类/诊断/审批/Git/补丁)"
        )

        # ---- Assert 2: 返回值可 JSON 序列化 (Celery 后端要求) ----
        serialized = json.dumps(result)
        roundtripped = json.loads(serialized)
        assert roundtripped["status"] == "FIXED"

        # ---- Assert 3: 补丁已真实应用到文件 ----
        patched_content = target_file.read_text(encoding="utf-8")
        assert "return a + b" in patched_content, (
            "目标文件应被补丁修改: 'return a - b' → 'return a + b'"
        )
        assert "return a - b" not in patched_content, (
            "原始 bug 代码应已被替换 — 补丁未生效"
        )

        # ---- Assert 4: Git 事务已提交 ----
        log_output = _git_log(tmp_path)
        assert "TestAI-Governance" in log_output, (
            f"Git log 应包含治理提交消息 '[TestAI-Governance]', 实际:\n{log_output}"
        )

        # ---- Assert 5: agent 被调用一次 (诊断步骤执行) ----
        orch.agent.analyze_with_context.assert_called_once_with(context)

        # ---- Assert 6: 审计追踪 (tracker events) 完整 ----
        events = orch.tracker.get_events_by_trace(trace_id)
        action_types = [e.action_type for e in events]

        # 必须包含关键治理步骤 (六步闭环的审计证据)
        assert GovernanceActionType.DIAGNOSE_START in action_types, (
            "缺少 DIAGNOSE_START 事件 — 治理流程未启动"
        )
        assert GovernanceActionType.PATCH_CREATE in action_types, (
            "缺少 PATCH_CREATE 事件 — 补丁创建步骤未执行"
        )
        assert GovernanceActionType.APPROVAL_GRANTED in action_types, (
            "缺少 APPROVAL_GRANTED 事件 — 自动审批未执行 "
            "(FUNCTIONAL + <20行 应自动批准)"
        )
        assert GovernanceActionType.PATCH_APPLIED in action_types, (
            "缺少 PATCH_APPLIED 事件 — 补丁应用步骤未执行"
        )

        # PATCH_APPLIED 事件状态必须是 FIXED
        patch_applied_events = [
            e for e in events
            if e.action_type == GovernanceActionType.PATCH_APPLIED
        ]
        assert len(patch_applied_events) == 1, (
            f"应有且仅有 1 个 PATCH_APPLIED 事件, 实际: {len(patch_applied_events)}"
        )
        assert patch_applied_events[0].status == "FIXED", (
            f"PATCH_APPLIED 状态应为 FIXED, 实际: {patch_applied_events[0].status}"
        )

        # 收敛步骤必须执行 (CONVERGED 或 DIVERGED)
        convergence_events = [
            e for e in events
            if e.action_type in (
                GovernanceActionType.CONVERGED,
                GovernanceActionType.DIVERGED,
            )
        ]
        assert len(convergence_events) >= 1, (
            "缺少收敛事件 (CONVERGED/DIVERGED) — 收敛评估步骤未执行"
        )

        # ---- Assert 7: 审批记录状态 ----
        tx_id = f"tx_{trace_id}"
        approval_record = orch.approval_mgr.get_approval(tx_id)
        assert approval_record is not None, "审批记录应存在"
        from src.governance.approval import ApprovalStatus
        assert approval_record.status == ApprovalStatus.APPROVED, (
            f"审批记录状态应为 APPROVED (自动批准), 实际: {approval_record.status}"
        )

    @pytest.mark.asyncio
    async def test_security_patch_triggers_pending_approval(self, tmp_path):
        """边界: PatchType.SECURITY → requires_approval=True → PENDING_APPROVAL。

        验证审批闸门:
        - SECURITY 类型补丁必须人工审批, 不自动应用
        - 文件未被修改, Git 无治理提交
        - 返回值含 approval_required=True, tx_id, patch_type="security"
        """
        trace_id = f"e2e-sec-{uuid.uuid4().hex[:8]}"
        target_file = _create_temp_git_repo(tmp_path)
        orch = _build_orchestrator(tmp_path, target_file)

        # Override: 使用 SECURITY patch type (requires_approval=True)
        orch.agent.analyze_with_context = AsyncMock(
            return_value=_make_mock_agent_result(PatchType.SECURITY)
        )

        context = DiagnosticContext(
            step_id=trace_id,
            component_name="Calculator",
            input_data={},
            actual_output="TypeError: unsupported operand type(s)",
            expected_baseline=None,
            exception_trace="TypeError: unsupported operand type(s) for -: 'int' and 'str'",
        )

        result = await orch.execute_governance_flow(context)

        # ---- Assert: status=PENDING_APPROVAL ----
        assert result["status"] == "PENDING_APPROVAL", (
            f"SECURITY 补丁应触发 PENDING_APPROVAL, 实际: {result.get('status')}"
        )
        assert result.get("approval_required") is True, (
            "PENDING_APPROVAL 结果应含 approval_required=True"
        )
        assert "tx_id" in result, "PENDING_APPROVAL 结果应含 tx_id"
        assert result.get("patch_type") == "security", (
            f"patch_type 应为 'security' (字符串), 实际: {result.get('patch_type')}"
        )
        assert isinstance(result["patch_type"], str), (
            "patch_type 必须是字符串 (Celery JSON 序列化要求)"
        )

        # ---- Assert: 文件未被修改 (未经审批) ----
        content = target_file.read_text(encoding="utf-8")
        assert "return a - b" in content, (
            "SECURITY 补丁未经审批不应修改文件"
        )
        assert "return a + b" not in content, (
            "SECURITY 补丁未经审批不应写入修复代码"
        )

        # ---- Assert: Git 无治理提交 ----
        log_output = _git_log(tmp_path)
        assert "TestAI-Governance" not in log_output, (
            f"SECURITY 补丁未经审批不应有 Git 提交:\n{log_output}"
        )

        # ---- Assert: 审批记录状态为 PENDING ----
        tx_id = result["tx_id"]
        approval_record = orch.approval_mgr.get_approval(tx_id)
        assert approval_record is not None, "审批记录应存在"
        from src.governance.approval import ApprovalStatus
        assert approval_record.status == ApprovalStatus.PENDING, (
            f"审批记录状态应为 PENDING (待人工审批), 实际: {approval_record.status}"
        )

        # ---- Assert: tracker 记录 APPROVAL_REQUIRED ----
        events = orch.tracker.get_events_by_trace(trace_id)
        action_types = [e.action_type for e in events]
        assert GovernanceActionType.APPROVAL_REQUIRED in action_types, (
            "缺少 APPROVAL_REQUIRED 事件 — 审批闸门未触发"
        )
        assert GovernanceActionType.PATCH_APPLIED not in action_types, (
            "不应有 PATCH_APPLIED 事件 — SECURITY 补丁未经审批不应应用"
        )

        # ---- Assert: 返回值可 JSON 序列化 ----
        json.dumps(result)

    @pytest.mark.asyncio
    async def test_network_exception_skipped(self, tmp_path):
        """负向: 网络异常 → 分类(RETRY) → SKIPPED (不触发 AI 诊断)。

        验证分类器:
        - ConnectionRefusedError → RETRY (非 AI_DIAGNOSE)
        - 返回 SKIPPED, agent 不被调用, Git 无提交, 文件未修改
        """
        trace_id = f"e2e-net-{uuid.uuid4().hex[:8]}"
        target_file = _create_temp_git_repo(tmp_path)
        orch = _build_orchestrator(tmp_path, target_file)

        context = DiagnosticContext(
            step_id=trace_id,
            component_name="HTTPProcessor",
            input_data={"url": "http://localhost:8080/health"},
            actual_output="ConnectionRefusedError",
            expected_baseline=None,
            exception_trace="ConnectionRefusedError: [Errno 111] Connection refused",
        )

        result = await orch.execute_governance_flow(context)

        # ---- Assert: status=SKIPPED ----
        assert result["status"] == "SKIPPED", (
            f"网络异常应分类为 RETRY → SKIPPED, 实际: {result.get('status')}"
        )
        assert result["reason"] == "Non-governable", (
            f"SKIPPED 原因应为 'Non-governable', 实际: {result.get('reason')}"
        )

        # ---- Assert: agent 不被调用 (网络异常不触发 AI 诊断) ----
        orch.agent.analyze_with_context.assert_not_called()

        # ---- Assert: 文件未修改 ----
        content = target_file.read_text(encoding="utf-8")
        assert "return a - b" in content, "网络异常不应触发补丁应用"

        # ---- Assert: Git 无治理提交 ----
        log_output = _git_log(tmp_path)
        assert "TestAI-Governance" not in log_output, "网络异常不应触发 Git 事务"

        # ---- Assert: tracker 无 PATCH_CREATE / PATCH_APPLIED ----
        events = orch.tracker.get_events_by_trace(trace_id)
        action_types = [e.action_type for e in events]
        assert GovernanceActionType.PATCH_CREATE not in action_types, (
            "网络异常不应触发补丁创建"
        )
        assert GovernanceActionType.PATCH_APPLIED not in action_types, (
            "网络异常不应触发补丁应用"
        )

        # ---- Assert: 返回值可 JSON 序列化 ----
        json.dumps(result)

    @pytest.mark.asyncio
    async def test_agent_failure_returns_failed(self, tmp_path):
        """异常: Agent 崩溃 → FAILED (异常兜底, 不崩溃)。

        验证异常处理:
        - agent.analyze_with_context 抛异常 → 返回 FAILED
        - 返回值含 error 字段, 可 JSON 序列化
        - tracker 记录 DIAGNOSE_COMPLETE status=FAILED
        """
        trace_id = f"e2e-fail-{uuid.uuid4().hex[:8]}"
        target_file = _create_temp_git_repo(tmp_path)
        orch = _build_orchestrator(tmp_path, target_file)

        # Override: agent 抛异常
        orch.agent.analyze_with_context = AsyncMock(
            side_effect=RuntimeError("LLM service unavailable")
        )

        context = DiagnosticContext(
            step_id=trace_id,
            component_name="Calculator",
            input_data={},
            actual_output="TypeError: unsupported operand type(s)",
            expected_baseline=None,
            exception_trace="TypeError: unsupported operand type(s) for -: 'int' and 'str'",
        )

        result = await orch.execute_governance_flow(context)

        # ---- Assert: status=FAILED ----
        assert result["status"] == "FAILED", (
            f"Agent 崩溃应返回 FAILED, 实际: {result.get('status')}"
        )
        assert "error" in result, "FAILED 结果应含 error 字段"
        assert "LLM service unavailable" in result["error"], (
            f"error 应包含异常信息, 实际: {result.get('error')}"
        )

        # ---- Assert: 文件未修改 (Agent 崩溃不触发补丁) ----
        content = target_file.read_text(encoding="utf-8")
        assert "return a - b" in content, "Agent 崩溃不应触发补丁应用"

        # ---- Assert: Git 无治理提交 ----
        log_output = _git_log(tmp_path)
        assert "TestAI-Governance" not in log_output, "Agent 崩溃不应触发 Git 事务"

        # ---- Assert: tracker 记录 DIAGNOSE_COMPLETE status=FAILED ----
        events = orch.tracker.get_events_by_trace(trace_id)
        diagnose_complete_events = [
            e for e in events
            if e.action_type == GovernanceActionType.DIAGNOSE_COMPLETE
        ]
        assert len(diagnose_complete_events) >= 1, (
            "Agent 崩溃应记录 DIAGNOSE_COMPLETE 事件"
        )
        assert any(
            e.status == "FAILED" for e in diagnose_complete_events
        ), "DIAGNOSE_COMPLETE 状态应为 FAILED"

        # ---- Assert: 返回值可 JSON 序列化 (Celery 要求) ----
        json.dumps(result)

    @pytest.mark.asyncio
    async def test_result_json_serializable_for_all_paths(self, tmp_path):
        """依赖: 所有治理路径的返回值可被 JSON 序列化 (Celery 后端存储要求)。

        这是 P0 BUG 的核心不变量: tasks.py 返回 orchestrator 结果 →
        Celery JSON 后端序列化存储 → 若含 PatchType 枚举则崩溃。

        覆盖 4 条返回路径: SKIPPED / FAILED / PENDING_APPROVAL / FIXED
        """
        import json

        trace_base = f"e2e-json-{uuid.uuid4().hex[:8]}"

        # ---- 路径1: SKIPPED (网络异常) ----
        target1 = _create_temp_git_repo(tmp_path / "repo1")
        orch1 = _build_orchestrator(tmp_path / "repo1", target1)
        ctx1 = DiagnosticContext(
            step_id=f"{trace_base}-1",
            component_name="HTTPProcessor",
            input_data={},
            actual_output="ConnectionRefusedError",
            expected_baseline=None,
            exception_trace="ConnectionRefusedError: connection refused",
        )
        result1 = await orch1.execute_governance_flow(ctx1)
        assert result1["status"] == "SKIPPED"
        json.dumps(result1)  # 不抛 TypeError

        # ---- 路径2: FAILED (agent 崩溃) ----
        target2 = _create_temp_git_repo(tmp_path / "repo2")
        orch2 = _build_orchestrator(tmp_path / "repo2", target2)
        orch2.agent.analyze_with_context = AsyncMock(
            side_effect=RuntimeError("LLM crashed")
        )
        ctx2 = DiagnosticContext(
            step_id=f"{trace_base}-2",
            component_name="Calculator",
            input_data={},
            actual_output="TypeError",
            expected_baseline=None,
            exception_trace="TypeError: unsupported operand",
        )
        result2 = await orch2.execute_governance_flow(ctx2)
        assert result2["status"] == "FAILED"
        json.dumps(result2)

        # ---- 路径3: PENDING_APPROVAL (SECURITY 补丁) ----
        target3 = _create_temp_git_repo(tmp_path / "repo3")
        orch3 = _build_orchestrator(tmp_path / "repo3", target3)
        orch3.agent.analyze_with_context = AsyncMock(
            return_value=_make_mock_agent_result(PatchType.SECURITY)
        )
        ctx3 = DiagnosticContext(
            step_id=f"{trace_base}-3",
            component_name="Calculator",
            input_data={},
            actual_output="TypeError",
            expected_baseline=None,
            exception_trace="TypeError: unsupported operand",
        )
        result3 = await orch3.execute_governance_flow(ctx3)
        assert result3["status"] == "PENDING_APPROVAL"
        # patch_type 必须是字符串, 不是 PatchType 枚举
        assert isinstance(result3.get("patch_type"), str), (
            f"patch_type 应为字符串, 实际: {type(result3.get('patch_type'))}"
        )
        json.dumps(result3)

        # ---- 路径4: FIXED (FUNCTIONAL 补丁, 自动批准) ----
        target4 = _create_temp_git_repo(tmp_path / "repo4")
        orch4 = _build_orchestrator(tmp_path / "repo4", target4)
        ctx4 = DiagnosticContext(
            step_id=f"{trace_base}-4",
            component_name="Calculator",
            input_data={},
            actual_output="TypeError",
            expected_baseline=None,
            exception_trace="TypeError: unsupported operand",
        )
        result4 = await orch4.execute_governance_flow(ctx4)
        assert result4["status"] == "FIXED"
        json.dumps(result4)
