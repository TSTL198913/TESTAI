import pytest
import json
import sys
from unittest.mock import patch, MagicMock
from src.ai.result_analyzer import (
    ResultAnalyzer, ResultAnalysis, AnalysisInsight, MetricTrend,
    TrendDirection, MetricCategory,
)


# =============================================================================
# 正向场景：ResultAnalysis 数据类默认值（Mutation L52）
# =============================================================================
class TestResultAnalysisDefaults:
    def test_fallback_used_default_is_false(self):
        """L52 replace_boolean: 新实例 fallback_used 默认必须为 False"""
        result = ResultAnalysis(success=True)
        assert result.fallback_used is False, (
            "KILL-L52: ResultAnalysis 默认 fallback_used 必须为 False，"
            "变异后会变成 True，导致 _parse_llm_result 错误标识 fallback"
        )
        assert result.success is True
        assert result.error_message == ""
        assert result.insights == []
        assert result.trends == []
        assert result.summary == {}


# =============================================================================
# 异常场景：analyze() LLM 模式异常分支（Mutation L69）
# =============================================================================
class TestAnalyzeLLMExceptionPath:
    def test_analyze_llm_exception_returns_success_false(self):
        """L69 replace_boolean: LLM 异常时 success 必须为 False"""
        analyzer = ResultAnalyzer(llm_api_key="valid-key")

        with patch.object(analyzer, "_analyze_with_llm", side_effect=Exception("LLM down")):
            result = analyzer.analyze({"pass_rate": 90}, None)

        assert result.success is False, (
            "KILL-L69: LLM 异常时 analyze() 必须返回 success=False"
        )
        assert result.fallback_used is True, (
            "LLM 异常后应切换到 fallback_insights 回填"
        )
        assert "LLM analysis failed" in result.error_message, (
            "error_message 必须包含 'LLM analysis failed': " + result.error_message
        )
        # fallback 结果应被填入 insights 和 trends
        assert isinstance(result.insights, list)
        assert isinstance(result.trends, list)
        assert len(result.trends) == 4  # 5 categories minus? 实际是 4 个 PASS_RATE, COVERAGE, RESPONSE_TIME, DEFECT_DENSITY


# =============================================================================
# 负向场景：_analyze_with_llm 的 content is None 检查（Mutation L94）
# =============================================================================
class TestAnalyzeWithLLMContentNone:
    def _build_mock_openai_module(self, mock_client):
        """构造可注入 sys.modules 的假 openai 模块"""
        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = mock_client
        return fake_openai

    def test_content_none_raises_value_error(self):
        """L94 negate_condition: content is None 时必须抛 ValueError"""
        analyzer = ResultAnalyzer(llm_api_key="test-key")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = None
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        fake_openai = self._build_mock_openai_module(mock_client)

        with patch.dict(sys.modules, {"openai": fake_openai}):
            with pytest.raises(ValueError, match="LLM response content is None"):
                analyzer._analyze_with_llm({"pass_rate": 80}, None)

    def test_valid_content_does_not_raise_and_parses(self):
        """L94 negate_condition: 有效 content 不应抛异常，且必须能解析"""
        analyzer = ResultAnalyzer(llm_api_key="test-key")

        expected_result = {
            "insights": [{
                "id": "ins-1", "title": "T", "description": "D",
                "severity": "low", "recommendation": "R", "confidence": 0.5,
                "related_metrics": ["a"],
            }],
            "trends": [{
                "category": "pass_rate", "current_value": 95.0,
                "previous_value": 90.0, "direction": "up", "change_percent": 5.55,
            }],
            "summary": {"overall": "good"},
        }

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = json.dumps(expected_result)
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        fake_openai = self._build_mock_openai_module(mock_client)

        with patch.dict(sys.modules, {"openai": fake_openai}):
            parsed = analyzer._analyze_with_llm({"pass_rate": 95}, {"pass_rate": 90})

        assert parsed.success is True, (
            "KILL-L94-negate: 有效内容时必须 success=True，若 negate 则会抛异常"
        )
        assert len(parsed.insights) == 1
        assert parsed.insights[0].id == "ins-1"
        assert parsed.insights[0].confidence == 0.5
        assert len(parsed.trends) == 1
        assert parsed.trends[0].category == MetricCategory.PASS_RATE
        assert parsed.trends[0].direction == TrendDirection.UP
        assert parsed.summary == {"overall": "good"}


