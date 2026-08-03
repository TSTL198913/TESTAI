"""DefectAnalyzer / ResultAnalyzer / TestCaseGenerator 单元测试。

测试目标 (用户测试哲学: 验证业务逻辑正确性, 非单纯覆盖率):
  这三个模块此前没有任何直接测试, 仅靠包导入产生 37-39% 的虚高覆盖。
  本文件覆盖其 fallback 业务逻辑 (无 OPENAI_API_KEY 场景), 验证:
  - DefectAnalyzer: 测试结果分析 + 代码静态缺陷检测
  - ResultAnalyzer: 趋势计算 + 洞察生成 + 健康度摘要
  - TestCaseGenerator: 从 spec/code 生成测试用例

覆盖五场景 (正向/负向/边界/异常/依赖):
  - 正向: 正常输入 → 正确分析结果
  - 负向: 空输入/无效输入 → 安全降级
  - 边界: 阈值边界值 (change_percent ±5, pass_rate 90/70)
  - 异常: LLM 异常 → fallback 兜底
  - 依赖: mock openai → LLM 路径 + 异常降级

断言规则: 验证具体业务逻辑 (findings 内容/severity/计数/trend direction),
禁止仅验证 success=True 的弱断言。
"""
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock
from typing import List

import pytest

# 确保 src 在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.ai.defect_analyzer import (
    DefectAnalyzer,
    DefectFinding,
    DefectSeverity,
    DefectType,
    AnalysisResult,
)
from src.ai.result_analyzer import (
    ResultAnalyzer,
    MetricTrend,
    MetricCategory,
    TrendDirection,
    AnalysisInsight,
    ResultAnalysis,
)
from src.ai.test_case_generator import (
    TestCaseGenerator,
    GeneratedTestCase,
    TestCaseType,
    GenerationResult,
)


# ==================== DefectAnalyzer ====================

