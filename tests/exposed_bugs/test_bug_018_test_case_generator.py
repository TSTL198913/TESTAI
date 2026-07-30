import pytest
from unittest.mock import patch, MagicMock
from src.ai.test_case_generator import TestCaseGenerator, TestCaseType, GeneratedTestCase


class TestTestCaseGenerator:
    @pytest.fixture
    def generator_with_fallback(self):
        return TestCaseGenerator(llm_api_key=None)

    @pytest.fixture
    def generator_with_llm(self):
        return TestCaseGenerator(llm_api_key="test_key")

    def test_init_uses_environment_variable(self):
        """正向：初始化时使用环境变量中的API key"""
        with patch("os.environ", {"OPENAI_API_KEY": "env_key"}):
            generator = TestCaseGenerator()
            assert generator.llm_api_key == "env_key"
            assert generator.use_fallback is False

    def test_init_without_api_key_uses_fallback(self):
        """边界：没有API key时使用fallback模式"""
        with patch("os.environ", {}):
            generator = TestCaseGenerator()
            assert generator.llm_api_key is None
            assert generator.use_fallback is True

    def test_generate_from_spec_api_type(self, generator_with_fallback):
        """正向：fallback模式下生成API测试用例"""
        spec = {
            "name": "Test API",
            "type": "api",
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/users",
                    "params": [{"name": "id", "type": "integer"}],
                }
            ],
        }
        
        result = generator_with_fallback.generate_from_spec(spec)
        
        assert result.success is True
        assert result.total_generated >= 2
        assert result.fallback_used is True
        
        success_case = next(tc for tc in result.test_cases if "success" in tc.id)
        assert success_case.type == TestCaseType.API
        assert success_case.priority == "high"
        
        invalid_case = next(tc for tc in result.test_cases if "invalid_params" in tc.id)
        assert invalid_case.type == TestCaseType.API
        assert invalid_case.priority == "medium"

    def test_generate_from_spec_unit_type(self, generator_with_fallback):
        """正向：fallback模式下生成单元测试用例"""
        spec = {
            "name": "Test Unit",
            "type": "unit",
            "functions": [
                {"name": "calculate", "params": ["x", "y"]}
            ],
        }
        
        result = generator_with_fallback.generate_from_spec(spec)
        
        assert result.success is True
        assert result.total_generated >= 2
        
        normal_case = next(tc for tc in result.test_cases if "normal" in tc.id)
        assert normal_case.type == TestCaseType.UNIT
        
        invalid_case = next(tc for tc in result.test_cases if "invalid" in tc.id)
        assert invalid_case.type == TestCaseType.UNIT

    def test_generate_from_spec_ui_type(self, generator_with_fallback):
        """正向：fallback模式下生成UI测试用例"""
        spec = {
            "name": "Test UI",
            "type": "ui",
            "pages": [
                {"name": "LoginPage"}
            ],
        }
        
        result = generator_with_fallback.generate_from_spec(spec)
        
        assert result.success is True
        assert result.total_generated >= 1
        
        load_case = next(tc for tc in result.test_cases if "load" in tc.id)
        assert load_case.type == TestCaseType.UI

    def test_generate_api_test_cases_with_missing_param(self, generator_with_fallback):
        """边界：API测试用例包含缺失参数场景"""
        endpoint = {
            "method": "POST",
            "path": "/api/login",
            "params": [{"name": "username"}, {"name": "password"}],
        }
        
        cases = generator_with_fallback._generate_api_test_cases(endpoint)
        
        missing_username_case = next(tc for tc in cases if "missing_username" in tc.id)
        assert missing_username_case is not None
        
        missing_password_case = next(tc for tc in cases if "missing_password" in tc.id)
        assert missing_password_case is not None

    def test_generate_from_code_python(self, generator_with_fallback):
        """正向：从Python代码生成测试用例"""
        code = """
def add(a, b):
    return a + b

def multiply(x, y):
    return x * y
"""
        
        result = generator_with_fallback.generate_from_code(code, "python")
        
        assert result.success is True
        assert result.total_generated >= 4
        
        add_normal_case = next(tc for tc in result.test_cases if "add_normal" in tc.id)
        assert add_normal_case is not None
        
        multiply_case = next(tc for tc in result.test_cases if "multiply" in tc.id)
        assert multiply_case is not None

    def test_generate_from_code_empty(self, generator_with_fallback):
        """边界：空代码返回空测试用例"""
        code = ""
        
        result = generator_with_fallback.generate_from_code(code, "python")
        
        assert result.success is True
        assert result.total_generated == 0

    def test_generate_from_code_non_python(self, generator_with_fallback):
        """边界：非Python代码返回空测试用例"""
        code = "function hello() { console.log('hello'); }"
        
        result = generator_with_fallback.generate_from_code(code, "javascript")
        
        assert result.success is True
        assert result.total_generated == 0

    def test_build_prompt_contains_spec_info(self, generator_with_fallback):
        """正向：构建的prompt包含规范信息"""
        spec = {
            "name": "Test API",
            "type": "api",
            "description": "Test description",
            "endpoints": [{"method": "GET", "path": "/test"}],
        }
        
        prompt = generator_with_fallback._build_prompt(spec)
        
        assert "Test API" in prompt
        assert "api" in prompt
        assert "Test description" in prompt
        assert "/test" in prompt

    def test_generated_test_case_has_all_fields(self, generator_with_fallback):
        """正向：生成的测试用例包含所有必要字段"""
        spec = {
            "name": "Test",
            "type": "unit",
            "functions": [{"name": "test_func"}],
        }
        
        result = generator_with_fallback.generate_from_spec(spec)
        
        tc = result.test_cases[0]
        assert tc.id is not None
        assert tc.name is not None
        assert tc.type is not None
        assert tc.description is not None
        assert tc.steps is not None
        assert tc.expected_results is not None
        assert tc.priority is not None
        assert tc.tags is not None
        assert tc.preconditions is not None
        assert tc.data is not None