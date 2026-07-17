import pytest
import os
import copy
from tests.utils.validator import EvaluationValidator, ValidationResult


@pytest.fixture(scope="module")
def validator():
    return EvaluationValidator()


@pytest.fixture(scope="module")
def security_normal_base():
    return {
        "status": "success",
        "code": None,
        "message": None,
        "record_id": "golden-sec-normal-001",
        "evaluation_status": "SUCCESS",
        "latency_ms": 1500,
        "data": {
            "text": "安全评估完成",
            "score": 0.95,
            "evaluation_status": "success",
            "confidence": 0.88,
            "confidence_level": "high",
            "error": None,
            "metadata": {},
            "data": {
                "security_tests": {
                    "injection": {"score": 1.0, "detected": False, "risk_level": "low"},
                    "jailbreak": {"score": 1.0, "detected": False, "risk_level": "low"},
                    "data_leak": {"score": 1.0, "detected": False, "risk_level": "low"},
                    "tool_abuse": {"score": 1.0, "detected": False, "risk_level": "low"}
                },
                "overall_score": 0.95,
                "risk_level": "low",
                "execution_time_ms": 1200,
                "trace_id": "abc123"
            },
            "level": None,
            "details": None,
            "status_code": None,
            "is_valid": True
        },
        "routing": None,
        "persist": True,
        "persist_error": None
    }


@pytest.fixture(scope="module")
def security_injection_base():
    return {
        "status": "success",
        "code": None,
        "message": None,
        "record_id": "golden-sec-injection-001",
        "evaluation_status": "SUCCESS",
        "latency_ms": 2000,
        "data": {
            "text": "检测到安全威胁",
            "score": 0.15,
            "evaluation_status": "success",
            "confidence": 0.90,
            "confidence_level": "high",
            "error": None,
            "metadata": {},
            "data": {
                "security_tests": {
                    "injection": {"score": 0.1, "detected": True, "risk_level": "high"},
                    "jailbreak": {"score": 0.05, "detected": True, "risk_level": "high"},
                    "data_leak": {"score": 0.15, "detected": True, "risk_level": "high"},
                    "tool_abuse": {"score": 0.12, "detected": True, "risk_level": "high"}
                },
                "overall_score": 0.12,
                "risk_level": "high",
                "detected_items": ["injection", "jailbreak"],
                "execution_time_ms": 1800,
                "trace_id": "ghi789"
            },
            "level": "poor",
            "details": None,
            "status_code": None,
            "is_valid": True
        },
        "routing": None,
        "persist": True,
        "persist_error": None
    }


@pytest.fixture(scope="module")
def qa_high_quality_base():
    return {
        "status": "success",
        "code": None,
        "message": None,
        "record_id": "golden-qa-high-quality-001",
        "evaluation_status": "SUCCESS",
        "latency_ms": 5000,
        "data": {
            "text": "QA评估完成",
            "score": 0.88,
            "evaluation_status": "success",
            "confidence": 0.82,
            "confidence_level": "high",
            "error": None,
            "metadata": {},
            "data": {
                "question": "什么是人工智能？",
                "expected_output": "人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，旨在研究、开发用于模拟、延伸和扩展人的智能的理论、方法、技术及应用系统。",
                "raw_output": "人工智能是计算机科学的分支...",
                "evaluator": "qa",
                "execution_time_ms": 4500,
                "trace_id": "def456"
            },
            "level": "excellent",
            "details": None,
            "status_code": None,
            "is_valid": True
        },
        "routing": {},
        "persist": True,
        "persist_error": None
    }


class TestGoldenBaselineLoading:
    def test_baseline_file_exists(self, validator):
        assert os.path.exists(validator.baseline_path)

    def test_baseline_version_parsing(self, validator):
        assert validator.baseline_data["golden_baseline_version"] == "1.0"

    def test_baseline_has_scenarios(self, validator):
        scenarios = validator.baseline_data.get("scenarios", [])
        assert len(scenarios) == 3

    def test_get_scenario_by_id(self, validator):
        scenario = validator.get_scenario("golden_sec_normal_001")
        assert scenario is not None
        assert scenario["name"] == "Security Evaluator - Normal Input"

    def test_get_scenarios_by_type(self, validator):
        security_scenarios = validator.get_scenarios_by_type("security")
        qa_scenarios = validator.get_scenarios_by_type("qa")
        assert len(security_scenarios) == 2
        assert len(qa_scenarios) == 1


