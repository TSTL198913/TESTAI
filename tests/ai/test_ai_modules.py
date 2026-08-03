"""
P0-AI-TEST: AI 模块真实业务断言测试 (重写版)

覆盖 classifier.py、evaluator.py、qa_engine.py 的核心逻辑。

严格性原则 (经变异测试验证):
- 原版 8 个变异里 7 个逃逸 (除 score=0.0 外), 证明 is not None 是 tautology
- 本版本重写为真实业务断言:
  1. 分类结果必须按 pattern 正确归类 (timeout→PERFORMANCE, password→SECURITY...)
  2. severity 必须按关键词判定 (critical→CRITICAL)
  3. confidence ∈ [0, 1]
  4. evaluator score = similarity*0.4 + correctness*0.3 + completeness*0.3
  5. matches_expected = (score >= 0.8)
  6. 空输出 → grade=POOR, score=0.0
  7. qa_engine 命中知识库 → source=KNOWLEDGE_BASE, references 非空, confidence=MEDIUM/HIGH
"""
import pytest

from src.ai.classifier import (
    AITextClassifier,
    ClassificationResult,
    DefectCategory,
    Severity,
)
from src.ai.evaluator import (
    AIEvaluator,
    EvaluationResult,
    EvaluationGrade,
)
from src.ai.qa_engine import (
    AIQAEngine,
    QAAnswer,
    AnswerSource,
    AnswerConfidence,
)


