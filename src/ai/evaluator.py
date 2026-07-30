import os
import json
import logging
import difflib
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class EvaluationGrade(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


@dataclass
class EvaluationResult:
    grade: EvaluationGrade
    score: float
    matches_expected: bool
    similarity: float
    correctness: float
    completeness: float
    confidence: float
    explanation: str = ""
    discrepancies: Dict[str, Any] = field(default_factory=dict)
    suggestions: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "grade": self.grade.value,
            "score": self.score,
            "matches_expected": self.matches_expected,
            "similarity": self.similarity,
            "correctness": self.correctness,
            "completeness": self.completeness,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "discrepancies": self.discrepancies,
            "suggestions": self.suggestions,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


class AIEvaluator:
    def __init__(self, llm_api_key: Optional[str] = None):
        self.llm_api_key = llm_api_key or os.environ.get("OPENAI_API_KEY")
        self.use_fallback = not self.llm_api_key
        self.logger = logging.getLogger(__name__)

    def evaluate(self, output: str, expected: str) -> EvaluationResult:
        if self.use_fallback:
            return self._evaluate_fallback(output, expected)

        try:
            return self._evaluate_with_llm(output, expected)
        except Exception as e:
            self.logger.warning(f"LLM evaluation failed: {e}, falling back to heuristic evaluation")
            return self._evaluate_fallback(output, expected)

    def _evaluate_with_llm(self, output: str, expected: str) -> EvaluationResult:
        prompt = self._build_evaluation_prompt(output, expected)

        try:
            import openai
            client = openai.OpenAI(api_key=self.llm_api_key)

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的测试结果评估专家。请根据预期输出评估实际输出的质量。",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM response content is None")
            result = json.loads(content)
            return self._parse_llm_evaluation(result)

        except Exception as e:
            self.logger.error(f"LLM evaluation error: {e}")
            raise

    def _evaluate_fallback(self, output: str, expected: str) -> EvaluationResult:
        if not output:
            return EvaluationResult(
                grade=EvaluationGrade.POOR,
                score=0.0,
                matches_expected=False,
                similarity=0.0,
                correctness=0.0,
                completeness=0.0,
                confidence=0.9,
                explanation="输出为空",
                suggestions={"improvement": "确保生成有效输出"},
            )

        output_clean = output.strip().lower()
        expected_clean = expected.strip().lower()

        similarity = self._calculate_similarity(output_clean, expected_clean)
        correctness = self._calculate_correctness(output_clean, expected_clean)
        completeness = self._calculate_completeness(output_clean, expected_clean)

        score = (similarity * 0.4 + correctness * 0.3 + completeness * 0.3)
        matches_expected = score >= 0.8
        grade = self._score_to_grade(score)

        explanation = self._generate_explanation(grade, similarity, correctness, completeness)
        discrepancies = self._find_discrepancies(output, expected)
        suggestions = self._generate_suggestions(grade, discrepancies)

        return EvaluationResult(
            grade=grade,
            score=score,
            matches_expected=matches_expected,
            similarity=similarity,
            correctness=correctness,
            completeness=completeness,
            confidence=0.7 + (0.3 * score),
            explanation=explanation,
            discrepancies=discrepancies,
            suggestions=suggestions,
        )

    def _build_evaluation_prompt(self, output: str, expected: str) -> str:
        return f"""
请评估以下实际输出与预期输出的匹配程度：

预期输出：
{expected}

实际输出：
{output}

请从以下维度评估：
1. 正确性（correctness）：实际输出是否符合预期逻辑
2. 完整性（completeness）：实际输出是否包含所有必要信息
3. 相似性（similarity）：实际输出与预期输出的文本相似度

请以JSON格式输出评估结果：
- grade: excellent/good/fair/poor
- score: 0-1的综合评分
- matches_expected: true/false
- similarity: 0-1的相似度评分
- correctness: 0-1的正确性评分
- completeness: 0-1的完整性评分
- confidence: 0-1的置信度
- explanation: 评估说明
- discrepancies: 差异详情（键值对）
- suggestions: 改进建议（键值对）
"""

    def _parse_llm_evaluation(self, result: Dict[str, Any]) -> EvaluationResult:
        try:
            grade = EvaluationGrade(result.get("grade", "fair"))
        except ValueError:
            grade = EvaluationGrade.FAIR

        return EvaluationResult(
            grade=grade,
            score=float(result.get("score", 0.0)),
            matches_expected=bool(result.get("matches_expected", False)),
            similarity=float(result.get("similarity", 0.0)),
            correctness=float(result.get("correctness", 0.0)),
            completeness=float(result.get("completeness", 0.0)),
            confidence=float(result.get("confidence", 0.0)),
            explanation=str(result.get("explanation", "")),
            discrepancies=dict(result.get("discrepancies", {})),
            suggestions=dict(result.get("suggestions", {})),
        )

    def _calculate_similarity(self, output: str, expected: str) -> float:
        if not output or not expected:
            return 0.0

        output_words = set(output.split())
        expected_words = set(expected.split())

        if not expected_words:
            return 1.0 if not output_words else 0.0

        intersection = output_words & expected_words
        union = output_words | expected_words

        if not union:
            return 1.0

        return len(intersection) / len(union)

    def _calculate_correctness(self, output: str, expected: str) -> float:
        if not output or not expected:
            return 0.0

        matcher = difflib.SequenceMatcher(None, output, expected)
        return matcher.ratio()

    def _calculate_completeness(self, output: str, expected: str) -> float:
        if not expected:
            return 1.0 if output else 0.0

        if not output:
            return 0.0

        expected_parts = [p.strip() for p in expected.split(",") if p.strip()]
        output_lower = output.lower()

        matched_parts = sum(1 for part in expected_parts if part.lower() in output_lower)

        return matched_parts / len(expected_parts) if expected_parts else 1.0

    def _score_to_grade(self, score: float) -> EvaluationGrade:
        if score >= 0.9:
            return EvaluationGrade.EXCELLENT
        elif score >= 0.7:
            return EvaluationGrade.GOOD
        elif score >= 0.5:
            return EvaluationGrade.FAIR
        else:
            return EvaluationGrade.POOR

    def _generate_explanation(self, grade: EvaluationGrade, similarity: float, correctness: float, completeness: float) -> str:
        explanations = []
        if similarity >= 0.8:
            explanations.append("内容相似度高")
        elif similarity >= 0.5:
            explanations.append("内容部分匹配")
        else:
            explanations.append("内容差异较大")

        if correctness >= 0.8:
            explanations.append("逻辑正确")
        elif correctness >= 0.5:
            explanations.append("逻辑部分正确")
        else:
            explanations.append("逻辑存在问题")

        if completeness >= 0.8:
            explanations.append("信息完整")
        elif completeness >= 0.5:
            explanations.append("信息基本完整")
        else:
            explanations.append("信息不完整")

        return "; ".join(explanations)

    def _find_discrepancies(self, output: str, expected: str) -> Dict[str, Any]:
        discrepancies = {}

        if output.strip() != expected.strip():
            discrepancies["content_mismatch"] = {
                "expected": expected[:100] + "..." if len(expected) > 100 else expected,
                "actual": output[:100] + "..." if len(output) > 100 else output,
            }

        output_lines = output.strip().split("\n")
        expected_lines = expected.strip().split("\n")

        if len(output_lines) != len(expected_lines):
            discrepancies["line_count_mismatch"] = {
                "expected_lines": len(expected_lines),
                "actual_lines": len(output_lines),
            }

        return discrepancies

    def _generate_suggestions(self, grade: EvaluationGrade, discrepancies: Dict[str, Any]) -> Dict[str, Any]:
        suggestions = {}

        if grade in (EvaluationGrade.FAIR, EvaluationGrade.POOR):
            suggestions["general"] = "建议检查输出逻辑，确保与预期一致"

        if "content_mismatch" in discrepancies:
            suggestions["content"] = "检查输出内容是否与预期匹配"

        if "line_count_mismatch" in discrepancies:
            suggestions["structure"] = "检查输出格式和行数是否正确"

        return suggestions

    def evaluate_test_quality(self, test_case: Dict[str, Any]) -> EvaluationResult:
        expected_output = test_case.get("expected_output", "")
        actual_output = test_case.get("actual_output", "")

        return self.evaluate(actual_output, expected_output)