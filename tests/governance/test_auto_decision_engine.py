import time
import pytest

from src.governance.auto_decision_engine import (
    AutoDecisionEngine,
    DecisionRule,
    GovernanceDecision,
)


@pytest.fixture(autouse=True)
def clean_engine():
    engine = AutoDecisionEngine()
    engine._history.clear()
    yield
    engine._history.clear()


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

        # Cleanup: remove the added rule to avoid state pollution
        engine.remove_rule("custom-rule-001")

    def test_remove_rule(self):
        engine = AutoDecisionEngine()
        temp_rule = DecisionRule(
            rule_id="temp_rule_for_removal_test",
            name="Temp Rule",
            description="Temporary rule for testing removal",
            condition="confidence >= 0.9",
            action="AUTO_APPROVE",
            priority=5,
        )
        engine.add_rule(temp_rule)
        result = engine.remove_rule("temp_rule_for_removal_test")
        assert result is True

        rules = engine.get_rules()
        rule_ids = [r["rule_id"] for r in rules]
        assert "temp_rule_for_removal_test" not in rule_ids

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
        history = engine._history.get_decisions_by_trace("trace-history-001")

        assert len(history) == 1
        assert history[0].decision == decision.decision

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

    # === Mutation killers for 6 surviving mutations (2026-07-31 audit) ===

    def test_is_fixable_default_false_kill_survivor_L181(self):
        """Kill L181 replace_boolean: context.get("is_fixable", False) default must stay False.
        
        If default is mutated to True, high-confidence patches WITHOUT is_fixable
        would auto-approve instead of requiring manual review.
        """
        engine = AutoDecisionEngine()
        # No is_fixable key provided — should default to False
        context = {
            "confidence": 0.95,
            # is_fixable intentionally omitted — default should be False
            "patch_type": "functional",
        }
        decision = engine.evaluate(context, trace_id="kill-L181-001")
        # With is_fixable=False (default), auto_approve rule should NOT trigger
        assert decision.decision == "REQUIRE_MANUAL", (
            f"KILL-L181: Without is_fixable, default must be False. "
            f"Mutation to True would cause auto-approve. Got {decision.decision}"
        )
        assert decision.rule_triggered is None, (
            "KILL-L181: No rule should trigger when is_fixable defaults to False"
        )

    def test_evaluate_rule_exception_returns_false_kill_survivor_L212(self):
        """Kill L212 replace_return_value: except block must return False, not True.
        
        If return value is mutated to True, invalid rule conditions would pass
        instead of being rejected.
        """
        engine = AutoDecisionEngine()
        # Create a rule whose condition string won't match any known pattern,
        # but context contains data that causes TypeError during evaluation
        rule = DecisionRule(
            rule_id="kill-L212-rule",
            name="Kill L212",
            description="Test exception handling",
            condition="confidence >= 0.9 AND is_fixable = True",
            action="AUTO_APPROVE",
            priority=200,
            confidence_threshold=0.9,
        )
        # Pass context with confidence as a list (causes TypeError on >= comparison)
        context = {"confidence": [0.95], "is_fixable": True}
        result = engine._evaluate_rule(rule, context)
        assert result is False, (
            f"KILL-L212: Exception handler must return False. "
            f"Mutation to True would bypass error handling. Got {result}"
        )

    def test_handle_reject_auto_true_kill_survivor_L223(self):
        """Kill L223 replace_boolean: _handle_reject must return auto=True.
        
        If auto is mutated to False, reject decisions lose their auto flag.
        """
        engine = AutoDecisionEngine()
        decision = GovernanceDecision(
            decision_id="test-kill-L223",
            trace_id="trace-kill-L223",
            decision_type="auto_decision",
            decision="REJECT",
            reason="Test reject",
            confidence=0.3,
            auto_approved=True,
            rule_triggered="rule_reject_low_confidence",
        )
        result = engine._handle_reject(decision)
        assert result["auto"] is True, (
            f"KILL-L223: _handle_reject must return auto=True. "
            f"Mutation to False would break auto-approve flag. Got {result}"
        )
        assert result["status"] == "rejected", (
            f"KILL-L223: status must be 'rejected'. Got {result['status']}"
        )

    def test_get_rules_default_enabled_only_kill_survivor_L237(self):
        """Kill L237 replace_boolean: get_rules() default enabled_only must stay True.
        
        If default is mutated to False, disabled rules would leak into the
        default results, causing unintended rule evaluation.
        """
        engine = AutoDecisionEngine()
        # First disable a rule
        engine.disable_rule("rule_reject_low_confidence")
        # Call get_rules() with default arg (should be enabled_only=True)
        rules = engine.get_rules()
        rule_ids = [r["rule_id"] for r in rules]
        assert "rule_reject_low_confidence" not in rule_ids, (
            f"KILL-L237: get_rules() default must filter disabled rules. "
            f"Mutation to False would include disabled rules. Got {rule_ids}"
        )
        assert len(rules) == 5, (
            f"KILL-L237: Expected 5 enabled rules after disabling 1. Got {len(rules)}"
        )
        # Re-enable for cleanup
        engine.enable_rule("rule_reject_low_confidence")

    def test_enable_rule_returns_true_kill_survivor_L276(self):
        """Kill L276 replace_return_value: enable_rule must return True on success.
        
        If return value is mutated to False, callers would think enable failed
        when it actually succeeded.
        """
        engine = AutoDecisionEngine()
        # First disable the rule
        engine.disable_rule("rule_reject_low_confidence")
        # Then re-enable and assert return value
        result = engine.enable_rule("rule_reject_low_confidence")
        assert result is True, (
            f"KILL-L276: enable_rule must return True when rule exists. "
            f"Mutation to False would break caller logic. Got {result}"
        )
        # Verify rule is actually enabled
        rules = engine.get_rules()
        rule_ids = [r["rule_id"] for r in rules]
        assert "rule_reject_low_confidence" in rule_ids, (
            "KILL-L276: Rule should be enabled after enable_rule returns True"
        )

    def test_disable_rule_returns_true_kill_survivor_L285(self):
        """Kill L285 replace_return_value: disable_rule must return True on success.

        If return value is mutated to False, callers would think disable failed
        when it actually succeeded.
        """
        engine = AutoDecisionEngine()
        result = engine.disable_rule("rule_reject_low_confidence")
        assert result is True, (
            f"KILL-L285: disable_rule must return True when rule exists. "
            f"Mutation to False would break caller logic. Got {result}"
        )
        # Verify rule is actually disabled
        rules = engine.get_rules()
        rule_ids = [r["rule_id"] for r in rules]
        assert "rule_reject_low_confidence" not in rule_ids, (
            "KILL-L285: Rule should be disabled after disable_rule returns True"
        )
        # Re-enable for cleanup
        engine.enable_rule("rule_reject_low_confidence")


