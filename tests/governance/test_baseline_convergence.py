import copy

import pytest

from src.governance.baseline import BaselineRecord, GoldenBaselineManager


@pytest.fixture(scope="module")
def baseline_manager():
    return GoldenBaselineManager()


@pytest.fixture(scope="module")
def security_normal_data():
    return {
        "status": "success",
        "record_id": "golden_sec_normal_001",
        "data": {
            "text": "安全评估完成",
            "score": 0.95,
            "confidence_level": "high",
            "data": {
                "security_tests": {
                    "injection": {"score": 1.0, "detected": False, "risk_level": "low"},
                    "jailbreak": {"score": 1.0, "detected": False, "risk_level": "low"},
                    "data_leak": {"score": 1.0, "detected": False, "risk_level": "low"},
                    "tool_abuse": {"score": 1.0, "detected": False, "risk_level": "low"},
                },
                "overall_score": 0.95,
                "risk_level": "low",
            },
            "is_valid": True,
        },
    }


@pytest.fixture(scope="module")
def security_injection_data():
    return {
        "status": "success",
        "record_id": "golden_sec_injection_001",
        "data": {
            "text": "检测到安全威胁",
            "score": 0.15,
            "confidence_level": "high",
            "data": {
                "security_tests": {
                    "injection": {"score": 0.1, "detected": True, "risk_level": "high"},
                    "jailbreak": {"score": 0.05, "detected": True, "risk_level": "high"},
                    "data_leak": {"score": 0.15, "detected": True, "risk_level": "high"},
                    "tool_abuse": {"score": 0.12, "detected": True, "risk_level": "high"},
                },
                "overall_score": 0.12,
                "risk_level": "high",
            },
            "is_valid": True,
        },
    }


@pytest.fixture(scope="module")
def qa_high_quality_data():
    return {
        "status": "success",
        "record_id": "golden_qa_high_quality_001",
        "data": {
            "text": "QA评估完成",
            "score": 0.88,
            "confidence_level": "high",
            "data": {
                "question": "什么是人工智能？",
                "expected_output": "人工智能是计算机科学的分支...",
                "raw_output": "人工智能是计算机科学的分支...",
                "evaluator": "qa",
            },
            "is_valid": True,
        },
    }


class TestGoldenBaselineManagerInitialization:
    def test_manager_is_singleton(self):
        manager1 = GoldenBaselineManager()
        manager2 = GoldenBaselineManager()
        assert manager1 is manager2

    def test_default_baselines_loaded(self, baseline_manager):
        baseline_ids = baseline_manager.get_all_baseline_ids()
        assert len(baseline_ids) >= 3
        assert "golden_sec_normal_001" in baseline_ids
        assert "golden_sec_injection_001" in baseline_ids
        assert "golden_qa_high_quality_001" in baseline_ids


class TestGoldenBaselineManagerGetters:
    def test_get_baseline_returns_record(self, baseline_manager):
        record = baseline_manager.get_baseline("golden_sec_normal_001")
        assert record is not None
        assert isinstance(record, BaselineRecord)
        assert record.record_id == "golden_sec_normal_001"
        assert record.baseline_type == "security"

    def test_get_baseline_returns_none_for_invalid_id(self, baseline_manager):
        record = baseline_manager.get_baseline("nonexistent_id")
        assert record is None

    def test_get_baselines_by_type(self, baseline_manager):
        security_baselines = baseline_manager.get_baselines_by_type("security")
        qa_baselines = baseline_manager.get_baselines_by_type("qa")
        assert len(security_baselines) >= 2
        assert len(qa_baselines) >= 1
        for baseline in security_baselines:
            assert baseline.baseline_type == "security"


class TestValidateAgainstBaselineSecurityNormal:
    def test_security_normal_valid_output(self, baseline_manager, security_normal_data):
        result = baseline_manager.validate_against_baseline(
            "golden_sec_normal_001", security_normal_data
        )
        assert result["passed"] is True, f"Validation failed: {result['errors']}"
        assert len(result["errors"]) == 0
        assert result["baseline_id"] == "golden_sec_normal_001"

    def test_security_normal_score_below_minimum(self, baseline_manager, security_normal_data):
        data = copy.deepcopy(security_normal_data)
        data["data"]["score"] = 0.85
        data["data"]["data"]["overall_score"] = 0.85
        result = baseline_manager.validate_against_baseline(
            "golden_sec_normal_001", data
        )
        assert result["passed"] is False, "Should fail when score below minimum"
        assert any("below minimum" in error for error in result["errors"])

    def test_security_normal_risk_level_incorrect(self, baseline_manager, security_normal_data):
        data = copy.deepcopy(security_normal_data)
        data["data"]["data"]["risk_level"] = "medium"
        result = baseline_manager.validate_against_baseline(
            "golden_sec_normal_001", data
        )
        assert result["passed"] is False, "Should fail when risk level is incorrect"
        assert any("Risk level" in error for error in result["errors"])

    def test_security_normal_detected_true_when_should_be_false(self, baseline_manager, security_normal_data):
        data = copy.deepcopy(security_normal_data)
        data["data"]["data"]["security_tests"]["injection"]["detected"] = True
        result = baseline_manager.validate_against_baseline(
            "golden_sec_normal_001", data
        )
        assert result["passed"] is False, "Should fail when detected is True but expected False"
        assert any("Detected" in error for error in result["errors"])


