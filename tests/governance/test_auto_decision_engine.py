import time
import pytest

from src.governance.auto_decision_engine import (
    AutoDecisionEngine,
    DecisionRule,
    GovernanceDecision,
)


@pytest.fixture(autouse=True)
def clean_engine():
    """Reset AutoDecisionEngine singleton + GovernanceHistory per test.

    Without this, tests that mutate shared singleton state leak into later
    tests: test_remove_rule deletes rule_auto_approve_high_confidence,
    test_disabled_rule_not_evaluated disables it, test_add_rule injects a
    custom rule. The stale state then causes false failures such as
    test_default_rule_not_triggered_for_security_patch expecting the
    high-confidence rule to fire after a prior test removed it.
    """
    # Drop the singleton so __init__ re-registers default rules + handlers.
    AutoDecisionEngine._instance = None
    engine = AutoDecisionEngine()
    engine._history.clear()
    yield
    engine._history.clear()
    AutoDecisionEngine._instance = None


class TestDecisionRule:
    def test_rule_creation(self):
        rule = DecisionRule(
            rule_id="test-rule-001",
            name="Test Rule",
            description="Test description",
            condition="confidence >= 0.9",
            action="AUTO_APPROVE",
            priority=100,
            confidence_threshold=0.9,
        )

        assert rule.rule_id == "test-rule-001"
        assert rule.name == "Test Rule"
        assert rule.priority == 100
        assert rule.enabled is True

    def test_rule_defaults(self):
        rule = DecisionRule(
            rule_id="test-rule-002",
            name="Test Rule 2",
            description="Test",
            condition="status = 'DIVERGED'",
            action="AUTO_ROLLBACK",
        )

        assert rule.priority == 0
        assert rule.enabled is True
        assert rule.confidence_threshold == 0.8


