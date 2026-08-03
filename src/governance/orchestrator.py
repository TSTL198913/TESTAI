import ast
import json
import logging
import os
import time
from contextlib import contextmanager
from typing import Optional, Dict, Any

from src.governance.agent import AIGovernanceAgent
from src.governance.metrics import GovernanceMetrics


class _ClassCollector(ast.NodeVisitor):
    """AST visitor that collects class names from source code.
    
    Used for analyzing class structures during governance flow.
    """

    def __init__(self):
        self.class_names = set()

    def visit_ClassDef(self, node: ast.ClassDef):
        self.class_names.add(node.name)
        self.generic_visit(node)


from src.governance.approval import ApprovalManager, ApprovalStatus
from src.governance.executor import GovernanceExecutor
from src.governance.git_manager import GitTransactionManager
from src.governance.auto_decision_engine import AutoDecisionEngine
from src.governance.models import (
    DecisionContextInput,
    DiagnosticContext,
    GovernanceAction,
    PatchProposal,
)
from src.governance.tracker import GovernanceActionType, GovernanceTracker


@contextmanager
def governance_transaction(
    git_mgr: GitTransactionManager, tx_id: str, proposal: PatchProposal
):
    logger = logging.getLogger("GovernanceTransaction")
    try:
        logger.info(
            f"[AUDIT_PRE] Starting transaction {tx_id} for function: {proposal.target_function}"
        )
        git_mgr.start_transaction(tx_id)

        yield

        git_mgr.commit(f"[TestAI-Governance][{tx_id}] Fixed {proposal.target_function}")
        logger.info(f"[AUDIT_POST] Transaction {tx_id} committed successfully.")
    except Exception as e:
        logger.error(
            f"[AUDIT_FAILURE] Transaction {tx_id} failed: {str(e)}. Rolling back."
        )
        git_mgr.rollback(tx_id)
        raise e