class TestValidateAgainstBaselineSecurityInjection:
    def test_security_injection_valid_output(self, baseline_manager, security_injection_data):
        result = baseline_manager.validate_against_baseline(
            "golden_sec_injection_001", security_injection_data
        )
        assert result["passed"] is True, f"Validation failed: {result['errors']}"
        assert len(result["errors"]) == 0

    def test_security_injection_score_above_maximum(self, baseline_manager, security_injection_data):
        data = copy.deepcopy(security_injection_data)
        data["data"]["score"] = 0.45
        data["data"]["data"]["overall_score"] = 0.45
        result = baseline_manager.validate_against_baseline(
            "golden_sec_injection_001", data
        )
        assert result["passed"] is False, "Should fail when score exceeds maximum"
        assert any("exceeds maximum" in error for error in result["errors"])

    def test_security_injection_detected_false_when_should_be_true(self, baseline_manager, security_injection_data):
        data = copy.deepcopy(security_injection_data)
        data["data"]["data"]["security_tests"]["injection"]["detected"] = False
        result = baseline_manager.validate_against_baseline(
            "golden_sec_injection_001", data
        )
        assert result["passed"] is False, "Should fail when detected is False but expected True"
        assert any("Detected" in error for error in result["errors"])


class TestValidateAgainstBaselineQAHighQuality:
    def test_qa_high_quality_valid_output(self, baseline_manager, qa_high_quality_data):
        result = baseline_manager.validate_against_baseline(
            "golden_qa_high_quality_001", qa_high_quality_data
        )
        assert result["passed"] is True, f"Validation failed: {result['errors']}"
        assert len(result["errors"]) == 0

    def test_qa_high_quality_score_below_minimum(self, baseline_manager, qa_high_quality_data):
        data = copy.deepcopy(qa_high_quality_data)
        data["data"]["score"] = 0.75
        result = baseline_manager.validate_against_baseline(
            "golden_qa_high_quality_001", data
        )
        assert result["passed"] is False, "Should fail when score below minimum"
        assert any("below minimum" in error for error in result["errors"])

    def test_qa_high_quality_confidence_level_invalid(self, baseline_manager, qa_high_quality_data):
        data = copy.deepcopy(qa_high_quality_data)
        data["data"]["confidence_level"] = "invalid_level"
        result = baseline_manager.validate_against_baseline(
            "golden_qa_high_quality_001", data
        )
        assert result["passed"] is False, "Should fail when confidence level is invalid"
        assert any("Confidence level" in error for error in result["errors"])


class TestValidateAgainstBaselineNotFound:
    def test_baseline_not_found_returns_failed(self, baseline_manager):
        result = baseline_manager.validate_against_baseline("nonexistent_id", {})
        assert result["passed"] is False, "Should fail when baseline not found"
        assert "Baseline not found" in result["errors"]


class TestCalculateConvergenceScore:
    def test_convergence_score_passed_returns_1(self, baseline_manager, security_normal_data):
        score = baseline_manager.calculate_convergence_score(
            security_normal_data, "golden_sec_normal_001"
        )
        assert score == 1.0, "Convergence score should be 1.0 when validation passes"

    def test_convergence_score_single_error_returns_08(self, baseline_manager, security_normal_data):
        data = copy.deepcopy(security_normal_data)
        data["data"]["score"] = 0.85
        score = baseline_manager.calculate_convergence_score(
            data, "golden_sec_normal_001"
        )
        assert score == 0.8, f"Convergence score should be 0.8 with 1 error, got {score}"

    def test_convergence_score_multiple_errors_decreases_score(self, baseline_manager, security_normal_data):
        data = copy.deepcopy(security_normal_data)
        data["data"]["score"] = 0.85
        data["data"]["data"]["risk_level"] = "medium"
        score = baseline_manager.calculate_convergence_score(
            data, "golden_sec_normal_001"
        )
        assert score == 0.6, f"Convergence score should be 0.6 with 2 errors, got {score}"

    def test_convergence_score_baseline_not_found_returns_08(self, baseline_manager):
        score = baseline_manager.calculate_convergence_score({}, "nonexistent_id")
        assert score == 0.8, f"Convergence score should be 0.8 when baseline not found (1 error), got {score}"

    def test_convergence_score_never_negative(self, baseline_manager, security_normal_data):
        data = copy.deepcopy(security_normal_data)
        data["data"]["score"] = 0.1
        data["data"]["data"]["risk_level"] = "high"
        data["data"]["data"]["security_tests"]["injection"]["detected"] = True
        score = baseline_manager.calculate_convergence_score(
            data, "golden_sec_normal_001"
        )
        assert score >= 0.0, "Convergence score should never be negative"


class TestBaselineRecord:
    def test_baseline_record_creation(self):
        record = BaselineRecord(
            record_id="test_001",
            baseline_type="security",
            data={"key": "value"},
        )
        assert record.record_id == "test_001"
        assert record.baseline_type == "security"
        assert record.data == {"key": "value"}
        assert record.created_at is not None

    def test_baseline_record_to_dict(self):
        record = BaselineRecord(
            record_id="test_001",
            baseline_type="security",
            data={"key": "value"},
        )
        record_dict = record.to_dict()
        assert record_dict["record_id"] == "test_001"
        assert record_dict["baseline_type"] == "security"
        assert record_dict["data"] == {"key": "value"}
        assert "created_at" in record_dict


class TestAddBaseline:
    def test_add_baseline_stores_record(self, baseline_manager):
        new_record = BaselineRecord(
            record_id="test_dynamic_001",
            baseline_type="test",
            data={"test": "data"},
        )
        baseline_manager.add_baseline(new_record)
        retrieved = baseline_manager.get_baseline("test_dynamic_001")
        assert retrieved is not None
        assert retrieved.record_id == "test_dynamic_001"