# =============================================================================
# 正向场景：fallback 模式分析（Mutation L113）
# =============================================================================
class TestAnalyzeFallbackMode:
    def test_fallback_used_flag_is_true(self):
        """L113 replace_boolean: fallback 模式必须标记 fallback_used=True"""
        analyzer = ResultAnalyzer(llm_api_key=None)  # 无 key → use_fallback=True
        result = analyzer.analyze({"pass_rate": 95}, None)

        assert result.success is True
        assert result.fallback_used is True, (
            "KILL-L113: fallback 分析必须设置 fallback_used=True，"
            "变异为 False 会导致调用方无法区分 LLM/规则模式"
        )
        # fallback 一定有 4 个趋势
        assert len(result.trends) == 4
        categories = {t.category for t in result.trends}
        assert categories == {
            MetricCategory.PASS_RATE, MetricCategory.COVERAGE,
            MetricCategory.RESPONSE_TIME, MetricCategory.DEFECT_DENSITY,
        }


# =============================================================================
# 正向场景：_parse_llm_result success 标记（Mutation L173）
# =============================================================================
class TestParseLLMResult:
    def test_parsed_result_success_true(self):
        """L173 replace_boolean: 解析成功必须 success=True"""
        analyzer = ResultAnalyzer(llm_api_key="k")
        raw = {
            "insights": [],
            "trends": [],
            "summary": {"k": "v"},
        }
        result = analyzer._parse_llm_result(raw)

        assert result.success is True, (
            "KILL-L173: _parse_llm_result 成功解析必须返回 success=True"
        )
        assert result.fallback_used is False
        assert result.summary == {"k": "v"}

    def test_parsed_insights_use_field_defaults(self):
        """解析缺失字段时使用默认值，验证强校验"""
        analyzer = ResultAnalyzer(llm_api_key="k")
        raw = {
            "insights": [{}],  # 所有字段缺失
            "trends": [{}],    # 所有字段缺失
        }
        result = analyzer._parse_llm_result(raw)
        # insight 默认值
        assert result.insights[0].severity == "medium"
        assert result.insights[0].confidence == 0.0
        assert result.insights[0].related_metrics == []
        # trend 默认值 (category/direction 通过 Enum 传入默认字符串，会走 Enum 构造)
        assert result.trends[0].category == MetricCategory.PASS_RATE
        assert result.trends[0].direction == TrendDirection.STABLE
        assert result.trends[0].current_value == 0.0
        assert result.trends[0].previous_value == 0.0
        assert result.trends[0].change_percent == 0.0