class TestDefectAnalyzerFallback:
    """DefectAnalyzer fallback 路径 (无 API key) 测试。"""

    def setup_method(self):
        """确保走 fallback 路径。"""
        os.environ.pop("OPENAI_API_KEY", None)
        self.analyzer = DefectAnalyzer()

    # --- 正向场景 ---

    def test_analyze_test_results_with_failures(self):
        """正向: 含 failures 的测试结果 → 生成 DefectFinding, severity 按 error_message 推断。"""
        results = {
            "failures": [
                {
                    "test_name": "test_login",
                    "error_message": "AssertionError: expected 200 but got 401",
                    "location": "tests/test_auth.py:42",
                },
            ],
            "errors": [],
        }
        result = self.analyzer.analyze_test_results(results)

        assert result.success is True
        assert result.fallback_used is True
        assert result.total_findings == 1
        assert result.high_count == 1  # AssertionError → HIGH
        finding = result.findings[0]
        assert finding.severity == DefectSeverity.HIGH
        assert finding.defect_type == DefectType.LOGIC_ERROR
        assert finding.confidence == 0.7
        assert "test_login" in finding.related_tests

    def test_analyze_test_results_with_errors(self):
        """正向: 含 errors 的测试结果 → severity=HIGH, defect_type=LOGIC_ERROR。"""
        results = {
            "failures": [],
            "errors": [
                {
                    "test_name": "test_db",
                    "error_message": "ConnectionError: timeout",
                    "location": "tests/test_db.py:10",
                },
            ],
        }
        result = self.analyzer.analyze_test_results(results)

        assert result.total_findings == 1
        finding = result.findings[0]
        assert finding.severity == DefectSeverity.HIGH
        assert finding.defect_type == DefectType.LOGIC_ERROR
        assert finding.confidence == 0.6

    def test_analyze_code_hardcoded_password(self):
        """正向: 硬编码密码 → CRITICAL security finding。"""
        code = 'password = "secret123"'
        result = self.analyzer.analyze_code(code, file_path="auth.py")

        assert result.success is True
        assert result.critical_count == 1
        finding = result.findings[0]
        assert finding.severity == DefectSeverity.CRITICAL
        assert finding.defect_type == DefectType.SECURITY
        assert finding.confidence == 0.95
        assert "环境变量" in finding.suggested_fix

    def test_analyze_code_silent_exception(self):
        """正向: except:pass → MEDIUM logic_error finding。"""
        code = "try:\n    pass\nexcept:\n    pass"
        result = self.analyzer.analyze_code(code)

        assert result.medium_count == 1
        finding = result.findings[0]
        assert finding.severity == DefectSeverity.MEDIUM
        assert finding.defect_type == DefectType.LOGIC_ERROR

    def test_analyze_code_print_debug(self):
        """正向: print() + def → LOW usability finding。"""
        code = "def func():\n    print('debug')"
        result = self.analyzer.analyze_code(code)

        assert result.low_count >= 1
        finding = next(f for f in result.findings if f.id == "print_debug")
        assert finding.severity == DefectSeverity.LOW
        assert finding.defect_type == DefectType.USABILITY

    def test_analyze_code_equality_none(self):
        """正向: == None → LOW logic_error finding。"""
        code = "if x == None:\n    pass"
        result = self.analyzer.analyze_code(code)

        finding = next(f for f in result.findings if f.id == "equality_none")
        assert finding.severity == DefectSeverity.LOW
        assert finding.confidence == 0.85

    # --- 负向场景 ---

    def test_analyze_test_results_empty(self):
        """负向: 空 failures+errors → 0 findings, success=True。"""
        result = self.analyzer.analyze_test_results({"failures": [], "errors": []})

        assert result.success is True
        assert result.total_findings == 0
        assert result.critical_count == 0

    def test_analyze_code_clean(self):
        """负向: 无缺陷代码 → 0 findings。"""
        code = "def hello():\n    return 'world'"
        result = self.analyzer.analyze_code(code)

        assert result.total_findings == 0

    # --- 边界场景 ---

    def test_infer_severity_timeout(self):
        """边界: timeout 关键词 → HIGH。"""
        results = {"failures": [{"error_message": "TimeoutError"}], "errors": []}
        result = self.analyzer.analyze_test_results(results)
        assert result.findings[0].severity == DefectSeverity.HIGH
        assert result.findings[0].defect_type == DefectType.PERFORMANCE

    def test_infer_severity_keyerror(self):
        """边界: keyerror 关键词 → MEDIUM, DATA_INTEGRITY。"""
        results = {"failures": [{"error_message": "KeyError: 'user'"}], "errors": []}
        result = self.analyzer.analyze_test_results(results)
        assert result.findings[0].severity == DefectSeverity.MEDIUM
        assert result.findings[0].defect_type == DefectType.DATA_INTEGRITY

    def test_infer_severity_typeerror(self):
        """边界: typeerror 关键词 → MEDIUM。"""
        results = {"failures": [{"error_message": "TypeError"}], "errors": []}
        result = self.analyzer.analyze_test_results(results)
        assert result.findings[0].severity == DefectSeverity.MEDIUM

    def test_infer_severity_unknown(self):
        """边界: 未知错误类型 → LOW。"""
        results = {"failures": [{"error_message": "Something went wrong"}], "errors": []}
        result = self.analyzer.analyze_test_results(results)
        assert result.findings[0].severity == DefectSeverity.LOW

    def test_build_analysis_result_counting(self):
        """边界: 多 severity findings → 正确计数。"""
        findings = [
            DefectFinding("1", "a", DefectSeverity.CRITICAL, DefectType.SECURITY, "d"),
            DefectFinding("2", "b", DefectSeverity.CRITICAL, DefectType.SECURITY, "d"),
            DefectFinding("3", "c", DefectSeverity.HIGH, DefectType.LOGIC_ERROR, "d"),
            DefectFinding("4", "e", DefectSeverity.MEDIUM, DefectType.LOGIC_ERROR, "d"),
            DefectFinding("5", "f", DefectSeverity.LOW, DefectType.USABILITY, "d"),
        ]
        result = self.analyzer._build_analysis_result(findings)

        assert result.critical_count == 2
        assert result.high_count == 1
        assert result.medium_count == 1
        assert result.low_count == 1
        assert result.total_findings == 5

    # --- 异常/依赖场景 ---

    def test_parse_llm_analysis_valid(self):
        """依赖: 伪造 LLM JSON → 正确解析为 DefectFinding。"""
        llm_result = {
            "findings": [
                {
                    "id": "llm_1",
                    "title": "SQL注入",
                    "severity": "critical",
                    "defect_type": "security",
                    "description": "SQL拼接存在注入风险",
                    "location": "db.py:10",
                    "code_snippet": "cursor.execute(sql)",
                    "suggested_fix": "使用参数化查询",
                    "confidence": 0.95,
                    "related_tests": ["test_sql"],
                }
            ]
        }
        result = self.analyzer._parse_llm_analysis(llm_result)

        assert result.success is True
        assert result.total_findings == 1
        assert result.fallback_used is False  # LLM 路径, 非 fallback
        finding = result.findings[0]
        assert finding.severity == DefectSeverity.CRITICAL
        assert finding.defect_type == DefectType.SECURITY
        assert finding.confidence == 0.95

    def test_analyze_with_llm_exception_falls_back(self):
        """异常: LLM 路径异常 → fallback 兜底, success=False, fallback_used=True。"""
        analyzer = DefectAnalyzer(llm_api_key="fake-key")
        assert analyzer.use_fallback is False

        with patch("src.ai.defect_analyzer.openai") as mock_openai:
            mock_client = MagicMock()
            mock_openai.OpenAI.return_value = mock_client
            mock_client.chat.completions.create.side_effect = Exception("API timeout")

            result = analyzer.analyze_test_results(
                {"failures": [{"test_name": "t1", "error_message": "AssertionError"}], "errors": []}
            )

        assert result.success is False
        assert result.fallback_used is True
        assert "LLM analysis failed" in result.error_message
        # fallback 仍产出 findings
        assert len(result.findings) == 1


