import pytest
from src.engine.factory import StepFactory


class TestStepFactoryMutation:
    def test_create_does_not_mutate_input_dict(self):
        """边界：StepFactory.create不应修改调用者的输入字典"""
        original_dict = {"step_id": "test_step", "method": "GET", "url": "http://test.com", "description": "Test step"}
        original_copy = original_dict.copy()
        
        StepFactory.create(original_dict)
        
        assert original_dict == original_copy, (
            "BUG-027: StepFactory.create()修改了调用者的输入字典"
        )

    def test_create_without_protocol_does_not_add_it(self):
        """边界：原始字典没有protocol时，不应添加该字段"""
        original_dict = {"step_id": "test_step", "method": "GET", "url": "http://test.com", "description": "Test step"}
        
        StepFactory.create(original_dict)
        
        assert "protocol" not in original_dict, (
            "BUG-027: StepFactory.create()向原始字典添加了protocol字段"
        )

    def test_create_produces_valid_test_step(self):
        """正向：StepFactory.create应生成有效的TestStep对象"""
        raw_step = {
            "step_id": "test_step",
            "protocol": "http",
            "method": "GET",
            "url": "http://test.com",
            "description": "Test step",
        }
        
        step = StepFactory.create(raw_step)
        
        assert step.step_id == "test_step"
        assert step.protocol == "http"
        assert step.method == "GET"

    def test_create_with_nested_protocol(self):
        """边界：StepFactory.create应能处理嵌套的协议结构，保留step_id"""
        raw_step = {
            "step_id": "test_step",
            "protocol": "http",
            "http": {
                "method": "GET",
                "url": "http://test.com",
                "description": "Test step",
            },
        }
        
        step = StepFactory.create(raw_step)
        
        assert step.step_id == "test_step"
        assert step.protocol == "http"

    def test_create_preserves_original_dict(self):
        """正向：验证StepFactory.create不修改输入字典"""
        original_dict = {"step_id": "test_step", "method": "GET", "url": "http://test.com", "description": "Test step"}
        original_keys = set(original_dict.keys())
        
        StepFactory.create(original_dict)
        
        assert set(original_dict.keys()) == original_keys, (
            "StepFactory.create不应添加新字段到原始字典"
        )
        assert "protocol" not in original_dict, (
            "protocol字段不应被添加到原始字典"
        )