import pytest
from src.ai.result_analyzer import ResultAnalyzer, MetricTrend, MetricCategory, TrendDirection


class TestResultAnalyzerDivideByZero:
    def test_analyze_with_zero_total_tests(self):
        analyzer = ResultAnalyzer()
        
        current_results = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "pass_rate": 0.0,
            "coverage": 0.0,
            "avg_response_time_ms": 0.0,
            "defect_count": 0,
        }
        
        result = analyzer.analyze(current_results)
        
        assert result.success is True
        assert result.summary["pass_rate"] == "0.00%"
        assert result.summary["total_tests"] == 0
        assert result.summary["passed_tests"] == 0
        assert result.summary["failed_tests"] == 0

    def test_generate_summary_divide_by_zero(self):
        analyzer = ResultAnalyzer()
        
        current_results = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
        }
        
        trends = []
        
        summary = analyzer._generate_summary(current_results, trends)
        
        assert summary["pass_rate"] == "0.00%"
        assert summary["total_tests"] == 0

    def test_calculate_trends_with_zero_previous(self):
        analyzer = ResultAnalyzer()
        
        current_results = {
            "pass_rate": 80.0,
            "coverage": 70.0,
            "avg_response_time_ms": 100.0,
            "defect_count": 5,
        }
        
        previous_results = None
        
        trends = analyzer._calculate_trends(current_results, previous_results)
        
        assert len(trends) == 4
        
        for trend in trends:
            assert trend.change_percent == 0.0
            assert trend.direction == TrendDirection.STABLE

    def test_create_trend_with_zero_previous(self):
        analyzer = ResultAnalyzer()
        
        trend = analyzer._create_trend(MetricCategory.PASS_RATE, 80.0, 0.0)
        
        assert trend.change_percent == 0.0
        assert trend.direction == TrendDirection.STABLE