import logging
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any

from src.governance.governance_history import GovernanceDecision, GovernanceHistory  # pylint: disable=import-error,no-name-in-module
from src.governance.metrics import GovernanceMetrics


@dataclass
class DecisionRule:
    rule_id: str
    name: str
    description: str
    condition: str
    action: str
    priority: int = 0
    enabled: bool = True
    confidence_threshold: float = 0.8


class AutoDecisionEngine:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:  # pylint: disable=access-member-before-definition
            return
        self._initialized = True
        self._rules: List[DecisionRule] = []
        self._history = GovernanceHistory()
        self._logger = logging.getLogger("AutoDecisionEngine")
        self._decision_handlers: Dict[str, Callable] = {}
        self._rules_lock = threading.RLock()  # P0-7 Fix: Thread safety for rule operations
        self._metrics = GovernanceMetrics()
        self._register_default_rules()
        self._register_default_handlers()

    def _register_default_rules(self):
        self._rules = [
            DecisionRule(
                rule_id="rule_auto_approve_high_confidence",
                name="Auto-Approve High Confidence",
                description="Automatically approve patches with confidence >= 0.9",
                condition="confidence >= 0.9 AND is_fixable = True",
                action="AUTO_APPROVE",
                priority=100,
                confidence_threshold=0.9,
            ),
            DecisionRule(
                rule_id="rule_reject_low_confidence",
                name="Reject Low Confidence",
                description="Reject patches with confidence < 0.5",
                condition="confidence < 0.5",
                action="REJECT",
                priority=90,
                confidence_threshold=0.5,
            ),
            DecisionRule(
                rule_id="rule_security_requires_manual",
                name="Security Requires Manual Review",
                description="Security patches always require manual approval",
                condition="patch_type = security",
                action="REQUIRE_MANUAL",
                priority=80,
            ),
            DecisionRule(
                rule_id="rule_auto_approve_known_pattern",
                name="Auto-Approve Known Pattern",
                description="Auto-approve patches matching known safe patterns (e.g., import ordering, docstring fixes)",
                condition="patch_category IN ('import_organize', 'docstring_fix', 'formatting')",
                action="AUTO_APPROVE",
                priority=70,
                confidence_threshold=0.8,
            ),
            DecisionRule(
                rule_id="rule_escalate_multiple_failures",
                name="Escalate After Multiple Failures",
                description="Require manual review after 3 consecutive patch failures for same component",
                condition="consecutive_failures >= 3",
                action="ESCALATE",
                priority=60,
            ),
            DecisionRule(
                rule_id="rule_auto_rollback_on_diverge",
                name="Auto-Rollback On Divergence",
                description="Automatically trigger rollback when baseline diverges",
                condition="status = 'DIVERGED'",
                action="AUTO_ROLLBACK",
                priority=50,
            ),
        ]

    def _register_default_handlers(self):
        self._decision_handlers = {
            "AUTO_APPROVE": self._handle_auto_approve,
            "REJECT": self._handle_reject,
            "REQUIRE_MANUAL": self._handle_require_manual,
            "ESCALATE": self._handle_escalate,
            "AUTO_ROLLBACK": self._handle_auto_rollback,
        }

    AUTO_ACTIONS = {"AUTO_APPROVE", "REJECT", "AUTO_ROLLBACK"}

    def evaluate(
        self,
        context: Dict[str, Any],
        trace_id: str,
    ) -> GovernanceDecision:
        if not context:
            raise ValueError("Context cannot be empty")
        if not trace_id:
            raise ValueError("trace_id is required")

        sorted_rules = sorted(
            [r for r in self._rules if r.enabled],
            key=lambda r: r.priority,
            reverse=True,
        )

        for rule in sorted_rules:
            if self._evaluate_rule(rule, context):
                decision = GovernanceDecision(
                    decision_id=f"dec-{int(time.time())}-{rule.rule_id}",
                    trace_id=trace_id,
                    decision_type="auto_decision",
                    decision=rule.action,
                    reason=f"Rule '{rule.name}' triggered: {rule.description}",
                    confidence=context.get("confidence", 0.0),
                    auto_approved=(rule.action in self.AUTO_ACTIONS),
                    rule_triggered=rule.rule_id,
                    metadata={
                        "rule_name": rule.name,
                        "context_keys": list(context.keys()),
                        "patch_type": context.get("patch_type", "unknown"),
                    },
                )
                self._history.record_decision(decision)
                self._logger.info(
                    f"Auto decision: {decision.decision} (rule: {rule.rule_id}, "
                    f"trace: {trace_id}, confidence: {decision.confidence})"
                )
                self._metrics.record_decision(decision.decision)
                return decision

        decision = GovernanceDecision(
            decision_id=f"dec-{int(time.time())}-default",
            trace_id=trace_id,
            decision_type="auto_decision",
            decision="REQUIRE_MANUAL",
            reason="No matching rule - requiring manual review",
            confidence=context.get("confidence", 0.0),
            auto_approved=False,
            rule_triggered=None,
            metadata={"context_keys": list(context.keys())},
        )
        self._history.record_decision(decision)
        self._logger.info(
            f"Default decision: REQUIRE_MANUAL (trace: {trace_id})"
        )
        self._metrics.record_decision(decision.decision)
        return decision

    def _evaluate_rule(self, rule: DecisionRule, context: Dict[str, Any]) -> bool:
        """P0-7 Fix: Improved error handling with specific exception types.
        
        Note: Current implementation uses string matching on rule.condition.
        This is a known limitation - for production, consider implementing
        a proper expression parser or using lambda functions for conditions.
        """
        try:
            condition = rule.condition

            if "confidence >= 0.9" in condition and "is_fixable = True" in condition:
                confidence = context.get("confidence", 0)
                is_fixable = context.get("is_fixable", False)
                if not isinstance(confidence, (int, float)):
                    self._logger.warning(f"Invalid confidence type in context for rule {rule.rule_id}")
                    return False
                return (
                    confidence >= 0.9
                    and is_fixable is True
                )
            elif "confidence < 0.5" in condition:
                confidence = context.get("confidence", 1)
                if not isinstance(confidence, (int, float)):
                    self._logger.warning(f"Invalid confidence type in context for rule {rule.rule_id}")
                    return False
                return confidence < 0.5
            elif "patch_type = security" in condition:
                return context.get("patch_type", "") == "security"
            elif "patch_category IN" in condition:
                allowed = ["import_organize", "docstring_fix", "formatting"]
                return context.get("patch_category", "") in allowed
            elif "consecutive_failures >= 3" in condition:
                consecutive_failures = context.get("consecutive_failures", 0)
                if not isinstance(consecutive_failures, (int, float)):
                    self._logger.warning(f"Invalid consecutive_failures type in context for rule {rule.rule_id}")
                    return False
                return consecutive_failures >= 3
            elif "status = 'DIVERGED'" in condition or 'status = "DIVERGED"' in condition:
                return context.get("status", "") == "DIVERGED"

            return False
        except (KeyError, TypeError, ValueError) as e:
            self._logger.error(f"Error evaluating rule {rule.rule_id}: {e}")
            return False
        except Exception as e:
            self._logger.error(f"Unexpected error evaluating rule {rule.rule_id}: {e}")
            return False

    def _handle_auto_approve(self, decision: GovernanceDecision) -> Dict[str, Any]:
        self._logger.info(f"AUTO_APPROVE: trace={decision.trace_id}")
        return {"status": "approved", "auto": True, "reason": decision.reason}

    def _handle_reject(self, decision: GovernanceDecision) -> Dict[str, Any]:
        self._logger.info(f"REJECT: trace={decision.trace_id}")
        return {"status": "rejected", "auto": True, "reason": decision.reason}

    def _handle_require_manual(self, decision: GovernanceDecision) -> Dict[str, Any]:
        self._logger.info(f"REQUIRE_MANUAL: trace={decision.trace_id}")
        return {"status": "pending_manual", "auto": False, "reason": decision.reason}

    def _handle_escalate(self, decision: GovernanceDecision) -> Dict[str, Any]:
        self._logger.info(f"ESCALATE: trace={decision.trace_id}")
        return {"status": "escalated", "auto": False, "reason": decision.reason}

    def _handle_auto_rollback(self, decision: GovernanceDecision) -> Dict[str, Any]:
        self._logger.info(f"AUTO_ROLLBACK: trace={decision.trace_id}")
        return {"status": "rolled_back", "auto": True, "reason": decision.reason}

    def get_rules(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """P0-7 Fix: Thread-safe rule retrieval."""
        with self._rules_lock:
            rules = self._rules if not enabled_only else [r for r in self._rules if r.enabled]
        return [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "description": r.description,
                "condition": r.condition,
                "action": r.action,
                "priority": r.priority,
                "enabled": r.enabled,
                "confidence_threshold": r.confidence_threshold,
            }
            for r in rules
        ]

    def add_rule(self, rule: DecisionRule) -> None:
        """P0-7 Fix: Thread-safe rule addition."""
        with self._rules_lock:
            self._rules.append(rule)
            self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, rule_id: str) -> bool:
        """P0-7 Fix: Thread-safe rule removal."""
        with self._rules_lock:
            for i, rule in enumerate(self._rules):
                if rule.rule_id == rule_id:
                    self._rules.pop(i)
                    return True
            return False

    def enable_rule(self, rule_id: str) -> bool:
        """P0-7 Fix: Thread-safe rule enable."""
        with self._rules_lock:
            for rule in self._rules:
                if rule.rule_id == rule_id:
                    rule.enabled = True
                    return True
            return False

    def disable_rule(self, rule_id: str) -> bool:
        """P0-7 Fix: Thread-safe rule disable."""
        with self._rules_lock:
            for rule in self._rules:
                if rule.rule_id == rule_id:
                    rule.enabled = False
                    return True
            return False

    def get_decision_history(self, trace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if trace_id:
            return self._history.get_decision_by_trace(trace_id)
        return self._history.get_recent_decisions()

    def get_stats(self) -> Dict[str, Any]:
        summary = self._history.get_summary()
        return {
            "total_decisions": summary["total_decisions"],
            "auto_approved_rate": summary["auto_approved_rate"],
            "decision_counts": summary["decision_counts"],
            "active_rules": len([r for r in self._rules if r.enabled]),
            "total_rules": len(self._rules),
        }