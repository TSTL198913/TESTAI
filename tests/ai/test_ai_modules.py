import pytest
from src.ai.test_case_generator import TestCaseGenerator, TestCaseType, GenerationResult
from src.ai.defect_analyzer import DefectAnalyzer, DefectSeverity, DefectType, AnalysisResult
from src.ai.result_analyzer import ResultAnalyzer, MetricCategory, TrendDirection, ResultAnalysis


class TestTestCaseGenerator:
    def test_generate_from_spec_api_fallback(self):
        generator = TestCaseGenerator(llm_api_key=None)
        spec = {
            "name": "用户管理API",
            "type": "api",
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/users",
                    "params": [{"name": "page"}, {"name": "size"}],
                }
            ],
        }
        
        result = generator.generate_from_spec(spec)
        
        assert result.success is True
        assert result.fallback_used is True
        assert result.total_generated >= 2
        assert len(result.test_cases) >= 2
        
        tc = result.test_cases[0]
        assert tc.type == TestCaseType.API
        assert tc.priority == "high"
        assert "api" in tc.tags

    def test_generate_from_spec_unit_fallback(self):
        generator = TestCaseGenerator(llm_api_key=None)
        spec = {
            "name": "数学工具函数",
            "type": "unit",
            "functions": [{"name": "add", "params": ["a", "b"]}],
        }
        
        result = generator.generate_from_spec(spec)
        
        assert result.success is True
        assert result.total_generated >= 2
        
        normal_case = next(tc for tc in result.test_cases if "正常参数" in tc.name)
        assert normal_case is not None
        assert normal_case.priority == "high"

    def test_generate_from_spec_ui_fallback(self):
        generator = TestCaseGenerator(llm_api_key=None)
        spec = {
            "name": "登录页面",
            "type": "ui",
            "pages": [{"name": "login"}],
        }
        
        result = generator.generate_from_spec(spec)
        
        assert result.success is True
        assert result.total_generated >= 1
        assert result.test_cases[0].type == TestCaseType.UI

    def test_generate_from_code_python(self):
        generator = TestCaseGenerator(llm_api_key=None)
        code = """
def calculate_sum(a, b):
    return a + b

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
"""
        
        result = generator.generate_from_code(code, language="python")
        
        assert result.success is True
        assert result.total_generated >= 4
        assert any("calculate_sum" in tc.name for tc in result.test_cases)
        assert any("divide" in tc.name for tc in result.test_cases)

    def test_generate_api_test_cases_with_missing_params(self):
        generator = TestCaseGenerator(llm_api_key=None)
        spec = {
            "name": "测试API",
            "type": "api",
            "endpoints": [
                {
                    "method": "POST",
                    "path": "/api/create",
                    "params": [{"name": "username"}, {"name": "email"}],
                }
            ],
        }
        
        result = generator.generate_from_spec(spec)
        
        assert result.total_generated == 4
        assert any("缺少username" in tc.name for tc in result.test_cases)
        assert any("缺少email" in tc.name for tc in result.test_cases)

    def test_generate_fallback_without_endpoints(self):
        generator = TestCaseGenerator(llm_api_key=None)
        spec = {"name": "空规范", "type": "api", "endpoints": []}
        
        result = generator.generate_from_spec(spec)
        
        assert result.success is True
        assert result.total_generated == 0


class TestDefectAnalyzer:
    def test_analyze_code_hardcoded_password(self):
        analyzer = DefectAnalyzer(llm_api_key=None)
        code = 'password = "secret123"'
        
        result = analyzer.analyze_code(code, "test.py")
        
        assert result.success is True
        assert result.total_findings >= 1
        finding = next(f for f in result.findings if f.title == "硬编码密码")
        assert finding.severity == DefectSeverity.CRITICAL
        assert finding.defect_type == DefectType.SECURITY
        assert finding.confidence >= 0.9

    def test_analyze_code_silent_exception(self):
        analyzer = DefectAnalyzer(llm_api_key=None)
        code = """
try:
    risky_operation()
except:
    pass
"""
        
        result = analyzer.analyze_code(code, "test.py")
        
        assert result.total_findings >= 1
        finding = next(f for f in result.findings if f.title == "静默异常处理")
        assert finding.severity == DefectSeverity.MEDIUM

    def test_analyze_code_print_debug(self):
        analyzer = DefectAnalyzer(llm_api_key=None)
        code = """
def process_data():
    print("debug info")
    return True
"""
        
        result = analyzer.analyze_code(code, "test.py")
        
        assert result.total_findings >= 1
        finding = next(f for f in result.findings if f.title == "调试打印语句")
        assert finding.severity == DefectSeverity.LOW

    def test_analyze_code_none_comparison(self):
        analyzer = DefectAnalyzer(llm_api_key=None)
        code = 'if value == None:'
        
        result = analyzer.analyze_code(code, "test.py")
        
        assert result.total_findings >= 1
        finding = next(f for f in result.findings if f.title == "None值比较使用==")
        assert finding.severity == DefectSeverity.LOW

    def test_analyze_code_no_defects(self):
        analyzer = DefectAnalyzer(llm_api_key=None)
        code = """
def add(a, b):
    if a is None or b is None:
        raise ValueError("Arguments cannot be None")
    return a + b
"""
        
        result = analyzer.analyze_code(code, "test.py")
        
        assert result.success is True
        assert result.total_findings == 0

    def test_analyze_test_results_failures(self):
        analyzer = DefectAnalyzer(llm_api_key=None)
        test_results = {
            "failures": [
                {
                    "test_name": "test_critical_feature",
                    "error_message": "AssertionError: Expected 200 but got 500",
                    "location": "test_api.py:42",
                }
            ],
            "errors": [],
        }
        
        result = analyzer.analyze_test_results(test_results)
        
        assert result.total_findings >= 1
        finding = next(f for f in result.findings if "test_critical_feature" in f.title)
        assert finding.severity == DefectSeverity.HIGH

    def test_analyze_test_results_errors(self):
        analyzer = DefectAnalyzer(llm_api_key=None)
        test_results = {
            "failures": [],
            "errors": [
                {"test_name": "test_network", "error_message": "TimeoutError: Connection timed out"}
            ],
        }
        
        result = analyzer.analyze_test_results(test_results)
        
        assert result.total_findings >= 1
        finding = next(f for f in result.findings if "test_network" in f.title)
        assert finding.severity == DefectSeverity.HIGH

    def test_infer_severity_keyerror(self):
        analyzer = DefectAnalyzer(llm_api_key=None)
        failure = {"error_message": "KeyError: 'missing_key'"}
        severity = analyzer._infer_severity(failure)
        assert severity == DefectSeverity.MEDIUM

    def test_infer_defect_type_performance(self):
        analyzer = DefectAnalyzer(llm_api_key=None)
        failure = {"error_message": "Timeout: request timed out after 30s"}
        defect_type = analyzer._infer_defect_type(failure)
        assert defect_type == DefectType.PERFORMANCE


