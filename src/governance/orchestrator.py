import json
import logging
import os
from contextlib import contextmanager
from typing import Optional, Dict, Any

from src.governance.agent import AIGovernanceAgent
from src.governance.approval import ApprovalManager, ApprovalStatus
from src.governance.executor import GovernanceExecutor
from src.governance.git_manager import GitTransactionManager
from src.governance.models import DiagnosticContext, GovernanceAction, PatchProposal
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

    async def execute_governance_flow(self, context: DiagnosticContext):
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

        if self.approval_mgr.requires_approval(tx_id):
            result["status"] = "PENDING_APPROVAL"
            result["approval_required"] = True
            result["tx_id"] = tx_id
            result["patch_type"] = proposal.patch_type.value
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
                f"[GOVERNANCE] Approval required for {tx_id} ({proposal.patch_type.value})"
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
        
        mapping = {"EvalPlatformProcessor": "extensions/eval_platform/processor.py"}
        relative_path = mapping.get(component_name, f"src/components/{component_name}.py")
        
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
