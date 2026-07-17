import json
import logging
from contextlib import contextmanager
from typing import Optional

from src.governance.agent import AIGovernanceAgent
from src.governance.approval import ApprovalManager, ApprovalStatus
from src.governance.executor import GovernanceExecutor
from src.governance.git_manager import GitTransactionManager
from src.governance.models import (DiagnosticContext, GovernanceAction,
                                   PatchProposal)
from src.governance.tracker import GovernanceActionType, GovernanceTracker


@contextmanager
def governance_transaction(git_mgr: GitTransactionManager, tx_id: str, proposal: PatchProposal):
    logger = logging.getLogger("GovernanceTransaction")
    try:
        logger.info(f"[AUDIT_PRE] Starting transaction {tx_id} for function: {proposal.target_function}")
        git_mgr.start_transaction(tx_id)

        yield

        git_mgr.commit(f"[TestAI-Governance][{tx_id}] Fixed {proposal.target_function}")
        logger.info(f"[AUDIT_POST] Transaction {tx_id} committed successfully.")
    except Exception as e:
        logger.error(f"[AUDIT_FAILURE] Transaction {tx_id} failed: {str(e)}. Rolling back.")
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
            step_id=context.step_id
        )

        action = self._classify_exception(context)
        if action != GovernanceAction.AI_DIAGNOSE:
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.DIAGNOSE_COMPLETE,
                component=context.component_name,
                step_id=context.step_id,
                status="SKIPPED",
                message="Non-governable action"
            )
            return {
                "status": "SKIPPED",
                "reason": "Non-governable",
                "confidence_score": 0.0,
                "reasoning": "Non-governable action",
                "suggested_fix": None
            }

        diagnosis = await self.agent.analyze_with_context(context)

        result = {
            "status": "DIAGNOSED",
            "reason": diagnosis.reasoning,
            "confidence_score": diagnosis.confidence_score,
            "reasoning": diagnosis.reasoning,
            "suggested_fix": diagnosis.patch_proposal.suggested_code if diagnosis.patch_proposal else None
        }

        self.tracker.record_event(
            trace_id=trace_id,
            action_type=GovernanceActionType.DIAGNOSE_COMPLETE,
            component=context.component_name,
            step_id=context.step_id,
            status="DIAGNOSED",
            confidence_score=diagnosis.confidence_score
        )

        if not diagnosis.is_fixable or not diagnosis.patch_proposal:
            result["status"] = "SKIPPED"
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.DIAGNOSE_COMPLETE,
                component=context.component_name,
                step_id=context.step_id,
                status="SKIPPED",
                message="Not fixable"
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
            patch_type=proposal.patch_type
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
                status="PENDING_APPROVAL"
            )
            self.logger.info(f"[GOVERNANCE] Approval required for {tx_id} ({proposal.patch_type.value})")
            return result

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
                    required_imports=proposal.required_imports
                )

                if not success:
                    raise RuntimeError(f"Executor failed to apply patch for {tx_id}")

            result["status"] = "FIXED"
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.PATCH_APPLIED,
                component=context.component_name,
                step_id=context.step_id,
                tx_id=tx_id,
                patch_type=proposal.patch_type,
                status="FIXED"
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
                message=str(e)
            )
            return result

    def _classify_exception(self, context: DiagnosticContext) -> GovernanceAction:
        return GovernanceAction.AI_DIAGNOSE

    def _resolve_file_path(self, component_name: str) -> str:
        mapping = {"EvalPlatformProcessor": "extensions/eval_platform/processor.py"}
        return mapping.get(component_name, f"src/components/{component_name}.py")

    async def approve_and_apply(self, tx_id: str, approver: str, reason: Optional[str] = None):
        record = self.approval_mgr.get_approval(tx_id)
        if not record:
            return {"status": "FAILED", "reason": "Approval record not found"}

        trace_id = record.context.step_id or tx_id
        context = record.context

        if not self.approval_mgr.approve(tx_id, approver, reason):
            self.tracker.record_event(
                trace_id=trace_id,
                action_type=GovernanceActionType.APPROVAL_REJECTED,
                component=context.component_name,
                tx_id=tx_id,
                patch_type=record.proposal.patch_type,
                status="REJECTED",
                message="Approval failed",
                approver=approver
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
            reason=reason
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
                    required_imports=proposal.required_imports
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
                approver=approver
            )

            return {
                "status": "FIXED",
                "tx_id": tx_id,
                "approved_by": approver,
                "reason": reason,
                "patch_type": proposal.patch_type.value
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
                approver=approver
            )
            return {"status": "FAILED", "reason": str(e)}