class TestResultAnalyzer:
    def test_analyze_pass_rate_decrease(self):
        analyzer = ResultAnalyzer(llm_api_key=None)
        current_results = {"pass_rate": 70, "total_tests": 100, "passed_tests": 70, "failed_tests": 30}
        previous_results = {"pass_rate": 90}
        
        result = analyzer.analyze(current_results, previous_results)
        
        assert result.success is True
        insight = next(i for i in result.insights if i.id == "pass_rate_drop")
        assert insight is not None
        assert insight.severity == "high"

    def test_analyze_low_coverage(self):
        analyzer = ResultAnalyzer(llm_api_key=None)
        current_results = {"coverage": 65, "total_tests": 100, "passed_tests": 90, "failed_tests": 10}
        
        result = analyzer.analyze(current_results)
        
        insight = next(i for i in result.insights if i.id == "low_coverage")
        assert insight is not None
        assert insight.severity == "medium"

    def test_analyze_test_failures(self):
        analyzer = ResultAnalyzer(llm_api_key=None)
        current_results = {"total_tests": 100, "passed_tests": 95, "failed_tests": 5}
        
        result = analyzer.analyze(current_results)
        
        insight = next(i for i in result.insights if i.id == "test_failures")
        assert insight is not None
        assert insight.severity == "medium"

    def test_analyze_test_failures_high_severity(self):
        analyzer = ResultAnalyzer(llm_api_key=None)
        current_results = {"total_tests": 100, "passed_tests": 80, "failed_tests": 20}
        
        result = analyzer.analyze(current_results)
        
        insight = next(i for i in result.insights if i.id == "test_failures")
        assert insight.severity == "high"

    def test_analyze_low_kill_rate(self):
        analyzer = ResultAnalyzer(llm_api_key=None)
        current_results = {"kill_rate": 60, "total_tests": 100, "passed_tests": 100, "failed_tests": 0}
        
        result = analyzer.analyze(current_results)
        
        insight = next(i for i in result.insights if i.id == "low_kill_rate")
        assert insight is not None

    def test_calculate_trends_pass_rate_up(self):
        analyzer = ResultAnalyzer(llm_api_key=None)
        current = {"pass_rate": 95}
        previous = {"pass_rate": 80}
        
        result = analyzer.analyze(current, previous)
        
        trend = next(t for t in result.trends if t.category == MetricCategory.PASS_RATE)
        assert trend.direction == TrendDirection.UP
        assert trend.change_percent > 0

    def test_calculate_trends_response_time_increase(self):
        analyzer = ResultAnalyzer(llm_api_key=None)
        current = {"avg_response_time_ms": 200}
        previous = {"avg_response_time_ms": 100}
        
        result = analyzer.analyze(current, previous)
        
        trend = next(t for t in result.trends if t.category == MetricCategory.RESPONSE_TIME)
        assert trend.direction == TrendDirection.DOWN

    def test_generate_summary_healthy(self):
        analyzer = ResultAnalyzer(llm_api_key=None)
        current_results = {"total_tests": 100, "passed_tests": 95, "failed_tests": 5}
        
        result = analyzer.analyze(current_results)
        
        assert result.summary["overall_health"] == "healthy"

    def test_generate_summary_degraded(self):
        analyzer = ResultAnalyzer(llm_api_key=None)
        current_results = {"total_tests": 100, "passed_tests": 75, "failed_tests": 25}
        
        result = analyzer.analyze(current_results)
        
        assert result.summary["overall_health"] == "degraded"

    def test_generate_summary_unhealthy(self):
        analyzer = ResultAnalyzer(llm_api_key=None)
        current_results = {"total_tests": 100, "passed_tests": 60, "failed_tests": 40}
        
        result = analyzer.analyze(current_results)
        
        assert result.summary["overall_health"] == "unhealthy"