class TestAITextClassifierBusinessLogic:
    """classifier.classify 必须按 error_patterns 真实匹配 (源码 classifier.py:88-143)。"""

    def setup_method(self):
        # 强制走 fallback (无 OPENAI_API_KEY)
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        self.classifier = AITextClassifier()

    @pytest.mark.parametrize("text,expected_category", [
        ("AssertionError: expected 5 but got 4", DefectCategory.LOGIC_ERROR),
        ("KeyError: 'user_id' not found", DefectCategory.LOGIC_ERROR),
        ("TypeError: unsupported operand", DefectCategory.LOGIC_ERROR),
        ("Timeout exceeded waiting for response", DefectCategory.PERFORMANCE),
        ("slow response time, latency issue", DefectCategory.PERFORMANCE),
        ("memory leak detected", DefectCategory.PERFORMANCE),
        ("SQL injection vulnerability found", DefectCategory.SECURITY),
        ("XSS cross-site scripting attack", DefectCategory.SECURITY),
        ("unauthorized access, forbidden", DefectCategory.SECURITY),
        ("database error, sql error, constraint violation", DefectCategory.DATA_INTEGRITY),
        ("foreign key constraint violated", DefectCategory.DATA_INTEGRITY),
        ("config error, invalid configuration", DefectCategory.CONFIGURATION),
        ("missing environment variable ENV_VAR", DefectCategory.CONFIGURATION),
        ("connection error, connection failed", DefectCategory.INFRASTRUCTURE),
        ("network error, socket error", DefectCategory.INFRASTRUCTURE),
        ("service unavailable, server down", DefectCategory.INFRASTRUCTURE),
    ])
    def test_classify_matches_correct_category(self, text, expected_category):
        """[真实业务] classify 必须按 pattern 真实匹配到正确的 DefectCategory。

        防变异: 如果 _match_category 跳过匹配直接返回 LOGIC_ERROR, 此测试必失败。
        """
        result = self.classifier.classify(text)
        assert isinstance(result, ClassificationResult), \
            f"classify 必须返回 ClassificationResult, 实际: {type(result)}"
        assert result.category == expected_category, (
            f"文本 '{text}' 应分类为 {expected_category.value}, "
            f"实际 {result.category.value} — pattern 匹配逻辑被破坏"
        )

    @pytest.mark.parametrize("text,expected_severity", [
        ("critical error, system crash", Severity.CRITICAL),
        ("fatal error, panic occurred", Severity.CRITICAL),
        ("high severity security vulnerability", Severity.HIGH),
        ("medium severity issue", Severity.MEDIUM),
        ("low severity info message", Severity.LOW),
    ])
    def test_classify_matches_correct_severity(self, text, expected_severity):
        """[真实业务] severity 必须按 severity_patterns 真实匹配。

        防变异: 如果 _match_severity 永远返回 LOW/CRITICAL, 此测试必失败。
        """
        result = self.classifier.classify(text)
        assert result.severity == expected_severity, (
            f"文本 '{text}' 应判定 severity={expected_severity.value}, "
            f"实际 {result.severity.value} — severity 匹配逻辑被破坏"
        )

    def test_classify_confidence_in_valid_range(self):
        """[真实业务] confidence ∈ [0, 1]。"""
        for text in ["timeout", "critical crash", "unknown gibberish xyz123", ""]:
            result = self.classifier.classify(text)
            assert 0.0 <= result.confidence <= 1.0, (
                f"confidence 越界: {result.confidence} (text='{text}')"
            )

    def test_classify_confidence_positive_when_pattern_matched(self):
        """[真实业务] 匹配 pattern 的文本, confidence 必须 > 0 (源码 _calculate_confidence)。

        防变异 C3: confidence 永远 0.0 → 此测试必失败。
        源码公式: base_confidence = matched_patterns/total_patterns + length_bonus。
        只要有1个 pattern 匹配, base > 0; length_bonus = min(len/500, 0.3) >= 0。
        所以匹配后 confidence > 0。
        """
        # 这些文本明确匹配各自 category 的 pattern
        matched_cases = [
            ("Timeout exceeded", DefectCategory.PERFORMANCE),
            ("AssertionError: x", DefectCategory.LOGIC_ERROR),
            ("SQL injection vulnerability", DefectCategory.SECURITY),
            ("database sql error", DefectCategory.DATA_INTEGRITY),
            ("connection failed", DefectCategory.INFRASTRUCTURE),
            ("config error invalid", DefectCategory.CONFIGURATION),
        ]
        for text, expected_cat in matched_cases:
            result = self.classifier.classify(text)
            assert result.category == expected_cat, \
                f"前置: 文本 '{text}' 应分类为 {expected_cat.value}"
            assert result.confidence > 0.0, (
                f"匹配 pattern 后 confidence 必须 > 0, 实际 {result.confidence} "
                f"(text='{text}') — 若为 0.0 说明 _calculate_confidence 被破坏 (变异 C3)"
            )

    def test_classify_returns_keywords_list(self):
        """[真实业务] keywords 必须是 list, 最多5个 (源码 _extract_keywords)。"""
        result = self.classifier.classify("timeout error slow performance")
        assert isinstance(result.keywords, list), \
            f"keywords 必须是 list, 实际: {type(result.keywords)}"
        assert len(result.keywords) <= 5, \
            f"keywords 最多5个, 实际 {len(result.keywords)}: {result.keywords}"

    def test_classify_returns_nonempty_explanation(self):
        """[真实业务] explanation 必须非空 (源码 _generate_explanation)。"""
        result = self.classifier.classify("timeout performance issue")
        assert isinstance(result.explanation, str) and len(result.explanation) > 0, \
            f"explanation 必须非空, 实际: '{result.explanation}'"

    def test_classify_returns_suggested_actions_for_each_category(self):
        """[真实业务] suggested_actions 必须按 category 返回 (源码 _generate_suggested_actions)。"""
        # 每个category都有对应的建议actions
        test_cases = [
            ("AssertionError", DefectCategory.LOGIC_ERROR),
            ("timeout slow", DefectCategory.PERFORMANCE),
            ("SQL injection", DefectCategory.SECURITY),
            ("database sql error", DefectCategory.DATA_INTEGRITY),
            ("config error", DefectCategory.CONFIGURATION),
            ("connection failed", DefectCategory.INFRASTRUCTURE),
        ]
        for text, expected_cat in test_cases:
            result = self.classifier.classify(text)
            assert result.category == expected_cat
            assert isinstance(result.suggested_actions, list), \
                f"suggested_actions 必须是 list"
            assert len(result.suggested_actions) >= 1, (
                f"category={result.category.value} 的 suggested_actions 不应为空 — "
                "若空则 _generate_suggested_actions 被破坏"
            )

    def test_classify_to_dict_serialization(self):
        """[真实业务] to_dict 必须包含所有字段且枚举转为 value 字符串。"""
        result = self.classifier.classify("timeout critical crash")
        d = result.to_dict()
        assert d["category"] == result.category.value
        assert d["severity"] == result.severity.value
        assert isinstance(d["confidence"], float)
        assert isinstance(d["keywords"], list)
        assert isinstance(d["suggested_actions"], list)
        # 枚举必须转字符串 (JSON 序列化要求)
        assert isinstance(d["category"], str), \
            "to_dict 后 category 必须是字符串, 不能是枚举对象"
        assert isinstance(d["severity"], str), \
            "to_dict 后 severity 必须是字符串"

    def test_classify_empty_input_uses_fallback(self):
        """[真实业务] 空输入: 走 fallback, category=LOGIC_ERROR, severity=MEDIUM (默认值)。"""
        result = self.classifier.classify("")
        assert isinstance(result, ClassificationResult)
        # 空字符串不匹配任何 pattern → 默认 LOGIC_ERROR
        assert result.category == DefectCategory.LOGIC_ERROR, \
            "空输入默认应分类为 LOGIC_ERROR"
        assert result.severity == Severity.MEDIUM, \
            "空输入默认 severity 应为 MEDIUM"

    def test_classify_consistent_output(self):
        """[真实业务] 相同输入必须返回相同结果 (确定性)。"""
        r1 = self.classifier.classify("timeout error")
        r2 = self.classifier.classify("timeout error")
        assert r1.category == r2.category
        assert r1.severity == r2.severity
        assert r1.confidence == r2.confidence
        assert r1.keywords == r2.keywords

    def test_classify_test_result_categorizes_status(self):
        """[真实业务] classify_test_result 按 status 分类 (源码 classifier.py:174-224)。

        源码分支顺序: passed → failed → error → skipped → timeout-in-text → default。
        timeout 分支只在 status 不匹配上述任一时才检查 full_text。
        """
        from src.ai.classifier import TestResultCategory

        # passed → result_category=PASS
        r = self.classifier.classify_test_result({"status": "passed"})
        assert r.result_category == TestResultCategory.PASS
        assert r.confidence == 1.0

        # skipped → SKIP
        r = self.classifier.classify_test_result({"status": "skipped"})
        assert r.result_category == TestResultCategory.SKIP
        assert r.confidence == 0.9

        # failed with timeout → FAIL + severity from classify (走 failed 分支, 不是 timeout)
        r = self.classifier.classify_test_result({
            "status": "failed",
            "error_message": "timeout exceeded",
            "stack_trace": "",
            "test_name": "test_timeout",
        })
        assert r.result_category == TestResultCategory.FAIL, \
            "status=failed 走 FAIL 分支 (即使 error_message 含 timeout)"
        assert r.defect_category == DefectCategory.PERFORMANCE, \
            "failed+timeout 文本应分类为 PERFORMANCE"

        # status=unknown + timeout in full_text → TIMEOUT 分支 (源码 line 210)
        r = self.classifier.classify_test_result({
            "status": "running",
            "error_message": "request timeout",
            "stack_trace": "",
            "test_name": "test_x",
        })
        # status="running" 不匹配 passed/failed/error/skipped → 走 timeout 检查
        assert r.result_category == TestResultCategory.TIMEOUT, (
            f"status=unknown + timeout in text 应走 TIMEOUT 分支, "
            f"实际 {r.result_category}"
        )
        assert r.defect_category == DefectCategory.PERFORMANCE
        assert r.severity == Severity.HIGH  # TIMEOUT 分支硬编码 HIGH


