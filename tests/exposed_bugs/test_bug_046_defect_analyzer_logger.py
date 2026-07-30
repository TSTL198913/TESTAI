import pytest
from src.ai.defect_analyzer import DefectAnalyzer


class TestDefectAnalyzerLogger:
    def test_defect_analyzer_has_logger(self):
        analyzer = DefectAnalyzer()
        
        assert hasattr(analyzer, '_logger') or hasattr(analyzer, 'logger'), \
            "DefectAnalyzer should have a logger attribute for proper logging"

    def test_analyze_code_fallback_detects_hardcoded_password(self):
        analyzer = DefectAnalyzer()
        
        code_with_password = 'password = "secret123"'
        result = analyzer.analyze_code(code_with_password, "test.py")
        
        assert result.fallback_used is True
        assert any(f.id == "security_hardcoded_password" for f in result.findings)

    def test_analyze_code_fallback_detects_silent_exception(self):
        analyzer = DefectAnalyzer()
        
        code_with_except = 'try:\n    x = 1/0\nexcept:\n    pass'
        result = analyzer.analyze_code(code_with_except, "test.py")
        
        assert result.fallback_used is True
        assert any(f.id == "silent_exception" for f in result.findings)