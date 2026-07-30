import pytest
from unittest.mock import patch, MagicMock
from src.ai.defect_analyzer import DefectAnalyzer, DefectSeverity, DefectType, DefectFinding


class TestDefectAnalyzer:
    @pytest.fixture
    def analyzer_with_fallback(self):
        return DefectAnalyzer(llm_api_key=None)

    @pytest.fixture
    def analyzer_with_llm(self):
        return DefectAnalyzer(llm_api_key="test_key")

    def test_init_uses_environment_variable(self):
        """正向：初始化时使用环境变量中的API key"""
        with patch("os.environ", {"OPENAI_API_KEY": "env_key"}):
            analyzer = DefectAnalyzer()
            assert analyzer.llm_api_key == "env_key"
            assert analyzer.use_fallback is False

    def test_init_without_api_key_uses_fallback(self):
        """边界：没有API key时使用fallback模式"""
        with patch("os.environ", {}):
            analyzer = DefectAnalyzer()
            assert analyzer.llm_api_key is None
            assert analyzer.use_fallback is True

    def test_analyze_test_results_fallback_mode(self, analyzer_with_fallback):
        """正向：fallback模式下分析测试结果"""
        test_results = {
            "failures": [
                {
                    "test_name": "test_func",
                    "error_message": "AssertionError: expected 5, got 3",
                    "location": "test_file.py:10",
                }
            ],
            "errors": [],
        }
        
        result = analyzer_with_fallback.analyze_test_results(test_results)
        
        assert result.success is True
        assert result.total_findings == 1
        assert analyzer_with_fallback.use_fallback is True
        assert result.findings[0].severity == DefectSeverity.HIGH
        assert result.findings[0].defect_type == DefectType.LOGIC_ERROR

    def test_analyze_test_results_with_errors(self, analyzer_with_fallback):
        """异常：测试结果包含errors时正确分类"""
        test_results = {
            "failures": [],
            "errors": [
                {
                    "test_name": "test_crash",
                    "error_message": "KeyError: 'missing_key'",
                    "location": "test_file.py:20",
                }
            ],
        }
        
        result = analyzer_with_fallback.analyze_test_results(test_results)
        
        assert result.total_findings == 1
        assert result.findings[0].severity == DefectSeverity.HIGH
        assert result.findings[0].defect_type == DefectType.LOGIC_ERROR

    def test_analyze_code_fallback_hardcoded_password(self, analyzer_with_fallback):
        """负向：fallback模式检测硬编码密码"""
        code = 'password = "secret123"'
        
        result = analyzer_with_fallback.analyze_code(code, "test.py")
        
        assert result.total_findings >= 1
        finding = next(f for f in result.findings if f.id == "security_hardcoded_password")
        assert finding.severity == DefectSeverity.CRITICAL
        assert finding.defect_type == DefectType.SECURITY

    def test_analyze_code_fallback_silent_exception(self, analyzer_with_fallback):
        """负向：fallback模式检测静默异常处理"""
        code = "try:\n    risky_operation()\nexcept:\n    pass"
        
        result = analyzer_with_fallback.analyze_code(code, "test.py")
        
        assert result.total_findings >= 1
        finding = next(f for f in result.findings if f.id == "silent_exception")
        assert finding.severity == DefectSeverity.MEDIUM
        assert finding.defect_type == DefectType.LOGIC_ERROR

    def test_analyze_code_fallback_none_comparison(self, analyzer_with_fallback):
        """边界：fallback模式检测None值比较使用=="""
        code = "if value == None:"
        
        result = analyzer_with_fallback.analyze_code(code, "test.py")
        
        assert result.total_findings >= 1
        finding = next(f for f in result.findings if f.id == "equality_none")
        assert finding.severity == DefectSeverity.LOW
        assert finding.defect_type == DefectType.LOGIC_ERROR

    def test_analyze_code_fallback_no_issues(self, analyzer_with_fallback):
        """正向：无问题代码返回空findings"""
        code = "def safe_function(x):\n    return x + 1"
        
        result = analyzer_with_fallback.analyze_code(code, "test.py")
        
        assert result.success is True
        assert result.total_findings == 0

    def test_infer_severity_assertion_error(self, analyzer_with_fallback):
        """边界：断言错误推断为HIGH严重程度"""
        failure = {"error_message": "AssertionError: test"}
        severity = analyzer_with_fallback._infer_severity(failure)
        assert severity == DefectSeverity.HIGH

    def test_infer_severity_key_error(self, analyzer_with_fallback):
        """边界：KeyError推断为MEDIUM严重程度"""
        failure = {"error_message": "KeyError: 'key'"}
        severity = analyzer_with_fallback._infer_severity(failure)
        assert severity == DefectSeverity.MEDIUM

    def test_infer_severity_unknown_error(self, analyzer_with_fallback):
        """边界：未知错误推断为LOW严重程度"""
        failure = {"error_message": "SomeError: unknown"}
        severity = analyzer_with_fallback._infer_severity(failure)
        assert severity == DefectSeverity.LOW

    def test_build_analysis_result_counts(self, analyzer_with_fallback):
        """正向：正确统计各严重程度数量"""
        findings = [
            DefectFinding(id="1", title="test", severity=DefectSeverity.CRITICAL, defect_type=DefectType.SECURITY, description=""),
            DefectFinding(id="2", title="test", severity=DefectSeverity.HIGH, defect_type=DefectType.LOGIC_ERROR, description=""),
            DefectFinding(id="3", title="test", severity=DefectSeverity.HIGH, defect_type=DefectType.LOGIC_ERROR, description=""),
            DefectFinding(id="4", title="test", severity=DefectSeverity.MEDIUM, defect_type=DefectType.PERFORMANCE, description=""),
            DefectFinding(id="5", title="test", severity=DefectSeverity.LOW, defect_type=DefectType.USABILITY, description=""),
        ]
        
        result = analyzer_with_fallback._build_analysis_result(findings)
        
        assert result.total_findings == 5
        assert result.critical_count == 1
        assert result.high_count == 2
        assert result.medium_count == 1
        assert result.low_count == 1