import pytest
from unittest.mock import patch
from src.ai.defect_analyzer import DefectAnalyzer


class TestDefectAnalyzerFallbackField:
    @pytest.fixture
    def analyzer_with_fallback(self):
        return DefectAnalyzer(llm_api_key=None)

    def test_analyze_test_results_fallback_mode_sets_fallback_used(self, analyzer_with_fallback):
        """边界：fallback模式下分析测试结果应设置fallback_used=True"""
        test_results = {
            "failures": [
                {
                    "test_name": "test_func",
                    "error_message": "AssertionError: test",
                    "location": "test_file.py:10",
                }
            ],
            "errors": [],
        }
        
        result = analyzer_with_fallback.analyze_test_results(test_results)
        
        assert analyzer_with_fallback.use_fallback is True
        assert result.fallback_used is True, (
            "AnalysisResult.fallback_used 应为 True，因为使用了 fallback 模式"
        )

    def test_analyze_code_fallback_mode_sets_fallback_used(self, analyzer_with_fallback):
        """边界：fallback模式下分析代码应设置fallback_used=True"""
        code = 'password = "secret"'
        
        result = analyzer_with_fallback.analyze_code(code, "test.py")
        
        assert analyzer_with_fallback.use_fallback is True
        assert result.fallback_used is True, (
            "AnalysisResult.fallback_used 应为 True，因为使用了 fallback 模式"
        )

    def test_llm_exception_fallback_sets_fallback_used(self):
        """异常：LLM分析失败回退到fallback时应设置fallback_used=True"""
        analyzer = DefectAnalyzer(llm_api_key="test_key")
        
        test_results = {
            "failures": [{"test_name": "test", "error_message": "Error"}],
            "errors": [],
        }
        
        with patch("src.ai.defect_analyzer.openai") as mock_openai:
            mock_openai.OpenAI.side_effect = Exception("LLM connection error")
            
            result = analyzer.analyze_test_results(test_results)
            
            assert result.success is False
            assert result.fallback_used is True, (
                "AnalysisResult.fallback_used 应为 True，因为LLM失败后使用了 fallback"
            )