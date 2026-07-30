import pytest
from src.engine.transformers import HttpTransformer


class TestHttpTransformerMutation:
    def test_transform_does_not_mutate_input_dict(self):
        """边界：HttpTransformer.transform不应修改调用者的输入字典"""
        original_dict = {
            "step_id": "test_step",
            "protocol": "http",
            "params": {
                "url": "http://test.com",
                "method": "GET",
            },
            "description": "Test step",
        }
        original_copy = original_dict.copy()
        original_copy["params"] = original_dict["params"].copy()

        transformer = HttpTransformer()
        transformer.transform(original_dict)

        assert original_dict == original_copy, (
            "BUG-028: HttpTransformer.transform()修改了调用者的输入字典"
        )

    def test_transform_preserves_original_params(self):
        """边界：HttpTransformer.transform不应移除原始params字段"""
        original_dict = {
            "step_id": "test_step",
            "protocol": "http",
            "params": {
                "url": "http://test.com",
                "method": "GET",
            },
            "description": "Test step",
        }

        transformer = HttpTransformer()
        transformer.transform(original_dict)

        assert "params" in original_dict, (
            "HttpTransformer.transform()不应移除原始params字段"
        )