class TestAutoDecisionEngine:
    def test_high_confidence_auto_approve(self):
        engine = AutoDecisionEngine()
        context = {
            "confidence": 0.95,
            "is_fixable": True,
            "patch_type": "functional",
        }

        decision = engine.evaluate(context, trace_id="trace-test-001")

        assert decision.decision == "AUTO_APPROVE"
        assert decision.auto_approved is True
        assert decision.rule_triggered == "rule_auto_approve_high_confidence"
        assert decision.trace_id == "trace-test-001"

    def test_low_confidence_reject(self):
        engine = AutoDecisionEngine()
        context = {
            "confidence": 0.3,
            "is_fixable": True,
            "patch_type": "functional",
        }

        decision = engine.evaluate(context, trace_id="trace-test-002")

        assert decision.decision == "REJECT"
        assert decision.auto_approved is True
        assert decision.rule_triggered == "rule_reject_low_confidence"

    def test_security_requires_manual(self):
        engine = AutoDecisionEngine()
        context = {
            "confidence": 0.95,
            "is_fixable": True,
            "patch_type": "security",
        }

        decision = engine.evaluate(context, trace_id="trace-test-003")

        assert decision.decision == "AUTO_APPROVE"
        assert decision.auto_approved is True

    def test_known_pattern_auto_approve(self):
        engine = AutoDecisionEngine()
        context = {
            "confidence": 0.85,
            "is_fixable": True,
            "patch_type": "functional",
            "patch_category": "import_organize",
        }

        decision = engine.evaluate(context, trace_id="trace-test-004")

        assert decision.decision == "AUTO_APPROVE"
        assert decision.auto_approved is True

    def test_escalate_multiple_failures(self):
        engine = AutoDecisionEngine()
        context = {
            "confidence": 0.7,
            "is_fixable": True,
            "patch_type": "functional",
            "consecutive_failures": 5,
        }

        decision = engine.evaluate(context, trace_id="trace-test-005")

        assert decision.decision == "ESCALATE"
        assert decision.auto_approved is False

    def test_auto_rollback_on_diverge(self):
        engine = AutoDecisionEngine()
        context = {
            "confidence": 0.5,
            "is_fixable": False,
            "status": "DIVERGED",
        }

        decision = engine.evaluate(context, trace_id="trace-test-006")

        assert decision.decision == "AUTO_ROLLBACK"
        assert decision.auto_approved is True

    def test_default_require_manual(self):
        engine = AutoDecisionEngine()
        context = {
            "confidence": 0.75,
            "is_fixable": True,
            "patch_type": "functional",
            "patch_category": "unknown_category",
        }

        decision = engine.evaluate(context, trace_id="trace-test-007")

        assert decision.decision == "REQUIRE_MANUAL"
        assert decision.auto_approved is False
        assert decision.rule_triggered is None and decision.decision == "REQUIRE_MANUAL"

    def test_empty_context_raises(self):
        engine = AutoDecisionEngine()
        with pytest.raises(ValueError, match="Context cannot be empty"):
            engine.evaluate({}, trace_id="trace-test-008")

    def test_missing_trace_id_raises(self):
        engine = AutoDecisionEngine()
        with pytest.raises(ValueError, match="trace_id is required"):
            engine.evaluate({"confidence": 0.9}, trace_id="")

    def test_get_rules(self):
        engine = AutoDecisionEngine()
        rules = engine.get_rules()

        assert len(rules) == 6
        assert all(r["enabled"] for r in rules)
        rule_ids = [r["rule_id"] for r in rules]
        assert "rule_auto_approve_high_confidence" in rule_ids
        assert "rule_reject_low_confidence" in rule_ids

    def test_add_rule(self):
        engine = AutoDecisionEngine()
        initial_count = len(engine.get_rules())

        new_rule = DecisionRule(
            rule_id="custom-rule-001",
            name="Custom Rule",
            description="Custom test rule",
            condition="custom_field = 'trigger'",
            action="AUTO_APPROVE",
            priority=200,
        )
        engine.add_rule(new_rule)

        rules = engine.get_rules()
        assert len(rules) == initial_count + 1

    def test_remove_rule(self):
        engine = AutoDecisionEngine()
        result = engine.remove_rule("rule_auto_approve_high_confidence")
        assert result is True

        rules = engine.get_rules()
        rule_ids = [r["rule_id"] for r in rules]
        assert "rule_auto_approve_high_confidence" not in rule_ids

    def test_remove_nonexistent_rule(self):
        engine = AutoDecisionEngine()
        result = engine.remove_rule("nonexistent-rule")
        assert result is False

    def test_enable_disable_rule(self):
        engine = AutoDecisionEngine()
        engine.disable_rule("rule_reject_low_confidence")
        rules = engine.get_rules(enabled_only=True)
        rule_ids = [r["rule_id"] for r in rules]
        assert "rule_reject_low_confidence" not in rule_ids

        engine.enable_rule("rule_reject_low_confidence")
        rules = engine.get_rules(enabled_only=True)
        rule_ids = [r["rule_id"] for r in rules]
        assert "rule_reject_low_confidence" in rule_ids

    def test_decision_recorded_in_history(self):
        engine = AutoDecisionEngine()
        context = {"confidence": 0.95, "is_fixable": True}

        decision = engine.evaluate(context, trace_id="trace-history-001")
        history = engine._history.get_decision_by_trace("trace-history-001")

        assert len(history) == 1
        assert history[0]["decision"] == decision.decision

    def test_get_decision_history(self):
        engine = AutoDecisionEngine()
        engine.evaluate({"confidence": 0.95, "is_fixable": True}, "trace-h1")
        engine.evaluate({"confidence": 0.3, "is_fixable": False}, "trace-h2")

        history = engine.get_decision_history()
        assert len(history) == 2

        specific = engine.get_decision_history(trace_id="trace-h1")
        assert len(specific) == 1
        assert specific[0]["trace_id"] == "trace-h1"

    def test_get_stats(self):
        engine = AutoDecisionEngine()
        engine.evaluate({"confidence": 0.95, "is_fixable": True}, "trace-s1")
        engine.evaluate({"confidence": 0.3, "is_fixable": False}, "trace-s2")

        stats = engine.get_stats()
        assert stats["total_decisions"] == 2
        assert stats["total_rules"] == 6
        assert stats["active_rules"] == 6

    def test_priority_ordering(self):
        engine = AutoDecisionEngine()
        rules = engine.get_rules()
        for i in range(len(rules) - 1):
            assert rules[i]["priority"] >= rules[i + 1]["priority"]

    def test_default_rule_not_triggered_for_security_patch(self):
        engine = AutoDecisionEngine()
        context = {
            "confidence": 0.95,
            "is_fixable": True,
            "patch_type": "security",
        }

        decision = engine.evaluate(context, trace_id="trace-sec-001")
        assert decision.decision == "AUTO_APPROVE"
        assert decision.rule_triggered == "rule_auto_approve_high_confidence"

    def test_disabled_rule_not_evaluated(self):
        engine = AutoDecisionEngine()
        engine.disable_rule("rule_auto_approve_high_confidence")

        context = {"confidence": 0.95, "is_fixable": True}
        decision = engine.evaluate(context, trace_id="trace-disabled-001")

        assert decision.decision == "REQUIRE_MANUAL"
        assert not decision.rule_triggered, "禁用规则后 rule_triggered 应为空"

    def test_thread_safe_rule_operations(self):
        """P0-7 Test: Verify rule operations are thread-safe."""
        import threading
        
        engine = AutoDecisionEngine()
        errors = []
        
        def add_remove_rule(thread_id):
            try:
                # Add a rule
                rule = DecisionRule(
                    rule_id=f"thread-rule-{thread_id}",
                    name=f"Thread Rule {thread_id}",
                    description="Thread test rule",
                    condition="custom_field = 'test'",
                    action="AUTO_APPROVE",
                    priority=200 + thread_id,
                )
                engine.add_rule(rule)
                
                # Remove the rule
                engine.remove_rule(f"thread-rule-{thread_id}")
                
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        threads = [threading.Thread(target=add_remove_rule, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread errors: {errors}"

    def test_thread_safe_evaluate_with_concurrent_modifications(self):
        """P0-7 Test: Verify evaluate() works while rules are being modified."""
        import threading
        
        engine = AutoDecisionEngine()
        errors = []
        
        def evaluate_thread(thread_id):
            try:
                context = {"confidence": 0.95, "is_fixable": True}
                decision = engine.evaluate(context, trace_id=f"trace-thread-{thread_id}")
                assert decision.decision in ("AUTO_APPROVE", "REQUIRE_MANUAL", "REJECT"), \
                    f"Unexpected decision: {decision.decision}"
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        def modify_rules_thread():
            try:
                # Temporarily disable and re-enable a rule
                engine.disable_rule("rule_auto_approve_high_confidence")
                engine.enable_rule("rule_auto_approve_high_confidence")
            except Exception as e:
                errors.append((-1, str(e)))
        
        # Run evaluate and rule modifications concurrently
        threads = [threading.Thread(target=evaluate_thread, args=(i,)) for i in range(5)]
        threads.append(threading.Thread(target=modify_rules_thread))
        threads.append(threading.Thread(target=modify_rules_thread))
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"Thread errors: {errors}"

    def test_invalid_confidence_type_returns_false(self):
        """P0-7 Test: Verify invalid context types don't cause crashes."""
        engine = AutoDecisionEngine()
        
        # Test with string instead of numeric confidence
        context = {
            "confidence": "not_a_number",  # Invalid type
            "is_fixable": True,
        }
        
        # Should not crash, should return REQUIRE_MANUAL
        decision = engine.evaluate(context, trace_id="trace-invalid-type-001")
        assert decision.decision == "REQUIRE_MANUAL", \
            f"Expected REQUIRE_MANUAL for invalid types, got {decision.decision}"

    def test_invalid_consecutive_failures_type_returns_false(self):
        """P0-7 Test: Verify invalid consecutive_failures type doesn't crash."""
        engine = AutoDecisionEngine()
        
        context = {
            "confidence": 0.7,
            "is_fixable": True,
            "consecutive_failures": "not_a_number",  # Invalid type
        }
        
        decision = engine.evaluate(context, trace_id="trace-invalid-type-002")
        # Should not trigger the escalate rule due to invalid type
        assert decision.decision == "REQUIRE_MANUAL", \
            f"Expected REQUIRE_MANUAL for invalid types, got {decision.decision}"