# =============================================================================
# 算术/边界场景：_create_trend 精确数值计算 + inverse 语义
# 覆盖 Mutation L196 / L201 / L205 (×2) / L210 / L215
# =============================================================================
class TestCreateTrendPrecision:
    def setup_method(self):
        self.analyzer = ResultAnalyzer(llm_api_key=None)

    # ---- L201 negate_condition: previous == 0 的特殊分支 ----
    def test_previous_zero_returns_stable_zero_change(self):
        """L201 negate: previous=0 时 change_percent=0.0 且 STABLE"""
        trend = self.analyzer._create_trend(
            MetricCategory.PASS_RATE, current=95.0, previous=0.0,
        )
        assert trend.change_percent == 0.0, (
            "KILL-L201: previous=0 时必须返回 change_percent=0.0"
        )
        assert trend.direction == TrendDirection.STABLE, (
            "KILL-L201: previous=0 时必须 direction=STABLE"
        )
        assert trend.current_value == 95.0
        assert trend.previous_value == 0.0

    # ---- L205 replace_arithmetic ×2: 精确验证 change_percent 公式 ----
    def test_change_percent_exact_formula_normal_branch(self):
        """L205 ×2: 精确校验 ((current-previous)/previous)*100 公式"""
        # 80 → 100： ((100-80)/80)*100 = 25.0
        trend = self.analyzer._create_trend(
            MetricCategory.PASS_RATE, current=100.0, previous=80.0,
        )
        assert trend.change_percent == pytest.approx(25.0), (
            "KILL-L205-arithmetic: (100-80)/80*100 必须等于 25.0"
        )

    def test_change_percent_exact_negative_and_boundary_4_99_stable(self):
        """L205 + L215 replace_comparison: 4.99% 增长 <5% → STABLE"""
        # 100 → 104.99： +4.99%  小于 5% → 稳定
        trend = self.analyzer._create_trend(
            MetricCategory.PASS_RATE, current=104.99, previous=100.0,
        )
        assert trend.change_percent == pytest.approx(4.99), (
            "(104.99-100)/100*100 = 4.99"
        )
        assert trend.direction == TrendDirection.STABLE, (
            "KILL-L215-compare: 4.99 < 5 必须 STABLE，> 替换为 >= 会变 UP"
        )

    # ---- L215 replace_comparison + negate: change_percent > 5 边界 ----
    def test_change_percent_exactly_5_point_01_triggers_up(self):
        """L215 negate/compare: 5.01% > 5% → UP"""
        trend = self.analyzer._create_trend(
            MetricCategory.PASS_RATE, current=105.01, previous=100.0,
        )
        assert trend.change_percent == pytest.approx(5.01)
        assert trend.direction == TrendDirection.UP, (
            "KILL-L215-negate: 5.01 > 5 必须 UP，negate 会变 STABLE/DOWN"
        )

    def test_change_percent_minus_4_99_stable(self):
        """L215 elif 分支：-4.99% 在 ±5 内 → STABLE"""
        trend = self.analyzer._create_trend(
            MetricCategory.PASS_RATE, current=95.01, previous=100.0,
        )
        assert trend.change_percent == pytest.approx(-4.99)
        assert trend.direction == TrendDirection.STABLE

    def test_change_percent_minus_5_point_01_triggers_down(self):
        """L215 elif 分支：-5.01% < -5% → DOWN"""
        trend = self.analyzer._create_trend(
            MetricCategory.PASS_RATE, current=94.99, previous=100.0,
        )
        assert trend.change_percent == pytest.approx(-5.01)
        assert trend.direction == TrendDirection.DOWN, (
            "-5.01 < -5 必须 DOWN"
        )

    # ---- L196 replace_boolean (DEFECT_DENSITY inverse=True) ----
    def test_defect_density_increase_marks_direction_down(self):
        """L196 inverse=True: 缺陷从 5 → 10 (+100%) 必须标记 DOWN（变差）"""
        # DEFECT_DENSITY 在 _calculate_trends 中固定 inverse=True 传入
        # inverse=True: change_percent>5 → DOWN（变差）；change_percent<-5 → UP（变好）
        trend = self.analyzer._create_trend(
            MetricCategory.DEFECT_DENSITY, current=10, previous=5, inverse=True,
        )
        # change: (10-5)/5*100 = +100% > 5，inverse=True → DOWN
        assert trend.change_percent == pytest.approx(100.0)
        assert trend.direction == TrendDirection.DOWN, (
            "KILL-L196: DEFECT_DENSITY inverse=True，缺陷增加 (+100%) 必须 DOWN；"
            "若 inverse 被改为 False 则会错误变 UP"
        )

    # ---- L210 negate_condition: inverse=True, change_percent < -5 → UP ----
    def test_defect_density_decrease_5_point_01_marks_up(self):
        """L210 negate: inverse=True, -5.01% 必须方向 UP（缺陷减少=变好）"""
        # 100 → 94.99 = -5.01%，inverse → UP
        trend = self.analyzer._create_trend(
            MetricCategory.DEFECT_DENSITY, current=94.99, previous=100.0, inverse=True,
        )
        assert trend.change_percent == pytest.approx(-5.01)
        assert trend.direction == TrendDirection.UP, (
            "KILL-L210: inverse=True 且 change_percent<-5 时必须 UP（变好）"
        )

    def test_defect_density_increase_4_99_inverse_stable(self):
        """inverse=True 边界：+4.99% 仍 STABLE"""
        trend = self.analyzer._create_trend(
            MetricCategory.RESPONSE_TIME, current=104.99, previous=100.0, inverse=True,
        )
        assert trend.direction == TrendDirection.STABLE

    # ---- L210 正向（inverse, change_percent>5） ----
    def test_response_time_increase_inverse_marks_down(self):
        """inverse=True 且 response_time 增加 10% → DOWN（变差）"""
        trend = self.analyzer._create_trend(
            MetricCategory.RESPONSE_TIME, current=110, previous=100, inverse=True,
        )
        assert trend.change_percent == pytest.approx(10.0)
        assert trend.direction == TrendDirection.DOWN


