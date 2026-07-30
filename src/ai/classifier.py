import os
import json
import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class TestResultCategory(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"
    TIMEOUT = "timeout"


class DefectCategory(str, Enum):
    LOGIC_ERROR = "logic_error"
    PERFORMANCE = "performance"
    SECURITY = "security"
    COMPATIBILITY = "compatibility"
    USABILITY = "usability"
    DATA_INTEGRITY = "data_integrity"
    CONFIGURATION = "configuration"
    INFRASTRUCTURE = "infrastructure"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ClassificationResult:
    category: DefectCategory
    severity: Severity
    confidence: float
    keywords: List[str] = field(default_factory=list)
    explanation: str = ""
    suggested_actions: List[str] = field(default_factory=list)
    classified_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "keywords": self.keywords,
            "explanation": self.explanation,
            "suggested_actions": self.suggested_actions,
            "classified_at": self.classified_at.isoformat(),
        }


@dataclass
class TestResultClassification:
    result_category: TestResultCategory
    defect_category: Optional[DefectCategory] = None
    severity: Optional[Severity] = None
    confidence: float = 0.0
    error_pattern: Optional[str] = None
    affected_components: List[str] = field(default_factory=list)
    classified_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_category": self.result_category.value,
            "defect_category": self.defect_category.value if self.defect_category else None,
            "severity": self.severity.value if self.severity else None,
            "confidence": self.confidence,
            "error_pattern": self.error_pattern,
            "affected_components": self.affected_components,
            "classified_at": self.classified_at.isoformat(),
        }


