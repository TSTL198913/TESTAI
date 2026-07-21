import pytest

from src.governance.baseline import BaselineRecord, GoldenBaselineManager


class TestGoldenBaselineManager:
    def test_singleton_instance(self):
        manager1 = GoldenBaselineManager()
        manager2 = GoldenBaselineManager()
        assert manager1 is manager2

    def test_get_all_baseline_ids(self):
        manager = GoldenBaselineManager()
        ids = manager.get_all_baseline_ids()
        assert len(ids) >= 3
        assert "golden_sec_normal_001" in ids
        assert "golden_sec_injection_001" in ids
        assert "golden_qa_high_quality_001" in ids

    def test_get_baseline(self):
        manager = GoldenBaselineManager()
        baseline = manager.get_baseline("golden_sec_normal_001")
        assert baseline is not None
        assert baseline.record_id == "golden_sec_normal_001"
        assert baseline.baseline_type == "security"

    def test_get_baselines_by_type(self):
        manager = GoldenBaselineManager()
        security_baselines = manager.get_baselines_by_type("security")
        qa_baselines = manager.get_baselines_by_type("qa")
        assert len(security_baselines) >= 2
        assert len(qa_baselines) >= 1

    def test_add_baseline(self):
        manager = GoldenBaselineManager()
        record = BaselineRecord(
            record_id="test_baseline_001",
            baseline_type="test",
            data={"name": "Test Baseline", "expected_score_min": 0.7},
        )
        manager.add_baseline(record)
        retrieved = manager.get_baseline("test_baseline_001")
        assert retrieved is not None
        assert retrieved.record_id == "test_baseline_001"

    def test_validate_against_baseline_passed(self):
        manager = GoldenBaselineManager()
        actual_data = {
            "status": "success",
            "data": {
                "score": 0.95,
                "confidence_level": "high",
                "data": {
                    "risk_level": "low",
                    "security_tests": {"injection": {"detected": False}},
                },
            },
        }
        result = manager.validate_against_baseline("golden_sec_normal_001", actual_data)
        assert result["passed"] is True
        assert len(result["errors"]) == 0

    def test_validate_against_baseline_score_below_min(self):
        manager = GoldenBaselineManager()
        actual_data = {
            "status": "success",
            "data": {
                "score": 0.85,
                "data": {
                    "risk_level": "low",
                    "security_tests": {"injection": {"detected": False}},
                },
            },
        }
        result = manager.validate_against_baseline("golden_sec_normal_001", actual_data)
        assert result["passed"] is False
        assert any("below minimum" in error for error in result["errors"])

    def test_validate_against_baseline_injection_detected(self):
        manager = GoldenBaselineManager()
        actual_data = {
            "status": "success",
            "data": {
                "score": 0.25,
                "data": {
                    "risk_level": "high",
                    "security_tests": {"injection": {"detected": True}},
                },
            },
        }
        result = manager.validate_against_baseline(
            "golden_sec_injection_001", actual_data
        )
        assert result["passed"] is True

    def test_validate_against_baseline_not_found(self):
        manager = GoldenBaselineManager()
        result = manager.validate_against_baseline("non_existent_baseline", {})
        assert result["passed"] is False
        assert "Baseline not found" in result["errors"]

    def test_calculate_convergence_score_passed(self):
        manager = GoldenBaselineManager()
        actual_data = {
            "status": "success",
            "data": {
                "score": 0.95,
                "data": {
                    "risk_level": "low",
                    "security_tests": {"injection": {"detected": False}},
                },
            },
        }
        score = manager.calculate_convergence_score(
            actual_data, "golden_sec_normal_001"
        )
        assert score == 1.0

    def test_calculate_convergence_score_partial(self):
        manager = GoldenBaselineManager()
        actual_data = {
            "status": "success",
            "data": {
                "score": 0.85,
                "data": {
                    "risk_level": "medium",
                    "security_tests": {"injection": {"detected": False}},
                },
            },
        }
        score = manager.calculate_convergence_score(
            actual_data, "golden_sec_normal_001"
        )
        assert score == 0.6


class TestConvergenceLoop:
    def test_convergence_loop_simulation(self):
        manager = GoldenBaselineManager()
        iterations = 5
        scores = []

        for i in range(iterations):
            score = 0.6 + i * 0.1
            actual_data = {
                "status": "success",
                "data": {
                    "score": score,
                    "data": {
                        "risk_level": "low",
                        "security_tests": {"injection": {"detected": False}},
                    },
                },
            }
            convergence_score = manager.calculate_convergence_score(
                actual_data, "golden_sec_normal_001"
            )
            scores.append(convergence_score)

        assert scores[-1] >= 0.8
        assert all(scores[i] <= scores[i + 1] for i in range(len(scores) - 1))

    def test_convergence_stability_window(self):
        manager = GoldenBaselineManager()
        scores = []

        for i in range(8):
            score = 0.9 + (i % 3) * 0.02
            actual_data = {
                "status": "success",
                "data": {
                    "score": score,
                    "data": {
                        "risk_level": "low",
                        "security_tests": {"injection": {"detected": False}},
                    },
                },
            }
            convergence_score = manager.calculate_convergence_score(
                actual_data, "golden_sec_normal_001"
            )
            scores.append(convergence_score)

        stability_window = scores[-5:]
        max_diff = max(stability_window) - min(stability_window)
        assert max_diff <= 0.1

    def test_convergence_with_actual_tests(self):
        manager = GoldenBaselineManager()
        actual_test_data = {
            "status": "success",
            "data": {
                "text": "安全评估完成",
                "score": 0.95,
                "evaluation_status": "success",
                "confidence": 0.88,
                "confidence_level": "high",
                "data": {
                    "security_tests": {
                        "injection": {
                            "score": 1.0,
                            "detected": False,
                            "risk_level": "low",
                        },
                        "jailbreak": {
                            "score": 1.0,
                            "detected": False,
                            "risk_level": "low",
                        },
                        "data_leak": {
                            "score": 1.0,
                            "detected": False,
                            "risk_level": "low",
                        },
                        "tool_abuse": {
                            "score": 1.0,
                            "detected": False,
                            "risk_level": "low",
                        },
                    },
                    "overall_score": 0.95,
                    "risk_level": "low",
                    "execution_time_ms": 1200,
                    "trace_id": "abc123",
                },
            },
        }
        result = manager.validate_against_baseline(
            "golden_sec_normal_001", actual_test_data
        )
        assert result["passed"] is True
        score = manager.calculate_convergence_score(
            actual_test_data, "golden_sec_normal_001"
        )
        assert score == 1.0