# =============================================================================
# _calculate_trends 整体链路：4 个趋势生成 + inverse 参数传递正确性
# =============================================================================
class TestCalculateTrends:
    def setup_method(self):
        self.analyzer = ResultAnalyzer(llm_api_key=None)

    def test_all_four_categories_present_with_correct_keys(self):
        """验证趋势计算有 4 个类别，且字段正确"""
        current = {
            "pass_rate": 90.0, "coverage": 85.0,
            "avg_response_time_ms": 200, "defect_count": 3,
        }
        previous = {
            "pass_rate": 80.0, "coverage": 80.0,
            "avg_response_time_ms": 100, "defect_count": 1,
        }
        trends = self.analyzer._calculate_trends(current, previous)
        by_cat = {t.category: t for t in trends}

        # PASS_RATE: 80→90 = +12.5% → UP (无 inverse)
        assert by_cat[MetricCategory.PASS_RATE].direction == TrendDirection.UP
        # COVERAGE: 80→85 = +6.25% → UP (无 inverse)
        assert by_cat[MetricCategory.COVERAGE].direction == TrendDirection.UP
        # RESPONSE_TIME: 100→200 = +100%, inverse=True → DOWN（变差）
        assert by_cat[MetricCategory.RESPONSE_TIME].direction == TrendDirection.DOWN
        # DEFECT_DENSITY: 1→3 = +200%, inverse=True → DOWN（变差）
        assert by_cat[MetricCategory.DEFECT_DENSITY].direction == TrendDirection.DOWN

    def test_previous_none_uses_zero_and_stable(self):
        """previous=None → 全部 previous=0 → STABLE change=0%"""
        current = {"pass_rate": 90.0, "coverage": 85.0,
                   "avg_response_time_ms": 200, "defect_count": 3}
        trends = self.analyzer._calculate_trends(current, None)
        for t in trends:
            assert t.previous_value == 0.0
            assert t.change_percent == 0.0
            assert t.direction == TrendDirection.STABLE