class TestHandlerDispatch:
    """P2-5 验证: evaluate() 必须实际调用已注册的 _decision_handlers。

    原实现 _register_default_handlers 注册了 5 个处理器但 evaluate 从未调用,
    _handle_auto_approve / _handle_reject 等是死代码 —— 自动决策只"记账"无动作。
    本测试类覆盖正向/负向/边界/异常: 处理器被调用、结果写入 metadata、
    处理器异常不污染决策、未注册动作安全降级。
    """

    @pytest.fixture(autouse=True)
    def restore_handlers_and_rules(self):
        """AutoDecisionEngine 是单例, 处理器/规则的突变会跨测试泄漏, 必须恢复。"""
        engine = AutoDecisionEngine()
        saved_handlers = dict(engine._decision_handlers)
        saved_rules = list(engine._rules)
        yield
        engine._decision_handlers.clear()
        engine._decision_handlers.update(saved_handlers)
        engine._rules.clear()
        engine._rules.extend(saved_rules)

    def test_evaluate_dispatches_auto_approve_handler(self):
        """正向: 高置信度触发 AUTO_APPROVE, 处理器结果应写入 metadata。"""
        engine = AutoDecisionEngine()
        context = {"confidence": 0.95, "is_fixable": True, "patch_type": "functional"}
        decision = engine.evaluate(context, trace_id="trace-dispatch-approve")
        assert decision.decision == "AUTO_APPROVE"
        handler_result = decision.metadata.get("handler_result")
        assert handler_result is not None, "AUTO_APPROVE 处理器未被调用"
        assert handler_result["status"] == "approved"
        assert handler_result["auto"] is True

    def test_evaluate_dispatches_reject_handler(self):
        """正向: 低置信度触发 REJECT, 处理器结果应为 rejected。"""
        engine = AutoDecisionEngine()
        context = {"confidence": 0.3, "is_fixable": True}
        decision = engine.evaluate(context, trace_id="trace-dispatch-reject")
        assert decision.decision == "REJECT"
        assert decision.metadata["handler_result"]["status"] == "rejected"

    def test_evaluate_dispatches_default_manual_handler(self):
        """正向: 无规则命中走默认 REQUIRE_MANUAL, 处理器仍应被调用。"""
        engine = AutoDecisionEngine()
        context = {"confidence": 0.75, "is_fixable": True, "patch_category": "unknown"}
        decision = engine.evaluate(context, trace_id="trace-dispatch-manual")
        assert decision.decision == "REQUIRE_MANUAL"
        assert decision.metadata["handler_result"]["status"] == "pending_manual"

    def test_handler_called_once_with_same_decision_object(self):
        """边界: 处理器应被调用恰好一次, 且接收的 decision 与返回值同一对象。"""
        engine = AutoDecisionEngine()
        calls = []
        original = engine._decision_handlers["AUTO_APPROVE"]

        def spy(decision):
            calls.append(decision)
            return original(decision)

        engine._decision_handlers["AUTO_APPROVE"] = spy
        context = {"confidence": 0.95, "is_fixable": True}
        decision = engine.evaluate(context, trace_id="trace-spy-001")
        assert len(calls) == 1, f"处理器应被调用一次, 实际 {len(calls)} 次"
        assert calls[0] is decision, "处理器接收的 decision 应与返回值同一对象"

    def test_handler_exception_does_not_crash_evaluate(self):
        """异常: 处理器抛错时 evaluate 不应崩溃, 错误须以结构化方式暴露,
        不得被裸 except 静默吞没。"""
        engine = AutoDecisionEngine()

        def boom(decision):
            raise RuntimeError("handler exploded")

        engine._decision_handlers["AUTO_APPROVE"] = boom
        context = {"confidence": 0.95, "is_fixable": True}
        decision = engine.evaluate(context, trace_id="trace-exc-001")
        # 决策仍应正常返回 (决策已由规则确定, 不受处理器副作用影响)
        assert decision.decision == "AUTO_APPROVE"
        # 错误必须暴露在 metadata, 证明未被吞没
        assert "handler_error" in decision.metadata, "处理器异常被静默吞没"
        assert "RuntimeError" in decision.metadata["handler_error"]
        assert "handler exploded" in decision.metadata["handler_error"]

    def test_no_handler_for_action_degrades_safely(self):
        """负向: 动作无注册处理器时应安全降级 (handler_result=None), 不得抛错。"""
        engine = AutoDecisionEngine()
        custom = DecisionRule(
            rule_id="custom-no-handler-action",
            name="No Handler Action",
            description="动作无对应处理器, 验证安全降级",
            condition="confidence >= 0.9 AND is_fixable = True",
            action="WEIRD_ACTION",
            priority=200,
        )
        engine.add_rule(custom)
        engine._decision_handlers.pop("WEIRD_ACTION", None)
        context = {"confidence": 0.95, "is_fixable": True}
        decision = engine.evaluate(context, trace_id="trace-no-handler-001")
        assert decision.decision == "WEIRD_ACTION"
        assert decision.metadata.get("handler_result") is None, (
            "未注册处理器时 handler_result 应为 None"
        )
        # 确保未误写 handler_error (降级不是异常)
        assert "handler_error" not in decision.metadata