class TestAIEvaluatorBusinessLogic:
    """evaluator.evaluate 必须按 score 公式真实计算 (源码 evaluator.py:54-134)。"""

    def setup_method(self):
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        self.evaluator = AIEvaluator()

    def test_evaluate_matching_output_scores_high(self):
        """[真实业务] 相同输出: score ≥ 0.8, matches_expected=True, grade ∈ {EXCELLENT, GOOD}。

        防变异: matches_expected 永远 True 时, 此测试不会失败; 但若 score 公式被改, 此测试会失败。
        所以需要组合断言: score>=0.8 AND matches_expected AND grade 不是 POOR。
        """
        result = self.evaluator.evaluate("hello world", "hello world")
        assert isinstance(result, EvaluationResult)
        # similarity: 相同字符串 → 1.0 (交集/并集 = 1.0)
        assert result.similarity == 1.0, \
            f"相同字符串 similarity 应为 1.0, 实际 {result.similarity}"
        # correctness: SequenceMatcher 相同字符串 → 1.0
        assert result.correctness == 1.0, \
            f"相同字符串 correctness 应为 1.0, 实际 {result.correctness}"
        # completeness: 相同 → 1.0
        assert result.completeness == 1.0, \
            f"相同字符串 completeness 应为 1.0, 实际 {result.completeness}"
        # score = 1.0*0.4 + 1.0*0.3 + 1.0*0.3 = 1.0
        assert abs(result.score - 1.0) < 1e-6, (
            f"score 应为 1.0 (公式: sim*0.4+corr*0.3+compl*0.3), 实际 {result.score}"
        )
        assert result.matches_expected is True, \
            "score>=0.8 时 matches_expected 必须为 True"
        assert result.grade in (EvaluationGrade.EXCELLENT, EvaluationGrade.GOOD), \
            f"score>=0.9 应 EXCELLENT, score>=0.7 应 GOOD; 实际 {result.grade}"

    def test_evaluate_mismatched_output_scores_low(self):
        """[真实业务] 完全不同输出: score<0.8, matches_expected=False。

        防变异 E1: matches_expected 永远 True → 此测试必失败。
        """
        result = self.evaluator.evaluate("error occurred", "success result")
        # similarity: 两字符串无共同词 → 0.0
        assert result.similarity == 0.0, (
            f"'error occurred' 与 'success result' 无共同词, similarity 应为 0.0, "
            f"实际 {result.similarity}"
        )
        # matches_expected 必须 False (因为 score < 0.8)
        assert result.matches_expected is False, (
            "不同输出 score 应 < 0.8, matches_expected 必须为 False — "
            "若为 True 说明 matches_expected 永远 True (变异 E1)"
        )
        # grade 应该是 POOR 或 FAIR (低分)
        assert result.grade in (EvaluationGrade.POOR, EvaluationGrade.FAIR), \
            f"低分 grade 应为 POOR/FAIR, 实际 {result.grade}"

    def test_evaluate_empty_output_returns_poor(self):
        """[真实业务] 空输出 → grade=POOR, score=0.0, matches_expected=False。

        防变异 E3: 空输入返回 EXCELLENT → 此测试必失败。
        """
        result = self.evaluator.evaluate("", "")
        assert result.grade == EvaluationGrade.POOR, (
            f"空输入 grade 应为 POOR, 实际 {result.grade} — "
            "若非 POOR 说明空输入分支被破坏 (变异 E3)"
        )
        assert result.score == 0.0, f"空输入 score 应为 0.0, 实际 {result.score}"
        assert result.matches_expected is False
        assert result.similarity == 0.0
        assert result.correctness == 0.0
        assert result.completeness == 0.0
        # explanation 必须含"输出为空"提示
        assert "输出为空" in result.explanation, (
            f"空输入 explanation 应含'输出为空', 实际: '{result.explanation}'"
        )
        # suggestions 必须非空
        assert "improvement" in result.suggestions, \
            f"空输入 suggestions 应含 improvement, 实际: {result.suggestions}"

    def test_evaluate_score_formula_is_weighted_sum(self):
        """[真实业务] score = similarity*0.4 + correctness*0.3 + completeness*0.3 (源码 line 115)。"""
        # 用一个部分匹配的例子, 让 score != 任何单一指标
        result = self.evaluator.evaluate("hello world test", "hello world")
        # 手算: similarity=2/3 (intersection={hello,world}, union={hello,world,test})
        expected_sim = 2.0 / 3.0
        assert abs(result.similarity - expected_sim) < 1e-6, (
            f"similarity 应为 {expected_sim}, 实际 {result.similarity}"
        )
        # 验证 score 公式
        expected_score = (
            result.similarity * 0.4
            + result.correctness * 0.3
            + result.completeness * 0.3
        )
        assert abs(result.score - expected_score) < 1e-6, (
            f"score 必须等于 sim*0.4+corr*0.3+compl*0.3 = {expected_score}, "
            f"实际 {result.score} — 公式被破坏"
        )

    def test_evaluate_grade_thresholds(self):
        """[真实业务] grade 阈值: ≥0.9 EXCELLENT, ≥0.7 GOOD, ≥0.5 FAIR, else POOR (源码 line 222-230)。"""
        # EXCELLENT: 完全匹配 score=1.0
        r = self.evaluator.evaluate("hello", "hello")
        assert r.grade == EvaluationGrade.EXCELLENT, \
            f"score=1.0 应 EXCELLENT, 实际 {r.grade}"
        # POOR: 空输入 score=0.0
        r = self.evaluator.evaluate("", "expected output")
        assert r.grade == EvaluationGrade.POOR, \
            f"空输入应 POOR, 实际 {r.grade}"

    def test_evaluate_to_dict_has_all_fields(self):
        """[真实业务] to_dict 必须含全部11个字段且 grade 枚举转字符串。"""
        result = self.evaluator.evaluate("hello", "hello")
        d = result.to_dict()
        required = {"grade", "score", "matches_expected", "similarity",
                    "correctness", "completeness", "confidence",
                    "explanation", "discrepancies", "suggestions", "evaluated_at"}
        missing = required - set(d.keys())
        assert not missing, f"to_dict 缺字段: {missing}"
        assert isinstance(d["grade"], str), "grade 必须转字符串"
        assert d["grade"] in ("excellent", "good", "fair", "poor")
        assert isinstance(d["matches_expected"], bool)
        assert isinstance(d["score"], float)

    def test_evaluate_discrepancies_when_content_differs(self):
        """[真实业务] 内容不同时, discrepancies 必须含 content_mismatch (源码 line 257-275)。"""
        result = self.evaluator.evaluate("actual output", "expected output")
        assert "content_mismatch" in result.discrepancies, (
            f"内容不同时 discrepancies 应含 content_mismatch, "
            f"实际: {result.discrepancies}"
        )
        # content_mismatch 应含 expected/actual 两个字段
        cm = result.discrepancies["content_mismatch"]
        assert "expected" in cm and "actual" in cm