# ==================== ResultAnalyzer ====================

class TestResultAnalyzerFallback:
    """ResultAnalyzer fallback 路径 (无 API key) 测试。"""

    def setup_method(self):
        os.environ.pop("OPENAI_API_KEY", None)
        self.analyzer = ResultAnalyzer()

    # --- 正向场景 ---

    def test_analyze_with_previous_results(self):
        """正向: 有历史数据 → 生成 trends + insights + summary。"""
        current = {
            "pass_rate": 85.0,
            "coverage": 75.0,
            "avg_response_time_ms": 200.0,
            "defect_count": 3,
            "total_tests": 100,
            "passed_tests": 85,
            "failed_tests": 15,
            "kill_rate": 70,
        }
        previous = {
            "pass_rate": 90.0,
            "coverage": 80.0,
            "avg_response_time_ms": 150.0,
            "defect_count": 2,
        }
        result = self.analyzer.analyze(current, previous)

        assert result.success is True
        assert result.fallback_used is True
        assert len(result.trends) == 4  # pass_rate, coverage, response_time, defect_density
        assert "overall_health" in result.summary

    def test_analyze_without_previous_results(self):
        """正向: 无历史数据 → previous=0, trends 仍生成。"""
        current = {"pass_rate": 90.0, "coverage": 85.0, "avg_response_time_ms": 100.0, "defect_count": 0}
        result = self.analyzer.analyze(current, previous_results=None)

        assert result.success is True
        assert len(result.trends) == 4
        # previous=0 → STABLE
        for trend in result.trends:
            assert trend.direction == TrendDirection.STABLE

    # --- 边界场景 ---

    def test_create_trend_previous_zero(self):
        """边界: previous=0 → change_percent=0, STABLE。"""
        trend = self.analyzer._create_trend(MetricCategory.PASS_RATE, 90.0, 0.0)
        assert trend.change_percent == 0.0
        assert trend.direction == TrendDirection.STABLE

    def test_create_trend_increase_above_threshold(self):
        """边界: change_percent > 5 (正向) → UP。"""
        trend = self.analyzer._create_trend(MetricCategory.PASS_RATE, 95.0, 90.0)
        assert trend.direction == TrendDirection.UP
        assert trend.change_percent > 5

    def test_create_trend_decrease_below_threshold(self):
        """边界: change_percent < -5 (正向) → DOWN。"""
        trend = self.analyzer._create_trend(MetricCategory.PASS_RATE, 80.0, 90.0)
        assert trend.direction == TrendDirection.DOWN

    def test_create_trend_within_threshold(self):
        """边界: |change_percent| <= 5 → STABLE。"""
        trend = self.analyzer._create_trend(MetricCategory.PASS_RATE, 92.0, 90.0)
        assert trend.direction == TrendDirection.STABLE

    def test_create_trend_inverse_increase(self):
        """边界: inverse=True, change > 5 → DOWN (响应时间增加是坏事)。"""
        trend = self.analyzer._create_trend(
            MetricCategory.RESPONSE_TIME, 200.0, 150.0, inverse=True
        )
        assert trend.direction == TrendDirection.DOWN

    def test_create_trend_inverse_decrease(self):
        """边界: inverse=True, change < -5 → UP (响应时间减少是好事)。"""
        trend = self.analyzer._create_trend(
            MetricCategory.RESPONSE_TIME, 100.0, 150.0, inverse=True
        )
        assert trend.direction == TrendDirection.UP

    def test_summary_healthy(self):
        """边界: pass_rate >= 90 且无下降趋势 → healthy。"""
        current = {"total_tests": 100, "passed_tests": 95, "failed_tests": 5, "pass_rate": 95.0,
                    "coverage": 85.0, "avg_response_time_ms": 100.0, "defect_count": 0}
        result = self.analyzer.analyze(current)
        assert result.summary["overall_health"] == "healthy"

    def test_summary_degraded(self):
        """边界: pass_rate 70-90 → degraded。"""
        current = {"total_tests": 100, "passed_tests": 75, "failed_tests": 25, "pass_rate": 75.0,
                    "coverage": 85.0, "avg_response_time_ms": 100.0, "defect_count": 0}
        result = self.analyzer.analyze(current)
        assert result.summary["overall_health"] == "degraded"

    def test_summary_unhealthy(self):
        """边界: pass_rate < 70 → unhealthy。"""
        current = {"total_tests": 100, "passed_tests": 60, "failed_tests": 40, "pass_rate": 60.0,
                    "coverage": 85.0, "avg_response_time_ms": 100.0, "defect_count": 0}
        result = self.analyzer.analyze(current)
        assert result.summary["overall_health"] == "unhealthy"

    # --- 负向场景 ---

    def test_insights_pass_rate_drop(self):
        """负向: 通过率下降 → 生成 pass_rate_drop insight。"""
        current = {"pass_rate": 80.0, "coverage": 85.0, "avg_response_time_ms": 100.0,
                    "defect_count": 0, "failed_tests": 0, "kill_rate": 90}
        previous = {"pass_rate": 90.0, "coverage": 85.0, "avg_response_time_ms": 100.0, "defect_count": 0}
        result = self.analyzer.analyze(current, previous)

        insight = next(i for i in result.insights if i.id == "pass_rate_drop")
        assert insight.severity == "high"
        assert "下降" in insight.description

    def test_insights_low_coverage(self):
        """负向: coverage < 80 → 生成 low_coverage insight。"""
        current = {"pass_rate": 95.0, "coverage": 60.0, "avg_response_time_ms": 100.0,
                    "defect_count": 0, "failed_tests": 0, "kill_rate": 90}
        result = self.analyzer.analyze(current)

        insight = next(i for i in result.insights if i.id == "low_coverage")
        assert insight.severity == "medium"
        assert "覆盖率" in insight.description

    def test_insights_test_failures(self):
        """负向: failed_tests > 0 → 生成 test_failures insight。"""
        current = {"pass_rate": 95.0, "coverage": 85.0, "avg_response_time_ms": 100.0,
                    "defect_count": 0, "failed_tests": 3, "kill_rate": 90}
        result = self.analyzer.analyze(current)

        insight = next(i for i in result.insights if i.id == "test_failures")
        assert insight.severity == "medium"  # 3 < 5 → medium

    def test_insights_many_failures_high_severity(self):
        """负向: failed_tests > 5 → severity=high。"""
        current = {"pass_rate": 80.0, "coverage": 85.0, "avg_response_time_ms": 100.0,
                    "defect_count": 0, "failed_tests": 10, "kill_rate": 90}
        result = self.analyzer.analyze(current)

        insight = next(i for i in result.insights if i.id == "test_failures")
        assert insight.severity == "high"

    def test_insights_low_kill_rate(self):
        """负向: kill_rate < 80 → 生成 low_kill_rate insight。"""
        current = {"pass_rate": 95.0, "coverage": 85.0, "avg_response_time_ms": 100.0,
                    "defect_count": 0, "failed_tests": 0, "kill_rate": 60}
        result = self.analyzer.analyze(current)

        insight = next(i for i in result.insights if i.id == "low_kill_rate")
        assert insight.severity == "medium"
        assert "Kill Rate" in insight.description

    def test_insights_response_time_increase(self):
        """负向: 响应时间增加 (inverse DOWN) → insight。"""
        current = {"pass_rate": 95.0, "coverage": 85.0, "avg_response_time_ms": 200.0,
                    "defect_count": 0, "failed_tests": 0, "kill_rate": 90}
        previous = {"pass_rate": 95.0, "coverage": 85.0, "avg_response_time_ms": 100.0, "defect_count": 0}
        result = self.analyzer.analyze(current, previous)

        insight = next(i for i in result.insights if i.id == "response_time_increase")
        assert insight.severity == "medium"


