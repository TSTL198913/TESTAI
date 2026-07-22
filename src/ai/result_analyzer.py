import os
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class MetricCategory(str, Enum):
    PASS_RATE = "pass_rate"  # nosec B105
    COVERAGE = "coverage"
    RESPONSE_TIME = "response_time"
    DEFECT_DENSITY = "defect_density"
    EXECUTION_TIME = "execution_time"


@dataclass
class MetricTrend:
    category: MetricCategory
    current_value: float
    previous_value: float
    direction: TrendDirection
    change_percent: float
    threshold: float = 0.0


@dataclass
class AnalysisInsight:
    id: str
    title: str
    description: str
    severity: str
    recommendation: str
    confidence: float = 0.0
    related_metrics: List[str] = field(default_factory=list)


@dataclass
class ResultAnalysis:
    success: bool
    insights: List[AnalysisInsight] = field(default_factory=list)
    trends: List[MetricTrend] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    fallback_used: bool = False


class ResultAnalyzer:
    def __init__(self, llm_api_key: Optional[str] = None):
        self.llm_api_key = llm_api_key or os.environ.get("OPENAI_API_KEY")
        self.use_fallback = not self.llm_api_key

    def analyze(self, current_results: Dict[str, Any], previous_results: Optional[Dict[str, Any]] = None) -> ResultAnalysis:
        if self.use_fallback:
            return self._analyze_fallback(current_results, previous_results)
        
        try:
            return self._analyze_with_llm(current_results, previous_results)
        except Exception as e:
            return ResultAnalysis(
                success=False,
                error_message=f"LLM analysis failed: {str(e)}",
                fallback_used=True,
                insights=self._analyze_fallback(current_results, previous_results).insights,
                trends=self._analyze_fallback(current_results, previous_results).trends,
            )

    def _analyze_with_llm(self, current_results: Dict[str, Any], previous_results: Optional[Dict[str, Any]]) -> ResultAnalysis:
        prompt = self._build_analysis_prompt(current_results, previous_results)
        
        try:
            import openai
            client = openai.OpenAI(api_key=self.llm_api_key)
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "你是一个专业的测试结果分析专家，能够分析测试结果趋势并提供有价值的洞察。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            
            result = json.loads(response.choices[0].message.content)
            return self._parse_llm_result(result)
            
        except Exception as e:
            raise e

    def _analyze_fallback(self, current_results: Dict[str, Any], previous_results: Optional[Dict[str, Any]]) -> ResultAnalysis:
        trends = self._calculate_trends(current_results, previous_results)
        insights = self._generate_insights(current_results, trends)
        summary = self._generate_summary(current_results, trends)
        
        return ResultAnalysis(
            success=True,
            insights=insights,
            trends=trends,
            summary=summary,
            fallback_used=True,
        )

    def _build_analysis_prompt(self, current_results: Dict[str, Any], previous_results: Optional[Dict[str, Any]]) -> str:
        return f"""
分析以下测试结果数据：

当前结果：{json.dumps(current_results, indent=2, ensure_ascii=False)}

历史结果：{json.dumps(previous_results or {}, indent=2, ensure_ascii=False)}

请提供：
1. 关键指标趋势分析（通过率、覆盖率、响应时间、缺陷密度）
2. 有价值的洞察和建议
3. 需要关注的问题
4. 改进建议

以JSON格式输出：
- insights: 洞察列表
  - id: 唯一标识
  - title: 标题
  - description: 描述
  - severity: high/medium/low
  - recommendation: 建议
  - confidence: 置信度(0-1)
- trends: 趋势列表
  - category: pass_rate/coverage/response_time/defect_density/execution_time
  - current_value: 当前值
  - previous_value: 历史值
  - direction: up/down/stable
  - change_percent: 变化百分比
- summary: 摘要信息
"""

    def _parse_llm_result(self, result: Dict[str, Any]) -> ResultAnalysis:
        insights = []
        for insight_data in result.get("insights", []):
            insight = AnalysisInsight(
                id=insight_data.get("id", ""),
                title=insight_data.get("title", ""),
                description=insight_data.get("description", ""),
                severity=insight_data.get("severity", "medium"),
                recommendation=insight_data.get("recommendation", ""),
                confidence=insight_data.get("confidence", 0.0),
                related_metrics=insight_data.get("related_metrics", []),
            )
            insights.append(insight)
        
        trends = []
        for trend_data in result.get("trends", []):
            trend = MetricTrend(
                category=MetricCategory(trend_data.get("category", "pass_rate")),
                current_value=trend_data.get("current_value", 0.0),
                previous_value=trend_data.get("previous_value", 0.0),
                direction=TrendDirection(trend_data.get("direction", "stable")),
                change_percent=trend_data.get("change_percent", 0.0),
            )
            trends.append(trend)
        
        return ResultAnalysis(
            success=True,
            insights=insights,
            trends=trends,
            summary=result.get("summary", {}),
        )

    def _calculate_trends(self, current: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> List[MetricTrend]:
        trends = []
        
        current_pass_rate = current.get("pass_rate", 0.0)
        prev_pass_rate = previous.get("pass_rate", 0.0) if previous else 0.0
        trends.append(self._create_trend(MetricCategory.PASS_RATE, current_pass_rate, prev_pass_rate))
        
        current_coverage = current.get("coverage", 0.0)
        prev_coverage = previous.get("coverage", 0.0) if previous else 0.0
        trends.append(self._create_trend(MetricCategory.COVERAGE, current_coverage, prev_coverage))
        
        current_response_time = current.get("avg_response_time_ms", 0.0)
        prev_response_time = previous.get("avg_response_time_ms", 0.0) if previous else 0.0
        trends.append(self._create_trend(MetricCategory.RESPONSE_TIME, current_response_time, prev_response_time, inverse=True))
        
        current_defects = current.get("defect_count", 0)
        prev_defects = previous.get("defect_count", 0) if previous else 0
        trends.append(self._create_trend(MetricCategory.DEFECT_DENSITY, current_defects, prev_defects, inverse=True))
        
        return trends

    def _create_trend(self, category: MetricCategory, current: float, previous: float, inverse: bool = False) -> MetricTrend:
        if previous == 0:
            change_percent = 0.0
            direction = TrendDirection.STABLE
        else:
            change_percent = ((current - previous) / previous) * 100
            
            if inverse:
                if change_percent > 5:
                    direction = TrendDirection.DOWN
                elif change_percent < -5:
                    direction = TrendDirection.UP
                else:
                    direction = TrendDirection.STABLE
            else:
                if change_percent > 5:
                    direction = TrendDirection.UP
                elif change_percent < -5:
                    direction = TrendDirection.DOWN
                else:
                    direction = TrendDirection.STABLE
        
        return MetricTrend(
            category=category,
            current_value=current,
            previous_value=previous,
            direction=direction,
            change_percent=change_percent,
        )

    def _generate_insights(self, results: Dict[str, Any], trends: List[MetricTrend]) -> List[AnalysisInsight]:
        insights = []
        
        pass_rate_trend = next((t for t in trends if t.category == MetricCategory.PASS_RATE), None)
        if pass_rate_trend and pass_rate_trend.direction == TrendDirection.DOWN:
            insights.append(AnalysisInsight(
                id="pass_rate_drop",
                title="测试通过率下降",
                description=f"测试通过率从{pass_rate_trend.previous_value:.2f}%下降到{pass_rate_trend.current_value:.2f}%",
                severity="high",
                recommendation="检查最近的代码变更，分析失败的测试用例，修复引入的回归问题",
                confidence=0.9,
                related_metrics=["pass_rate"],
            ))
        
        coverage_trend = next((t for t in trends if t.category == MetricCategory.COVERAGE), None)
        if coverage_trend and coverage_trend.current_value < 80:
            insights.append(AnalysisInsight(
                id="low_coverage",
                title="测试覆盖率不足",
                description=f"当前测试覆盖率为{coverage_trend.current_value:.2f}%，低于80%的目标",
                severity="medium",
                recommendation="增加单元测试和集成测试，重点覆盖未覆盖的代码路径",
                confidence=0.85,
                related_metrics=["coverage"],
            ))
        
        response_trend = next((t for t in trends if t.category == MetricCategory.RESPONSE_TIME), None)
        if response_trend and response_trend.direction == TrendDirection.DOWN:
            insights.append(AnalysisInsight(
                id="response_time_increase",
                title="响应时间增加",
                description=f"平均响应时间增加了{response_trend.change_percent:.2f}%",
                severity="medium",
                recommendation="分析性能瓶颈，优化慢接口，考虑添加缓存或异步处理",
                confidence=0.8,
                related_metrics=["response_time"],
            ))
        
        failure_count = results.get("failed_tests", 0)
        if failure_count > 0:
            insights.append(AnalysisInsight(
                id="test_failures",
                title=f"{failure_count}个测试失败",
                description=f"当前有{failure_count}个测试用例失败，需要关注",
                severity="high" if failure_count > 5 else "medium",
                recommendation="优先修复失败的测试用例，确保主分支质量",
                confidence=0.95,
                related_metrics=["failed_tests"],
            ))
        
        kill_rate = results.get("kill_rate", 0)
        if kill_rate < 80:
            insights.append(AnalysisInsight(
                id="low_kill_rate",
                title="变异测试Kill Rate不足",
                description=f"当前Kill Rate为{kill_rate}%，低于80%的目标",
                severity="medium",
                recommendation="增强测试用例的断言强度，覆盖更多边界条件和异常场景",
                confidence=0.8,
                related_metrics=["kill_rate"],
            ))
        
        return insights

    def _generate_summary(self, results: Dict[str, Any], trends: List[MetricTrend]) -> Dict[str, Any]:
        total_tests = results.get("total_tests", 0)
        passed_tests = results.get("passed_tests", 0)
        failed_tests = results.get("failed_tests", 0)
        
        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        improving_trends = sum(1 for t in trends if t.direction == TrendDirection.UP)
        declining_trends = sum(1 for t in trends if t.direction == TrendDirection.DOWN)
        
        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "pass_rate": f"{pass_rate:.2f}%",
            "improving_metrics": improving_trends,
            "declining_metrics": declining_trends,
            "overall_health": "healthy" if pass_rate >= 90 and declining_trends == 0 else "degraded" if pass_rate >= 70 else "unhealthy",
        }