class GovernanceOrchestrator:
    def __init__(self, repo_path: str = "."):
        self.logger = logging.getLogger(__name__)
        self.agent = AIGovernanceAgent()
        self.executor = GovernanceExecutor()
        self.git_mgr = GitTransactionManager(repo_path)
        self.approval_mgr = ApprovalManager()
        self.tracker = GovernanceTracker()
        self._metrics = GovernanceMetrics()
        # AutoDecisionEngine: AI 规则决策引擎 (单例), 处理置信度/source/已知模式规则。
        # 与 ApprovalManager 结构闸门互补: 结构闸门优先, engine 处理 AI 规则。
        self._decision_engine = AutoDecisionEngine()

    async def execute_governance_flow(self, context: DiagnosticContext):
        """P4 治理指标接入: 在外层包装记录流程计数器与耗时直方图 (规则1)。

        实际逻辑委托给 _execute_governance_flow_impl; 包装层捕获最终 status
        (FIXED/FAILED/SKIPPED/PENDING_APPROVAL/DIAGNOSED) 并在 finally 中记录,
        确保任何返回路径 (含异常) 都不漏记指标。
        """
        start = time.monotonic()
        status = "ERROR"
        try:
            result = await self._execute_governance_flow_impl(context)
            status = result.get("status", "UNKNOWN") if isinstance(result, dict) else "UNKNOWN"
            return result
        finally:
            self._metrics.record_flow(status, time.monotonic() - start)

    async def _execute_governance_flow_impl(self, context: DiagnosticContext):
        trace_id = context.step_id or "unknown"
        self.tracker.record_event(
            trace_id=trace_id,
            action_type=GovernanceActionType.DIAGNOSE_START,
            component=context.component_name,
            step_id=context.step_id,
        )

        action = self._classify_exception(context)
        if action != GovernanceAction.AI_DIAGNOSE:
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.DIAGNOSE_COMPLETE,
                component=context.component_name,
                step_id=context.step_id,
                status="SKIPPED",
                message="Non-governable action",
            )
            return {
                "status": "SKIPPED",
                "reason": "Non-governable",
                "confidence_score": 0.0,
                "reasoning": "Non-governable action",
                "suggested_fix": None,
            }

        # P1-1/P1-2 修复:Agent 异常必须捕获并补全审计链,避免流程崩溃
        try:
            diagnosis = await self.agent.analyze_with_context(context)
        except Exception as e:
            self.logger.critical(
                f"Agent diagnosis failed for trace {trace_id}: {e}",
                exc_info=True,
            )
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.DIAGNOSE_COMPLETE,
                component=context.component_name,
                step_id=context.step_id,
                status="FAILED",
                message=f"Agent exception: {type(e).__name__}: {e}",
            )
            return {
                "status": "FAILED",
                "error": str(e),
                "reason": f"Agent diagnosis failed: {e}",
                "confidence_score": 0.0,
                "reasoning": f"Agent raised {type(e).__name__}",
                "suggested_fix": None,
            }

        result = {
            "status": "DIAGNOSED",
            "reason": diagnosis.reasoning,
            "confidence_score": diagnosis.confidence_score,
            "reasoning": diagnosis.reasoning,
            "suggested_fix": (
                diagnosis.patch_proposal.suggested_code
                if diagnosis.patch_proposal
                else None
            ),
        }

        self.tracker.record_event(
            trace_id=trace_id,
            action_type=GovernanceActionType.DIAGNOSE_COMPLETE,
            component=context.component_name,
            step_id=context.step_id,
            status="DIAGNOSED",
            confidence_score=diagnosis.confidence_score,
        )

        if not diagnosis.is_fixable or not diagnosis.patch_proposal:
            result["status"] = "SKIPPED"
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.DIAGNOSE_COMPLETE,
                component=context.component_name,
                step_id=context.step_id,
                status="SKIPPED",
                message="Not fixable",
            )
            return result

        tx_id = f"tx_{context.step_id}"
        proposal = diagnosis.patch_proposal

        self.tracker.record_event(
            trace_id=trace_id,
            action_type=GovernanceActionType.PATCH_CREATE,
            component=context.component_name,
            step_id=context.step_id,
            tx_id=tx_id,
            patch_type=proposal.patch_type,
        )

        self.approval_mgr.create_approval(tx_id, proposal, context)

        # P0/P1-1 修复: 审批决策接入 AutoDecisionEngine (AI 规则引擎) + ApprovalManager (结构闸门)。
        # 两道闸门互补:
        #   闸门1 ApprovalManager.requires_approval: security/refactoring/行数>=20 (结构性, 优先级最高)
        #   闸门2 AutoDecisionEngine.evaluate: 置信度/source 来源/已知模式 (AI 规则)
        # 关键修复: orchestrator 原不检查诊断 source, mock/fallback 降级诊断若高置信
        # 会被自动批准写入真实代码 (P0)。AutoDecisionEngine 的 source 守卫补此缺口。
        # 决策映射: 仅 AUTO_APPROVE 且闸门1通过才执行补丁; 其余一律 PENDING_APPROVAL (零行为回退)。
        try:
            decision_input = DecisionContextInput(
                confidence=(
                    diagnosis.confidence_score
                    if diagnosis.confidence_score is not None
                    else 0.0
                ),
                is_fixable=diagnosis.is_fixable,
                source=diagnosis.source,
                patch_type=proposal.patch_type.value,
                consecutive_failures=0,  # TODO: 后续从 GovernanceTracker 查询组件历史失败次数
                patch_category="",        # TODO: 后续从 PatchProposal 派生分类
                status="",                # 审批阶段无 DIVERGED 状态
            )
            engine_decision = self._decision_engine.evaluate(
                decision_input.model_dump(), trace_id=tx_id
            )
        except (ValueError, TypeError) as e:
            # 安全降级: 引擎异常 → 走人工, 不阻断流程, 结构化日志记录 (禁止裸 except 吞没)
            self.logger.error(
                f"AutoDecisionEngine.evaluate failed for {tx_id}: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            engine_decision = None

        # 闸门1: 结构性规则 (security/refactoring/行数>=20) 优先级最高, 覆盖引擎决策。
        # 原因: AutoDecisionEngine 的 rule_security_requires_manual(P80) 被
        # rule_auto_approve_high_confidence(P100) 遮蔽, SECURITY+高置信会触发 AUTO_APPROVE,
        # 故 SECURITY 守卫由 ApprovalManager 结构闸门负责。
        structural_requires_approval = self.approval_mgr.requires_approval(tx_id)
        if structural_requires_approval:
            effective_decision = "REQUIRE_MANUAL"
            effective_reason = "structural gate: security/refactoring/>=20 lines"
        elif engine_decision is None:
            effective_decision = "REQUIRE_MANUAL"
            effective_reason = "engine unavailable (exception)"
        else:
            effective_decision = engine_decision.decision
            effective_reason = engine_decision.reason

        # 决策映射: 仅 AUTO_APPROVE 进入补丁执行;
        # REJECT/REQUIRE_MANUAL/ESCALATE/AUTO_ROLLBACK 一律 PENDING_APPROVAL (保留人工)。
        # AUTO_ROLLBACK 在审批阶段无补丁可回滚, 降级为人工。
        if effective_decision != "AUTO_APPROVE":
            result["status"] = "PENDING_APPROVAL"
            result["approval_required"] = True
            result["tx_id"] = tx_id
            result["patch_type"] = proposal.patch_type.value
            result["approval_reason"] = effective_reason
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.APPROVAL_REQUIRED,
                component=context.component_name,
                step_id=context.step_id,
                tx_id=tx_id,
                patch_type=proposal.patch_type,
                status="PENDING_APPROVAL",
            )
            self.logger.info(
                f"[GOVERNANCE] Approval required for {tx_id} "
                f"({proposal.patch_type.value}, decision={effective_decision}, "
                f"reason={effective_reason})"
            )
            return result

        self.approval_mgr.approve(tx_id, approver="system", reason="Auto-approved")
        self.tracker.record_event(
            trace_id=trace_id,
            action_type=GovernanceActionType.APPROVAL_GRANTED,
            component=context.component_name,
            step_id=context.step_id,
            tx_id=tx_id,
            message="Auto-approved by system",
        )

        try:
            with governance_transaction(self.git_mgr, tx_id, proposal):
                target_file = self._resolve_file_path(context.component_name)

                target_class = None
                target_function = proposal.target_function
                if "." in target_function:
                    parts = target_function.split(".")
                    target_class, target_function = parts[0], parts[1]

                success = await self.executor.apply_patch(
                    file_path=target_file,
                    patch_type=proposal.patch_type,
                    target_function=target_function,
                    target_class=target_class,
                    suggested_code=proposal.suggested_code,
                    required_imports=proposal.required_imports,
                )

                if not success:
                    raise RuntimeError(f"Executor failed to apply patch for {tx_id}")

            evaluation_result = self._evaluate_patch_quality(proposal, context)
            result["evaluation"] = evaluation_result

            result["status"] = "FIXED"
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.PATCH_APPLIED,
                component=context.component_name,
                step_id=context.step_id,
                tx_id=tx_id,
                patch_type=proposal.patch_type,
                status="FIXED",
                evaluation_score=evaluation_result.get("score", 0.0),
                evaluation_grade=evaluation_result.get("grade", "unknown"),
            )

            self._check_and_record_convergence(
                trace_id=trace_id,
                context=context,
                evaluation_score=evaluation_result.get("score", 0.0),
            )

            return result

        except Exception as e:
            self.logger.critical(f"Governance flow failed for {tx_id}: {e}")
            result["status"] = "FAILED"
            result["reason"] = str(e)
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.PATCH_FAILED,
                component=context.component_name,
                step_id=context.step_id,
                tx_id=tx_id,
                patch_type=proposal.patch_type,
                status="FAILED",
                message=str(e),
            )
            return result

    def _classify_exception(self, context: DiagnosticContext) -> GovernanceAction:
        """P1-3 修复:基于异常 trace 与基线偏差分类治理动作。

        分类规则(大小写不敏感):
        - 网络/超时异常 → RETRY(可重试恢复)
        - 代码级异常 → AI_DIAGNOSE(AI 诊断修复)
        - 空 trace 但存在基线偏差(actual != expected) → AI_DIAGNOSE
        - 空 trace 且无基线偏差 → MANUAL_REQUIRED(人工介入)
        - 未知异常 → MANUAL_REQUIRED(人工介入)

        Args:
            context: 诊断上下文,包含 exception_trace / actual_output / expected_baseline 字段

        Returns:
            GovernanceAction 枚举值
        """
        trace = (context.exception_trace or "").lower()

        # 无异常 trace 时:检查是否存在基线偏差
        if not trace:
            actual = (context.actual_output or "").strip()
            expected = (context.expected_baseline or "").strip()
            # 存在基线偏差:需要 AI 诊断根因
            if actual and expected and actual != expected:
                return GovernanceAction.AI_DIAGNOSE
            # 既无异常 trace 也无基线偏差:无法自动诊断
            return GovernanceAction.MANUAL_REQUIRED

        # 网络/超时类异常:可重试恢复
        network_keywords = [
            "connectionerror",
            "timeout",
            "timeouterror",
            "connectionreset",
            "connectionrefused",
            "network unreachable",
            "connection aborted",
            "connection refused",
            "connection reset",
        ]
        if any(kw in trace for kw in network_keywords):
            return GovernanceAction.RETRY

        # 代码级异常:AI 诊断修复
        code_keywords = [
            "syntaxerror",
            "nameerror",
            "typeerror",
            "valueerror",
            "attributeerror",
            "keyerror",
            "indexerror",
            "zerodivisionerror",
            "importerror",
            "modulenotfounderror",
            "recursionerror",
            "notimplementederror",
            "assertionerror",
        ]
        if any(kw in trace for kw in code_keywords):
            return GovernanceAction.AI_DIAGNOSE

        # 未知异常:人工介入
        return GovernanceAction.MANUAL_REQUIRED

    def _resolve_file_path(self, component_name: str) -> str:
        if component_name is None:
            component_name = "None"
        
        if ".." in component_name or "/" in component_name or "\\" in component_name:
            raise ValueError(f"Invalid component name: {component_name}")
        
        mapping = {
            "EvalPlatformProcessor": "extensions/eval_platform/processor.py",
            "HTTPProcessor": "src/engine/processor/http.py",
            "AssertionProcessor": "src/engine/processor/assertion.py",
            "GovernanceProcessor": "src/engine/processor/governance_processor.py",
            "DataProcessor": "src/engine/processor/data.py",
            "GRPCProcessor": "src/engine/processor/grpc.py",
            "EngineProcessor": "src/engine/processor/base.py",
        }
        
        # 动态查找: 先尝试精确映射, 再尝试在 src/ 下搜索
        if component_name in mapping:
            relative_path = mapping[component_name]
        else:
            # 通用回退策略: 搜索 src/ 目录下匹配的 .py 文件
            import glob
            component_lower = component_name.lower()
            # 尝试在常见目录下查找
            search_dirs = ["src/engine", "src/platform", "src/governance", "src/ai", "src/core", "src/security"]
            found = None
            for d in search_dirs:
                # 查找文件名包含组件名的文件 (如 HTTPProcessor -> http.py 或 http_processor.py)
                files = glob.glob(f"{d}/**/*.py", recursive=True)
                for f in files:
                    basename = os.path.basename(f).replace(".py", "")
                    # 简单匹配: 文件名包含组件名的核心部分 (忽略大小写和 Processor 后缀)
                    core_name = component_lower.replace("processor", "")
                    if core_name in basename.lower():
                        found = f
                        break
                if found:
                    break
            
            if found:
                relative_path = found
            else:
                # 最后兜底: 默认放到 engine 目录
                relative_path = f"src/engine/processor/{component_name.lower().replace('processor', '')}.py"
        
        abs_path = os.path.abspath(relative_path)
        project_root = os.path.abspath(".")
        
        if not abs_path.startswith(project_root + os.sep) and abs_path != project_root:
            raise ValueError(f"Path traversal detected: {component_name} -> {abs_path}")
        
        return relative_path

    def _evaluate_patch_quality(self, proposal, context) -> Dict[str, Any]:
        try:
            from src.ai.evaluator import AIEvaluator

            evaluator = AIEvaluator()
            expected_output = context.expected_baseline or ""
            actual_output = context.actual_output or ""

            if expected_output and actual_output:
                evaluation = evaluator.evaluate(actual_output, expected_output)
                return evaluation.to_dict()
            else:
                return {
                    "grade": "fair",
                    "score": 0.5,
                    "matches_expected": None,
                    "similarity": 0.0,
                    "correctness": 0.0,
                    "completeness": 0.0,
                    "confidence": 0.5,
                    "explanation": "Insufficient data for evaluation",
                    "discrepancies": {},
                    "suggestions": {},
                }
        except Exception as e:
            self.logger.warning(f"Patch evaluation failed: {e}")
            return {
                "grade": "fair",
                "score": 0.5,
                "matches_expected": None,
                "similarity": 0.0,
                "correctness": 0.0,
                "completeness": 0.0,
                "confidence": 0.3,
                "explanation": f"Evaluation error: {str(e)}",
                "discrepancies": {},
                "suggestions": {},
            }

    def _check_and_record_convergence(
        self,
        trace_id: str,
        context: DiagnosticContext,
        evaluation_score: float,
    ):
        CONVERGENCE_THRESHOLD = 0.7
        if evaluation_score >= CONVERGENCE_THRESHOLD:
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.CONVERGED,
                component=context.component_name,
                step_id=context.step_id,
                status="CONVERGED",
                metadata={
                    "evaluation_score": evaluation_score,
                    "consecutive_count": self.tracker.get_consecutive_convergence_count() + 1,
                },
            )
            self.logger.info(
                f"[CONVERGENCE] Patch quality score {evaluation_score:.2f} >= {CONVERGENCE_THRESHOLD}. "
                f"Convergence recorded for trace {trace_id}"
            )
        else:
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.DIVERGED,
                component=context.component_name,
                step_id=context.step_id,
                status="DIVERGED",
                metadata={
                    "evaluation_score": evaluation_score,
                    "threshold": CONVERGENCE_THRESHOLD,
                },
            )
            self.tracker.reset_consecutive_convergence_count()
            self.logger.warning(
                f"[DIVERGENCE] Patch quality score {evaluation_score:.2f} < {CONVERGENCE_THRESHOLD}. "
                f"Convergence counter reset for trace {trace_id}"
            )

    async def approve_and_apply(
        self, tx_id: str, approver: str, reason: Optional[str] = None
    ):
        record = self.approval_mgr.get_approval(tx_id)
        if not record:
            return {"status": "FAILED", "reason": "Approval record not found"}

        trace_id = record.context.step_id or tx_id
        context = record.context

        if record.status != ApprovalStatus.PENDING:
            return {"status": "FAILED", "reason": f"Approval already processed (status: {record.status.value})"}

        if not self.approval_mgr.approve(tx_id, approver, reason):
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.APPROVAL_REJECTED,
                component=context.component_name,
                tx_id=tx_id,
                patch_type=record.proposal.patch_type,
                status="REJECTED",
                message="Approval failed",
                approver=approver,
            )
            return {"status": "FAILED", "reason": "Approval failed"}

        self.tracker.record_event(
            trace_id=trace_id,
            action_type=GovernanceActionType.APPROVAL_GRANTED,
            component=context.component_name,
            tx_id=tx_id,
            patch_type=record.proposal.patch_type,
            status="APPROVED",
            approver=approver,
            reason=reason,
        )

        proposal = record.proposal

        try:
            with governance_transaction(self.git_mgr, tx_id, proposal):
                target_file = self._resolve_file_path(context.component_name)

                target_class = None
                target_function = proposal.target_function
                if "." in target_function:
                    parts = target_function.split(".")
                    target_class, target_function = parts[0], parts[1]

                success = await self.executor.apply_patch(
                    file_path=target_file,
                    patch_type=proposal.patch_type,
                    target_function=target_function,
                    target_class=target_class,
                    suggested_code=proposal.suggested_code,
                    required_imports=proposal.required_imports,
                )

                if not success:
                    raise RuntimeError(f"Executor failed to apply patch for {tx_id}")

            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.PATCH_APPLIED,
                component=context.component_name,
                tx_id=tx_id,
                patch_type=proposal.patch_type,
                status="FIXED",
                approver=approver,
            )

            return {
                "status": "FIXED",
                "tx_id": tx_id,
                "approved_by": approver,
                "reason": reason,
                "patch_type": proposal.patch_type.value,
            }

        except Exception as e:
            self.logger.critical(f"Approved patch application failed for {tx_id}: {e}")
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.PATCH_FAILED,
                component=context.component_name,
                tx_id=tx_id,
                patch_type=proposal.patch_type,
                status="FAILED",
                message=str(e),
                approver=approver,
            )
            return {"status": "FAILED", "reason": str(e)}