# =============================================================================
# _generate_insights 条件分支（Mutations L234, L246, L258, L270, L282）
# =============================================================================
class TestGenerateInsights:
    def setup_method(self):
        self.analyzer = ResultAnalyzer(llm_api_key=None)

    # ---- L234 negate_condition: PASS_RATE DOWN → pass_rate_drop ----
    def test_pass_rate_down_generates_drop_insight(self):
        """L234 negate: PASS_RATE DOWN 时必须生成 pass_rate_drop"""
        down_trend = MetricTrend(
            MetricCategory.PASS_RATE, 80.0, 95.0,
            TrendDirection.DOWN, -15.789,
        )
        insights = self.analyzer._generate_insights(
            {"pass_rate": 80.0}, [down_trend],
        )
        ids = [i.id for i in insights]
        assert "pass_rate_drop" in ids, (
            "KILL-L234: PASS_RATE DOWN 必须生成 pass_rate_drop insight"
        )
        drop = next(i for i in insights if i.id == "pass_rate_drop")
        assert drop.severity == "high"
        assert drop.confidence == 0.9
        assert "95.00%" in drop.description and "80.00%" in drop.description

    def test_pass_rate_up_no_drop_insight(self):
        """L234 反向验证：PASS_RATE UP 不生成 pass_rate_drop"""
        up_trend = MetricTrend(
            MetricCategory.PASS_RATE, 95.0, 80.0, TrendDirection.UP, 18.75,
        )
        insights = self.analyzer._generate_insights({}, [up_trend])
        ids = [i.id for i in insights]
        assert "pass_rate_drop" not in ids

    # ---- L246 replace_comparison: coverage < 80 ----
    def test_coverage_79_generates_low_coverage(self):
        """L246 compare: coverage=79 < 80 必须生成 low_coverage"""
        cov_trend = MetricTrend(
            MetricCategory.COVERAGE, 79.0, 79.0, TrendDirection.STABLE, 0.0,
        )
        insights = self.analyzer._generate_insights({}, [cov_trend])
        ids = [i.id for i in insights]
        assert "low_coverage" in ids, (
            "KILL-L246: coverage 79 < 80 必须生成 low_coverage"
        )
        low = next(i for i in insights if i.id == "low_coverage")
        assert low.severity == "medium"
        assert low.confidence == 0.85
        assert "79.00%" in low.description

    def test_coverage_exactly_80_no_low_coverage(self):
        """L246 compare 边界: coverage=80 不生成 (< 不包含等于)"""
        cov_trend = MetricTrend(
            MetricCategory.COVERAGE, 80.0, 75.0, TrendDirection.UP, 6.66,
        )
        insights = self.analyzer._generate_insights({}, [cov_trend])
        ids = [i.id for i in insights]
        assert "low_coverage" not in ids, (
            "KILL-L246: coverage=80 不应触发 < 80，若 < 改为 <= 会误报"
        )

    def test_coverage_81_no_low_coverage(self):
        """coverage=81 > 80 不生成"""
        cov_trend = MetricTrend(
            MetricCategory.COVERAGE, 81.0, 80.0, TrendDirection.UP, 1.25,
        )
        insights = self.analyzer._generate_insights({}, [cov_trend])
        assert "low_coverage" not in [i.id for i in insights]

    # ---- L258 replace_comparison: RESPONSE_TIME DOWN (inverse=变差) ----
    def test_response_time_down_generates_increase_insight(self):
        """L258 compare: RESPONSE_TIME DOWN(=增加) 生成 response_time_increase"""
        resp_trend = MetricTrend(
            MetricCategory.RESPONSE_TIME, 300.0, 100.0,
            TrendDirection.DOWN, 200.0,  # inverse=True: +200% → DOWN(变差)
        )
        insights = self.analyzer._generate_insights({}, [resp_trend])
        ids = [i.id for i in insights]
        assert "response_time_increase" in ids, (
            "KILL-L258: RESPONSE_TIME DOWN(=增加) 必须生成 response_time_increase"
        )
        inc = next(i for i in insights if i.id == "response_time_increase")
        assert inc.severity == "medium"
        assert inc.confidence == 0.8
        assert "200.00%" in inc.description

    def test_response_time_up_no_increase_insight(self):
        """RESPONSE_TIME UP(=减少) 不生成 increase 告警"""
        resp_trend = MetricTrend(
            MetricCategory.RESPONSE_TIME, 50.0, 200.0,
            TrendDirection.UP, -75.0,
        )
        insights = self.analyzer._generate_insights({}, [resp_trend])
        assert "response_time_increase" not in [i.id for i in insights]

    # ---- L270 replace_comparison: failure_count > 0 ----
    def test_one_failure_generates_test_failures(self):
        """L270 compare: failed_tests=1 > 0 → 生成且 severity=medium (<=5)"""
        insights = self.analyzer._generate_insights({"failed_tests": 1}, [])
        ids = [i.id for i in insights]
        assert "test_failures" in ids, (
            "KILL-L270: failed_tests=1 > 0 必须生成 test_failures"
        )
        tf = next(i for i in insights if i.id == "test_failures")
        assert tf.severity == "medium"
        assert tf.confidence == 0.95
        assert "1个测试失败" in tf.title
        assert "当前有1个测试用例失败" in tf.description

    def test_six_failures_high_severity(self):
        """failure_count > 5 → high severity"""
        insights = self.analyzer._generate_insights({"failed_tests": 6}, [])
        tf = next(i for i in insights if i.id == "test_failures")
        assert tf.severity == "high"

    def test_zero_failures_no_insight(self):
        """L270 compare 反向: failed_tests=0 不生成"""
        insights = self.analyzer._generate_insights({"failed_tests": 0}, [])
        assert "test_failures" not in [i.id for i in insights], (
            "KILL-L270: failed_tests=0 不应生成；若 >0 改为 >=0 会误报"
        )

    # ---- L282 replace_comparison: kill_rate < 80 ----
    def test_kill_rate_79_generates_low_kill_rate(self):
        """L282 compare: kill_rate=79 < 80 → 生成 low_kill_rate"""
        insights = self.analyzer._generate_insights({"kill_rate": 79}, [])
        ids = [i.id for i in insights]
        assert "low_kill_rate" in ids, (
            "KILL-L282: kill_rate=79 < 80 必须生成 low_kill_rate"
        )
        kr = next(i for i in insights if i.id == "low_kill_rate")
        assert kr.severity == "medium"
        assert kr.confidence == 0.8
        assert "79%" in kr.description

    def test_kill_rate_exactly_80_no_insight(self):
        """L282 compare 边界: kill_rate=80 不触发 (< 不含等于)"""
        insights = self.analyzer._generate_insights({"kill_rate": 80}, [])
        assert "low_kill_rate" not in [i.id for i in insights], (
            "KILL-L282: kill_rate=80 不应触发 < 80；若 < 改为 <= 会误报"
        )

    def test_kill_rate_81_no_insight(self):
        """kill_rate=81 不生成"""
        insights = self.analyzer._generate_insights({"kill_rate": 81}, [])
        assert "low_kill_rate" not in [i.id for i in insights]

    def test_no_kill_rate_key_default_zero_generates_insight(self):
        """未传 kill_rate 时 .get(kill_rate, 0) → 0 < 80 必然生成"""
        insights = self.analyzer._generate_insights({}, [])
        assert "low_kill_rate" in [i.id for i in insights]


