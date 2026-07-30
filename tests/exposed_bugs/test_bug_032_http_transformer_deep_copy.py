import pytest
from src.engine.transformers import HttpTransformer


class TestHttpTransformerDeepCopy:
    def test_transform_does_not_mutate_nested_params(self):
        transformer = HttpTransformer()
        original_step = {
            "step_id": "test_step",
            "params": {
                "url": "http://example.com",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
            },
        }

        original_params = original_step["params"].copy()

        result = transformer.transform(original_step)

        assert original_step["params"] == original_params, "Original params dict should not be mutated"

    def test_transform_preserves_nested_dict_independence(self):
        transformer = HttpTransformer()
        original_step = {
            "step_id": "test_step",
            "params": {
                "url": "http://example.com",
                "nested": {"key": "value"},
            },
        }

        result = transformer.transform(original_step)

        if "nested" in result:
            result["nested"]["key"] = "modified"

        assert original_step["params"]["nested"]["key"] == "value", "Nested dict should be independent copy"