class AITextClassifier:
    def __init__(self, llm_api_key: Optional[str] = None):
        self.llm_api_key = llm_api_key or os.environ.get("OPENAI_API_KEY")
        self.use_fallback = not self.llm_api_key
        self.logger = logging.getLogger(__name__)
        self._load_patterns()

    def _load_patterns(self):
        self.error_patterns = {
            DefectCategory.LOGIC_ERROR: [
                r"(AssertionError|Assertion Failed)",
                r"(KeyError|IndexError|ValueError)",
                r"(AttributeError|TypeError)",
                r"(NameError|UnboundLocalError)",
                r"(ZeroDivisionError|FloatingPointError)",
                r"(logic error|incorrect result|wrong value)",
                r"(条件.*错误|逻辑.*错误)",
            ],
            DefectCategory.PERFORMANCE: [
                r"(Timeout|timeout exceeded)",
                r"(slow|slowdown|performance issue)",
                r"(latency|response time)",
                r"(memory leak|memory error)",
                r"(CPU|cpu usage|high load)",
                r"(超时|性能.*问题|响应.*慢)",
            ],
            DefectCategory.SECURITY: [
                r"(security|vulnerability|exploit)",
                r"(SQL.*injection|XSS|cross.*site)",
                r"(CSRF|csrf|clickjacking)",
                r"(password|credential|secret)",
                r"(unauthorized|forbidden|access denied)",
                r"(安全|漏洞|注入|攻击)",
            ],
            DefectCategory.COMPATIBILITY: [
                r"(compatibility|version.*issue)",
                r"(deprecat|deprecated)",
                r"(incompatible|not compatible)",
                r"(browser.*issue|platform.*issue)",
                r"(兼容.*问题|版本.*冲突)",
            ],
            DefectCategory.DATA_INTEGRITY: [
                r"(database|db error|sql error)",
                r"(data.*corrupt|corrupted)",
                r"(constraint.*violation|unique.*constraint)",
                r"(foreign.*key|referential.*integrity)",
                r"(数据.*错误|数据库.*问题)",
            ],
            DefectCategory.CONFIGURATION: [
                r"(config.*error|configuration.*issue)",
                r"(missing.*config|invalid.*config)",
                r"(environment.*variable|env.*var)",
                r"(setting.*error|parameter.*error)",
                r"(配置.*错误|环境.*变量)",
            ],
            DefectCategory.INFRASTRUCTURE: [
                r"(connection.*error|connect.*failed)",
                r"(network.*error|socket.*error)",
                r"(server.*down|service.*unavailable)",
                r"(port.*error|bind.*error)",
                r"(连接.*错误|网络.*问题|服务.*不可用)",
            ],
        }

        self.severity_patterns = {
            Severity.CRITICAL: [
                r"(critical|fatal|crash|panic)",
                r"(数据丢失|系统崩溃|核心.*错误)",
            ],
            Severity.HIGH: [
                r"(high.*severity|major.*issue)",
                r"(安全.*漏洞|认证.*失败)",
            ],
            Severity.MEDIUM: [
                r"(medium.*severity|minor.*issue)",
                r"(性能.*问题|兼容性.*问题)",
            ],
            Severity.LOW: [
                r"(low.*severity|info.*message)",
                r"(警告|提示|建议)",
            ],
        }

    def classify(self, text: str) -> ClassificationResult:
        if self.use_fallback:
            return self._classify_fallback(text)

        try:
            return self._classify_with_llm(text)
        except Exception as e:
            self.logger.warning(f"LLM classification failed: {e}, falling back to pattern matching")
            return self._classify_fallback(text)

    def classify_test_result(self, test_result: Dict[str, Any]) -> TestResultClassification:
        status = test_result.get("status", "").lower()
        error_message = test_result.get("error_message", "")
        stack_trace = test_result.get("stack_trace", "")
        test_name = test_result.get("test_name", "")

        full_text = f"{status} {error_message} {stack_trace} {test_name}"

        if status == "passed":
            return TestResultClassification(
                result_category=TestResultCategory.PASS,
                confidence=1.0,
            )
        elif status == "failed":
            defect_class = self.classify(full_text)
            return TestResultClassification(
                result_category=TestResultCategory.FAIL,
                defect_category=defect_class.category,
                severity=defect_class.severity,
                confidence=defect_class.confidence,
                affected_components=self._extract_components(stack_trace),
            )
        elif status == "error":
            defect_class = self.classify(full_text)
            return TestResultClassification(
                result_category=TestResultCategory.ERROR,
                defect_category=defect_class.category,
                severity=defect_class.severity,
                confidence=defect_class.confidence,
                affected_components=self._extract_components(stack_trace),
            )
        elif status == "skipped":
            return TestResultClassification(
                result_category=TestResultCategory.SKIP,
                confidence=0.9,
            )
        elif "timeout" in full_text.lower():
            return TestResultClassification(
                result_category=TestResultCategory.TIMEOUT,
                defect_category=DefectCategory.PERFORMANCE,
                severity=Severity.HIGH,
                confidence=0.95,
                affected_components=self._extract_components(stack_trace),
            )
        else:
            return TestResultClassification(
                result_category=TestResultCategory.FAIL,
                defect_category=DefectCategory.LOGIC_ERROR,
                severity=Severity.MEDIUM,
                confidence=0.5,
            )

    def _classify_with_llm(self, text: str) -> ClassificationResult:
        prompt = self._build_classification_prompt(text)

        try:
            import openai
            client = openai.OpenAI(api_key=self.llm_api_key)

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的缺陷分类专家。请根据文本内容分类缺陷类型和严重程度。",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )

            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM response content is None")
            result = json.loads(content)
            return self._parse_llm_classification(result)

        except Exception as e:
            self.logger.error(f"LLM classification error: {e}")
            raise

    def _classify_fallback(self, text: str) -> ClassificationResult:
        text_lower = text.lower()

        category = self._match_category(text_lower)
        severity = self._match_severity(text_lower)
        keywords = self._extract_keywords(text)

        confidence = self._calculate_confidence(text_lower, category)
        explanation = self._generate_explanation(category, severity, keywords)
        suggested_actions = self._generate_suggested_actions(category)

        return ClassificationResult(
            category=category,
            severity=severity,
            confidence=confidence,
            keywords=keywords,
            explanation=explanation,
            suggested_actions=suggested_actions,
        )

    def _build_classification_prompt(self, text: str) -> str:
        categories = ", ".join([c.value for c in DefectCategory])
        severities = ", ".join([s.value for s in Severity])

        return f"""
请对以下文本进行缺陷分类：

文本内容：
{text}

请选择最匹配的类别（{categories}）和严重程度（{severities}）。

请以JSON格式输出：
- category: 缺陷类别
- severity: 严重程度
- confidence: 0-1的置信度
- keywords: 提取的关键词列表
- explanation: 分类说明
- suggested_actions: 建议的处理措施列表
"""

    def _parse_llm_classification(self, result: Dict[str, Any]) -> ClassificationResult:
        try:
            category = DefectCategory(result.get("category", "logic_error"))
        except ValueError:
            category = DefectCategory.LOGIC_ERROR

        try:
            severity = Severity(result.get("severity", "medium"))
        except ValueError:
            severity = Severity.MEDIUM

        return ClassificationResult(
            category=category,
            severity=severity,
            confidence=float(result.get("confidence", 0.5)),
            keywords=list(result.get("keywords", [])),
            explanation=str(result.get("explanation", "")),
            suggested_actions=list(result.get("suggested_actions", [])),
        )

    def _match_category(self, text: str) -> DefectCategory:
        for category, patterns in self.error_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return category
        return DefectCategory.LOGIC_ERROR

    def _match_severity(self, text: str) -> Severity:
        for severity, patterns in self.severity_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return severity
        return Severity.MEDIUM

    def _extract_keywords(self, text: str) -> List[str]:
        keywords = []
        category_keywords = {
            "logic": ["logic", "error", "assert", "failed", "wrong", "incorrect"],
            "performance": ["slow", "timeout", "latency", "performance", "memory", "cpu"],
            "security": ["security", "vulnerability", "attack", "password", "secret"],
            "data": ["database", "sql", "data", "integrity", "constraint"],
            "config": ["config", "configuration", "setting", "env", "parameter"],
        }

        text_lower = text.lower()
        for category, words in category_keywords.items():
            for word in words:
                if word in text_lower and word not in keywords:
                    keywords.append(word)

        return keywords[:5]

    def _extract_components(self, stack_trace: str) -> List[str]:
        components = []
        module_pattern = r"File \"([^\"]+[/\\]src[/\\][^\"]+)\.py\""
        matches = re.findall(module_pattern, stack_trace)

        for match in matches:
            parts = match.split("/")
            if len(parts) >= 2:
                component = parts[-2]
                if component not in components:
                    components.append(component)

        return components[:3]

    def _calculate_confidence(self, text: str, category: DefectCategory) -> float:
        matched_patterns = 0
        total_patterns = len(self.error_patterns[category])

        for pattern in self.error_patterns[category]:
            if re.search(pattern, text, re.IGNORECASE):
                matched_patterns += 1

        if total_patterns == 0:
            return 0.5

        base_confidence = matched_patterns / total_patterns
        length_bonus = min(len(text) / 500, 0.3)

        return min(1.0, base_confidence + length_bonus)

    def _generate_explanation(self, category: DefectCategory, severity: Severity, keywords: List[str]) -> str:
        explanations = {
            DefectCategory.LOGIC_ERROR: "检测到逻辑错误",
            DefectCategory.PERFORMANCE: "检测到性能问题",
            DefectCategory.SECURITY: "检测到安全问题",
            DefectCategory.COMPATIBILITY: "检测到兼容性问题",
            DefectCategory.DATA_INTEGRITY: "检测到数据完整性问题",
            DefectCategory.CONFIGURATION: "检测到配置问题",
            DefectCategory.INFRASTRUCTURE: "检测到基础设施问题",
        }

        severity_descriptions = {
            Severity.CRITICAL: "严重程度为CRITICAL",
            Severity.HIGH: "严重程度为HIGH",
            Severity.MEDIUM: "严重程度为MEDIUM",
            Severity.LOW: "严重程度为LOW",
        }

        parts = [explanations.get(category, "检测到问题")]
        if severity:
            parts.append(severity_descriptions.get(severity, ""))
        if keywords:
            parts.append(f"关键词: {', '.join(keywords)}")

        return "; ".join(filter(None, parts))

    def _generate_suggested_actions(self, category: DefectCategory) -> List[str]:
        actions = {
            DefectCategory.LOGIC_ERROR: [
                "检查代码逻辑，定位问题根源",
                "添加针对性的单元测试",
                "修复后重新运行测试",
            ],
            DefectCategory.PERFORMANCE: [
                "分析性能瓶颈，使用性能分析工具",
                "优化慢查询或算法",
                "考虑引入缓存机制",
            ],
            DefectCategory.SECURITY: [
                "立即修复安全漏洞",
                "进行安全审查",
                "添加安全测试用例",
            ],
            DefectCategory.COMPATIBILITY: [
                "检查版本兼容性",
                "更新依赖库",
                "添加兼容性测试",
            ],
            DefectCategory.DATA_INTEGRITY: [
                "检查数据库约束",
                "验证数据一致性",
                "添加数据验证逻辑",
            ],
            DefectCategory.CONFIGURATION: [
                "检查配置文件",
                "验证环境变量",
                "添加配置验证",
            ],
            DefectCategory.INFRASTRUCTURE: [
                "检查网络连接",
                "验证服务状态",
                "添加健康检查",
            ],
        }

        return actions.get(category, ["分析问题，制定修复方案"])