# =============================================================================
# _generate_summary 数值与健康度计算（Mutations L300, L302, L312）
# =============================================================================
class TestGenerateSummary:
    def setup_method(self):
        self.analyzer = ResultAnalyzer(llm_api_key=None)

    # ---- L300 replace_comparison: total_tests > 0 ----
    def test_total_tests_zero_pass_rate_zero(self):
        """L300 compare: total_tests=0 → pass_rate=0% (不做除法)"""
        summary = self.analyzer._generate_summary(
            {"total_tests": 0, "passed_tests": 0, "failed_tests": 0}, [],
        )
        assert summary["total_tests"] == 0
        assert summary["passed_tests"] == 0
        assert summary["failed_tests"] == 0
        assert summary["pass_rate"] == "0.00%", (
            "KILL-L300: total_tests=0 必须 pass_rate=0.00%；若 >0 改为 >=0 会除零"
        )

    def test_total_tests_positive_exact_pass_rate_calculation(self):
        """L300 + 除法正确性: 80 passed / 100 total *100 = 80.00%"""
        summary = self.analyzer._generate_summary(
            {"total_tests": 100, "passed_tests": 80, "failed_tests": 20}, [],
        )
        assert summary["pass_rate"] == "80.00%", (
            "80/100*100 = 80.00%；算术变异会改变此值"
        )
        assert summary["total_tests"] == 100
        assert summary["passed_tests"] == 80
        assert summary["failed_tests"] == 20

    def test_33_passed_77_total_exact_percent(self):
        """浮点精度: 33/77*100 = 42.857142... → "42.86%" (两位小数四舍五入)"""
        summary = self.analyzer._generate_summary(
            {"total_tests": 77, "passed_tests": 33, "failed_tests": 44}, [],
        )
        assert summary["pass_rate"] == f"{(33/77*100):.2f}%"

    # ---- L302 replace_comparison: direction == TrendDirection.UP ----
    def test_improving_and_declining_counts_match_directions(self):
        """L302: 精确统计 improving 和 declining 数量"""
        # 2 UP, 1 DOWN, 1 STABLE
        trends = [
            MetricTrend(MetricCategory.PASS_RATE, 95, 90, TrendDirection.UP, 5.5),
            MetricTrend(MetricCategory.COVERAGE, 85, 80, TrendDirection.UP, 6.25),
            MetricTrend(MetricCategory.RESPONSE_TIME, 200, 100, TrendDirection.DOWN, 100),
            MetricTrend(MetricCategory.DEFECT_DENSITY, 5, 5, TrendDirection.STABLE, 0),
        ]
        summary = self.analyzer._generate_summary(
            {"total_tests": 10, "passed_tests": 10, "failed_tests": 0}, trends,
        )
        assert summary["improving_metrics"] == 2, (
            "KILL-L302: 2 个 UP 趋势必须 improving_metrics=2"
        )
        assert summary["declining_metrics"] == 1, (
            "1 个 DOWN 趋势必须 declining_metrics=1"
        )

    def test_zero_improving_zero_declining(self):
        """L302 反向: 全 STABLE → 0/0"""
        trends = [
            MetricTrend(MetricCategory.PASS_RATE, 95, 95, TrendDirection.STABLE, 0),
            MetricTrend(MetricCategory.COVERAGE, 85, 85, TrendDirection.STABLE, 0),
        ]
        summary = self.analyzer._generate_summary(
            {"total_tests": 0, "passed_tests": 0, "failed_tests": 0}, trends,
        )
        assert summary["improving_metrics"] == 0
        assert summary["declining_metrics"] == 0

    # ---- L312 replace_comparison: overall_health 三档阈值 ----
    def test_health_healthy_pass_95_and_no_decline(self):
        """L312: pass_rate=95 ≥90 且 declining=0 → healthy"""
        trends = [
            MetricTrend(MetricCategory.PASS_RATE, 95, 90, TrendDirection.UP, 5.5),
        ]
        summary = self.analyzer._generate_summary(
            {"total_tests": 100, "passed_tests": 95, "failed_tests": 5}, trends,
        )
        assert summary["overall_health"] == "healthy", (
            "KILL-L312: 95% pass rate + 0 decline → healthy"
        )

    def test_health_degraded_pass_95_but_has_decline(self):
        """L312: pass_rate=95 ≥90 但 declining>0 → degraded (不满足 healthy 的第二个条件)"""
        trends = [
            MetricTrend(MetricCategory.PASS_RATE, 95, 90, TrendDirection.UP, 5.5),
            MetricTrend(MetricCategory.COVERAGE, 80, 90, TrendDirection.DOWN, -11.1),
        ]
        summary = self.analyzer._generate_summary(
            {"total_tests": 100, "passed_tests": 95, "failed_tests": 5}, trends,
        )
        assert summary["overall_health"] == "degraded", (
            "KILL-L312: declining=1 即使 pass_rate≥90 也必须 degraded (非 healthy)"
        )

    def test_health_degraded_exactly_70_pass(self):
        """L312: pass_rate=70.00%，≥70 且 <90 → degraded"""
        summary = self.analyzer._generate_summary(
            {"total_tests": 100, "passed_tests": 70, "failed_tests": 30}, [],
        )
        assert summary["overall_health"] == "degraded", (
            "KILL-L312: pass_rate 恰好 70% (>=70, <90) → degraded"
        )

    def test_health_unhealthy_pass_69_99(self):
        """L312: pass_rate=69.99% < 70 → unhealthy"""
        # passed=6999, total=10000 → 69.99%
        summary = self.analyzer._generate_summary(
            {"total_tests": 10000, "passed_tests": 6999, "failed_tests": 3001}, [],
        )
        assert summary["overall_health"] == "unhealthy", (
            "KILL-L312: pass_rate < 70 必须 unhealthy；若 >=70 改为 >70 会误判为 degraded"
        )

    def test_health_unhealthy_zero_pass_rate(self):
        """pass_rate=0% → unhealthy"""
        summary = self.analyzer._generate_summary(
            {"total_tests": 100, "passed_tests": 0, "failed_tests": 100}, [],
        )
        assert summary["overall_health"] == "unhealthy"