# ==================== TestCaseGenerator ====================

class TestTestCaseGeneratorFallback:
    """TestCaseGenerator fallback 路径 (无 API key) 测试。"""

    def setup_method(self):
        os.environ.pop("OPENAI_API_KEY", None)
        self.generator = TestCaseGenerator()

    # --- 正向场景 ---

    def test_generate_from_spec_api(self):
        """正向: type=api + endpoints → 生成 API 测试用例 (success + invalid_params)。"""
        spec = {
            "name": "UserAPI",
            "type": "api",
            "endpoints": [
                {"method": "POST", "path": "/users", "params": [{"name": "username"}]},
            ],
        }
        result = self.generator.generate_from_spec(spec)

        assert result.success is True
        assert result.fallback_used is True
        # 1 success + 1 invalid_params + 1 missing_param = 3
        assert result.total_generated == 3
        # 验证 preconditions 和 data 字段
        for tc in result.test_cases:
            assert len(tc.preconditions) > 0
            assert "method" in tc.data
            assert "path" in tc.data

    def test_generate_from_spec_api_no_params(self):
        """正向: api 无 params → 只生成 success + invalid_params (无 missing_param)。"""
        spec = {
            "name": "HealthAPI",
            "type": "api",
            "endpoints": [{"method": "GET", "path": "/health", "params": []}],
        }
        result = self.generator.generate_from_spec(spec)

        assert result.total_generated == 2  # success + invalid_params

    def test_generate_from_spec_unit(self):
        """正向: type=unit + functions → 生成 unit 测试用例 (normal + invalid)。"""
        spec = {
            "name": "MathLib",
            "type": "unit",
            "functions": [{"name": "add", "params": ["a", "b"]}],
        }
        result = self.generator.generate_from_spec(spec)

        assert result.success is True
        assert result.total_generated == 2  # normal + invalid
        normal = next(tc for tc in result.test_cases if "normal" in tc.id)
        assert normal.priority == "high"
        assert "add" in normal.preconditions[0]

    def test_generate_from_spec_ui(self):
        """正向: type=ui + pages → 生成 UI 测试用例。"""
        spec = {
            "name": "WebApp",
            "type": "ui",
            "pages": [{"name": "LoginPage"}],
        }
        result = self.generator.generate_from_spec(spec)

        assert result.success is True
        assert result.total_generated == 1
        tc = result.test_cases[0]
        assert tc.type == TestCaseType.UI
        assert "LoginPage" in tc.name
        assert "/loginpage" in tc.data["url"]

    def test_generate_from_code_python(self):
        """正向: Python 代码 → 解析函数 → 生成 unit 测试用例。"""
        code = "def add(a, b):\n    return a + b\ndef greet(name):\n    return f'Hello {name}'"
        result = self.generator.generate_from_code(code, language="python")

        assert result.success is True
        # 2 functions × 2 (normal + invalid) = 4
        assert result.total_generated == 4
        # 验证函数名出现在测试用例 id 中
        ids = [tc.id for tc in result.test_cases]
        assert any("add" in i for i in ids)
        assert any("greet" in i for i in ids)

    # --- 负向场景 ---

    def test_generate_from_spec_empty_endpoints(self):
        """负向: api 类型但 endpoints 为空 → 0 用例。"""
        spec = {"name": "EmptyAPI", "type": "api", "endpoints": []}
        result = self.generator.generate_from_spec(spec)

        assert result.success is True
        assert result.total_generated == 0

    def test_generate_from_spec_unknown_type(self):
        """负向: 未知 spec type → 0 用例。"""
        spec = {"name": "Unknown", "type": "e2e"}
        result = self.generator.generate_from_spec(spec)

        assert result.success is True
        assert result.total_generated == 0

    def test_generate_from_code_no_functions(self):
        """负向: 代码无函数定义 → 0 用例。"""
        code = "x = 1\ny = 2\nprint(x + y)"
        result = self.generator.generate_from_code(code)

        assert result.success is True
        assert result.total_generated == 0

    # --- 边界场景 ---

    def test_analyze_code_python_function_no_params(self):
        """边界: 无参函数 → params=[] 正确解析。"""
        code = "def main():\n    pass"
        spec = self.generator._analyze_code(code, "python")

        assert spec["type"] == "unit"
        assert len(spec["functions"]) == 1
        assert spec["functions"][0]["name"] == "main"
        assert spec["functions"][0]["params"] == []

    def test_analyze_code_non_python(self):
        """边界: 非 Python 语言 → 不解析函数, spec 仍返回。"""
        code = "function add(a, b) { return a + b; }"
        spec = self.generator._analyze_code(code, "javascript")

        assert spec["type"] == "unit"
        assert len(spec["functions"]) == 0

    def test_generate_api_test_cases_with_params(self):
        """边界: params 有值 → 生成 missing_param 用例。"""
        endpoint = {"method": "POST", "path": "/data", "params": [{"name": "id"}, {"name": "type"}]}
        cases = self.generator._generate_api_test_cases(endpoint)

        # 1 success + 1 invalid_params + 2 missing_param = 4
        assert len(cases) == 4
        missing_cases = [c for c in cases if "missing" in c.id]
        assert len(missing_cases) == 2

    # --- 异常/依赖场景 ---

    def test_generate_with_llm_exception_falls_back(self):
        """异常: LLM 路径异常 → fallback 兜底。"""
        generator = TestCaseGenerator(llm_api_key="fake-key")
        assert generator.use_fallback is False

        with patch("builtins.__import__", side_effect=ImportError("no openai")):
            # openai import fails inside _generate_with_llm
            result = generator.generate_from_spec(
                {"name": "test", "type": "api", "endpoints": [{"method": "GET", "path": "/h"}]}
            )

        assert result.success is False
        assert result.fallback_used is True
        assert "LLM generation failed" in result.error_message