class TestAIQAEngineBusinessLogic:
    """qa_engine.answer 必须按知识库真实检索 (源码 qa_engine.py:110-198)。"""

    def setup_method(self):
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        self.engine = AIQAEngine()

    def test_answer_testing_question_hits_knowledge_base(self):
        """[真实业务] 含 'testing' 关键词的提问 → 命中知识库 → source=KNOWLEDGE_BASE。

        源码匹配逻辑 (qa_engine.py:164-167):
          if any(tag.lower() in question_lower for tag in entry.tags):
              matched_entries.append(entry)
          elif entry.title.lower() in question_lower or question_lower in entry.title.lower():
              matched_entries.append(entry)
        即 tag 是 question 的子串。kb_test_001 tags=['testing','test_case','design'],
        'testing' 在 'what is mutation testing?' 里 → 命中 kb_test_001。

        防变异 Q1: confidence 永远 LOW → 此测试必失败 (因为命中的应是 MEDIUM/HIGH)。
        防变异 Q2: references 永远空 → 此测试必失败。
        """
        result = self.engine.answer("What is mutation testing?")
        assert isinstance(result, QAAnswer)
        # 命中知识库 (kb_test_001 含 'testing' tag)
        assert result.source == AnswerSource.KNOWLEDGE_BASE, (
            f"含 'testing' 的提问应命中知识库 source=KNOWLEDGE_BASE, "
            f"实际 {result.source}"
        )
        # references 必须含命中的 entry.id (至少含 kb_test_001)
        assert isinstance(result.references, list) and len(result.references) >= 1, (
            "命中知识库时 references 必须非空 — 若空说明 references 被清空 (变异 Q2)"
        )
        assert "kb_test_001" in result.references, (
            f"提问 'mutation testing' 含 'testing' tag 应命中 kb_test_001, "
            f"references={result.references}"
        )
        # confidence 应为 MEDIUM 或 HIGH (源码 line 176-180)
        assert result.confidence in (AnswerConfidence.MEDIUM, AnswerConfidence.HIGH), (
            f"命中知识库时 confidence 应为 MEDIUM/HIGH, 实际 {result.confidence} — "
            "若 LOW 说明 confidence 逻辑被破坏 (变异 Q1)"
        )
        # answer 必须含知识库内容关键词
        assert "测试" in result.answer, (
            f"answer 应含知识库内容, 实际: '{result.answer[:200]}'"
        )

    def test_answer_governance_question_hits_knowledge_base(self):
        """[真实业务] 治理相关问题命中 kb_governance_*。"""
        result = self.engine.answer("Tell me about governance approval process")
        assert result.source == AnswerSource.KNOWLEDGE_BASE
        assert any(rid.startswith("kb_governance") for rid in result.references), (
            f"governance 提问应命中 kb_governance_*, references={result.references}"
        )
        assert "审批" in result.answer or "approval" in result.answer.lower()

    def test_answer_convergence_question_hits_knowledge_base(self):
        """[真实业务] 收敛相关问题命中 kb_governance_002。"""
        result = self.engine.answer("What is system convergence criteria?")
        assert result.source == AnswerSource.KNOWLEDGE_BASE
        assert "kb_governance_002" in result.references, (
            f"convergence 提问应命中 kb_governance_002, references={result.references}"
        )
        assert "0.9" in result.answer or "收敛" in result.answer, (
            f"answer 应含收敛分数 0.9 或'收敛'关键词, 实际: '{result.answer[:200]}'"
        )

    def test_answer_unknown_question_returns_low_confidence(self):
        """[真实业务] 完全无关问题 → confidence=LOW, source=MODEL_GENERATION (fallback)。"""
        result = self.engine.answer("xyzzy plugh random gibberish 12345")
        assert result.confidence == AnswerConfidence.LOW, (
            f"无关问题 confidence 应为 LOW, 实际 {result.confidence}"
        )
        assert result.source == AnswerSource.MODEL_GENERATION, \
            f"无关问题 fallback source 应为 MODEL_GENERATION, 实际 {result.source}"
        assert len(result.references) == 0, \
            "无关问题 references 应为空"
        # answer 必须含"信息有限"或类似 fallback 提示 (源码 line 192)
        assert "有限" in result.answer or "limited" in result.answer.lower(), (
            f"无关问题 answer 应含 fallback 提示, 实际: '{result.answer[:200]}'"
        )

    def test_answer_with_context_merges_context(self):
        """[真实业务] 带 context 的提问 → answer 仍按问题命中知识库。"""
        result = self.engine.answer(
            "What is testing?",
            context="test_login failed with 401"
        )
        assert isinstance(result, QAAnswer)
        # 应命中 testing 相关知识库
        assert result.source == AnswerSource.KNOWLEDGE_BASE
        assert len(result.references) >= 1

    def test_answer_returns_follow_up_questions_for_testing(self):
        """[真实业务] testing 关键词 → follow_up_questions 含 testing 相关 (源码 line 223-239)。"""
        result = self.engine.answer("testing best practices")
        assert isinstance(result.follow_up_questions, list)
        assert len(result.follow_up_questions) >= 1, (
            "testing 提问应生成 follow_up_questions"
        )
        # follow_up 应含"测试"或"testing"
        joined = " ".join(result.follow_up_questions).lower()
        assert "测试" in joined or "testing" in joined, (
            f"follow_up_questions 应含 testing/测试 主题, 实际: {result.follow_up_questions}"
        )

    def test_answer_consistent(self):
        """[真实业务] 相同问题 → 相同答案 (确定性)。"""
        r1 = self.engine.answer("What is mutation testing?")
        r2 = self.engine.answer("What is mutation testing?")
        assert r1.answer == r2.answer
        assert r1.references == r2.references
        assert r1.confidence == r2.confidence
        assert r1.source == r2.source

    def test_answer_empty_question_documents_known_quirk(self):
        """[真实业务+诚实声明] 空问题行为: 源码 line 166 `question_lower in entry.title.lower()`,
        当 question="" 时, "" in 任何字符串都返回 True → 命中所有 entry → confidence=HIGH。

        这是源码的真实行为 (虽然语义上有 bug: 空问题不应命中任何知识)。
        测试断言真实行为, 而非理想行为; 若日后修复此 bug, 此测试需更新。
        """
        result = self.engine.answer("")
        # 真实行为: 空问题命中所有 entry (源码 quirk)
        assert result.source == AnswerSource.KNOWLEDGE_BASE, (
            f"空问题因源码 quirk 命中所有 entry, source 应为 KNOWLEDGE_BASE, "
            f"实际 {result.source}"
        )
        assert len(result.references) >= 1, \
            "空问题应命中所有 entry (源码 quirk), references 不为空"
        assert result.confidence == AnswerConfidence.HIGH, (
            f"空问题命中>=2 entry → HIGH (源码 line 176-180), 实际 {result.confidence}"
        )

    def test_answer_to_dict_has_all_fields(self):
        """[真实业务] to_dict 含全部字段且枚举转字符串。"""
        result = self.engine.answer("testing question")
        d = result.to_dict()
        required = {"answer", "confidence", "source", "context",
                    "references", "follow_up_questions", "answered_at"}
        missing = required - set(d.keys())
        assert not missing, f"to_dict 缺字段: {missing}"
        assert isinstance(d["confidence"], str), "confidence 必须转字符串"
        assert isinstance(d["source"], str), "source 必须转字符串"