# =============================================================================
# 依赖场景：LLM vs fallback 模式切换 + analyze() 顶层入口覆盖
# =============================================================================
class TestAnalyzeTopLevelModes:
    def test_no_api_key_uses_fallback_directly(self):
        """无 API key → use_fallback=True → analyze 直接走 _analyze_fallback"""
        # 确保环境变量也没
        with patch.dict("os.environ", {}, clear=True):
            analyzer = ResultAnalyzer()
        assert analyzer.use_fallback is True
        result = analyzer.analyze(
            {"pass_rate": 95.0, "coverage": 90.0,
             "avg_response_time_ms": 150, "defect_count": 2,
             "failed_tests": 0, "kill_rate": 85,
             "total_tests": 100, "passed_tests": 95},
            None,
        )
        assert result.success is True
        assert result.fallback_used is True
        # 应有 4 个趋势
        assert len(result.trends) == 4
        # summary 必须包含字段
        for key in ["total_tests", "passed_tests", "failed_tests",
                    "pass_rate", "improving_metrics", "declining_metrics",
                    "overall_health"]:
            assert key in result.summary, f"summary 缺少关键字段 {key}"

    def test_valid_key_uses_llm_then_fallback_on_exception(self):
        """有 API key → 走 _analyze_with_llm，异常时回退"""
        analyzer = ResultAnalyzer(llm_api_key="key-exists")
        assert analyzer.use_fallback is False

        # 让 LLM 抛出异常
        with patch.object(analyzer, "_analyze_with_llm", side_effect=Exception("boom")):
            result = analyzer.analyze({"pass_rate": 50}, None)

        assert result.success is False
        assert result.fallback_used is True
        assert "boom" in result.error_message
        # 即便失败，也应包含 fallback 的 4 个趋势回填
        assert len(result.trends) == 4


# =============================================================================
# 原始测试用例保留（LLM 异常日志捕获）—— 增强断言强度
# =============================================================================
class TestResultAnalyzerNoLogging:
    def test_analyze_with_llm_logs_error(self):
        analyzer = ResultAnalyzer(llm_api_key="test_key")

        log_capture = []

        def capture_log(*args, **kwargs):
            log_capture.append(args[0] if args else "")

        mock_client = MagicMock()
        # 这里让 client.chat.completions.create 抛异常
        mock_client.chat.completions.create.side_effect = Exception("API connection failed")
        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = mock_client

        with patch.dict(sys.modules, {"openai": fake_openai}):
            with patch.object(analyzer.logger, "error", side_effect=capture_log):
                with pytest.raises(Exception):
                    analyzer._analyze_with_llm({"pass_rate": 80}, None)

                assert len(log_capture) > 0, (
                    "Expected at least one error log when LLM analysis fails"
                )
                assert "LLM analysis failed" in log_capture[0], (
                    f"Expected 'LLM analysis failed' in log, got: {log_capture[0]}"
                )
                # 必须包含异常具体信息
                assert "API connection failed" in log_capture[0], (
                    "日志必须包含原始异常 message: API connection failed"
                )
