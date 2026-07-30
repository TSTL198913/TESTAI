import pytest
from unittest.mock import patch, MagicMock
from src.ai.defect_analyzer import DefectAnalyzer


class TestDefectAnalyzerFallbackException:
    def test_analyze_test_results_handles_fallback_exception(self):
        analyzer = DefectAnalyzer(llm_api_key="test_key")
        
        test_results = {"failures": [], "errors": []}
        
        with patch.object(analyzer, '_analyze_with_llm', side_effect=RuntimeError("LLM error")):
            with patch.object(analyzer, '_analyze_fallback', side_effect=ValueError("Fallback error")):
                result = analyzer.analyze_test_results(test_results)

                assert result.success is False
                assert "LLM analysis failed" in result.error_message

    def test_analyze_code_handles_fallback_exception(self):
        analyzer = DefectAnalyzer(llm_api_key="test_key")
        
        code = "def test():\n    pass"
        
        with patch.object(analyzer, '_analyze_code_with_llm', side_effect=RuntimeError("LLM error")):
            with patch.object(analyzer, '_analyze_code_fallback', side_effect=ValueError("Fallback error")):
                result = analyzer.analyze_code(code, "test.py")

                assert result.success is False
                assert "LLM analysis failed" in result.error_message