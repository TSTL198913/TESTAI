import pytest
from src.governance.baseline import GoldenBaselineManager, BaselineRecord


class TestBaselineConfidenceErrorMessage:
    def test_confidence_level_error_message_is_correct(self):
        manager = GoldenBaselineManager()
        
        record = BaselineRecord(
            record_id="test_confidence",
            baseline_type="qa",
            data={
                "id": "test_confidence",
                "type": "qa",
                "expected_confidence_level": ["high", "good"],
            },
        )
        manager.add_baseline(record)
        
        result = manager.validate_against_baseline(
            "test_confidence",
            {"data": {"confidence_level": "low"}}
        )
        
        assert result["passed"] == False
        assert len(result["errors"]) == 1
        assert "not in" in result["errors"][0].lower(), \
            f"Expected 'not in' in error message, got: {result['errors'][0]}"
        assert "low" in result["errors"][0]
        assert "high" in result["errors"][0]
        assert "good" in result["errors"][0]