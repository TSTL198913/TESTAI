import pytest
from unittest.mock import patch, MagicMock
from src.ai.result_analyzer import ResultAnalyzer


class TestResultAnalyzerNoLogging:
    def test_analyze_with_llm_logs_error(self):
        analyzer = ResultAnalyzer(llm_api_key="test_key")
        
        log_capture = []
        
        def capture_log(*args, **kwargs):
            log_capture.append(args[0] if args else "")
        
        with patch.object(analyzer.logger, 'error', capture_log):
            with pytest.raises(Exception):
                analyzer._analyze_with_llm({"pass_rate": 80}, None)
            
            assert len(log_capture) > 0, "Expected at least one error log when LLM analysis fails"
            assert "LLM analysis failed" in log_capture[0], f"Expected 'LLM analysis failed' in log, got: {log_capture[0]}"