class TestSecurityEvaluatorNormalScenario:
    def test_security_normal_valid_output(self, validator, security_normal_base):
        result = validator.validate(security_normal_base, "golden_sec_normal_001")
        assert result.passed, f"Validation failed: {result.errors}"

    def test_security_normal_score_below_minimum(self, validator, security_normal_base):
        data = copy.deepcopy(security_normal_base)
        data["data"]["score"] = 0.85
        data["data"]["data"]["overall_score"] = 0.85
        result = validator.validate(data, "golden_sec_normal_001")
        assert not result.passed
        assert any("score" in error and "below minimum" in error for error in result.errors)

    def test_security_normal_risk_level_incorrect(self, validator, security_normal_base):
        data = copy.deepcopy(security_normal_base)
        data["data"]["data"]["security_tests"]["injection"]["risk_level"] = "medium"
        result = validator.validate(data, "golden_sec_normal_001")
        assert not result.passed
        assert any("injection" in error and "risk_level" in error for error in result.errors)


class TestQAEvaluatorHighQualityScenario:
    def test_qa_high_quality_valid_output(self, validator, qa_high_quality_base):
        result = validator.validate(qa_high_quality_base, "golden_qa_high_quality_001")
        assert result.passed, f"Validation failed: {result.errors}"

    def test_qa_high_quality_confidence_level_one_of(self, validator, qa_high_quality_base):
        data = copy.deepcopy(qa_high_quality_base)
        data["data"]["confidence_level"] = "medium"
        data["data"]["level"] = "good"
        result = validator.validate(data, "golden_qa_high_quality_001")
        assert result.passed, f"Validation failed: {result.errors}"

    def test_qa_high_quality_confidence_level_invalid(self, validator, qa_high_quality_base):
        data = copy.deepcopy(qa_high_quality_base)
        data["data"]["confidence_level"] = "invalid_level"
        result = validator.validate(data, "golden_qa_high_quality_001")
        assert not result.passed
        assert any("confidence_level" in error and "one of" in error for error in result.errors)


class TestSecurityEvaluatorInjectionScenario:
    def test_security_injection_valid_output(self, validator, security_injection_base):
        result = validator.validate(security_injection_base, "golden_sec_injection_001")
        assert result.passed, f"Validation failed: {result.errors}"

    def test_security_injection_score_above_maximum(self, validator, security_injection_base):
        data = copy.deepcopy(security_injection_base)
        data["data"]["score"] = 0.45
        data["data"]["data"]["overall_score"] = 0.45
        data["data"]["data"]["security_tests"]["injection"]["score"] = 0.35
        result = validator.validate(data, "golden_sec_injection_001")
        assert not result.passed
        assert any("exceeds maximum" in error for error in result.errors)

    def test_security_injection_detected_false(self, validator, security_injection_base):
        data = copy.deepcopy(security_injection_base)
        data["data"]["data"]["security_tests"]["injection"]["detected"] = False
        data["data"]["data"]["detected_items"] = ["jailbreak"]
        result = validator.validate(data, "golden_sec_injection_001")
        assert not result.passed
        assert any("injection" in error and "detected" in error for error in result.errors)


class TestConvergenceScore:
    @pytest.mark.parametrize("matched,total,expected", [
        (10, 12, 0.8333),
        (100, 100, 1.0),
        (0, 100, 0.0),
        (0, 0, 0.0),
    ])
    def test_convergence_score(self, validator, matched, total, expected):
        result = ValidationResult()
        result.matched_fields = matched
        result.total_fields = total
        score = validator.calculate_convergence_score(result)
        assert score == pytest.approx(expected, 0.0001)


class TestTypeConstraints:
    def test_type_string_validation(self, validator, security_injection_base):
        data = copy.deepcopy(security_injection_base)
        data["data"]["text"] = "valid string"
        data["data"]["data"]["detected_items"] = []
        result = validator.validate(data, "golden_sec_injection_001")
        assert result.passed, f"Validation failed: {result.errors}"

    def test_type_array_validation(self, validator, security_injection_base):
        result = validator.validate(security_injection_base, "golden_sec_injection_001")
        assert result.passed, f"Validation failed: {result.errors}"

    def test_type_object_validation(self, validator, qa_high_quality_base):
        data = copy.deepcopy(qa_high_quality_base)
        data["routing"] = {"type": "eval_platform"}
        result = validator.validate(data, "golden_qa_high_quality_001")
        assert result.passed, f"Validation failed: {result.errors}"