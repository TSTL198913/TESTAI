import os
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class AnswerSource(str, Enum):
    KNOWLEDGE_BASE = "knowledge_base"
    MODEL_GENERATION = "model_generation"
    CACHED = "cached"


class AnswerConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class QAAnswer:
    answer: str
    confidence: AnswerConfidence
    source: AnswerSource
    context: str = ""
    references: List[str] = field(default_factory=list)
    follow_up_questions: List[str] = field(default_factory=list)
    answered_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "confidence": self.confidence.value,
            "source": self.source.value,
            "context": self.context,
            "references": self.references,
            "follow_up_questions": self.follow_up_questions,
            "answered_at": self.answered_at.isoformat(),
        }


@dataclass
class KnowledgeEntry:
    id: str
    content: str
    title: str = ""
    category: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


class AIQAEngine:
    def __init__(self, llm_api_key: Optional[str] = None):
        self.llm_api_key = llm_api_key or os.environ.get("OPENAI_API_KEY")
        self.use_fallback = not self.llm_api_key
        self.logger = logging.getLogger(__name__)
        self.knowledge_base: Dict[str, KnowledgeEntry] = {}
        self._load_default_knowledge()

    def _load_default_knowledge(self):
        default_entries = [
            {
                "id": "kb_test_001",
                "title": "测试用例设计原则",
                "category": "testing",
                "content": "测试用例设计应遵循等价类划分、边界值分析、因果图等方法。应覆盖正向、负向、边界、异常、依赖五种场景。",
                "tags": ["testing", "test_case", "design"],
            },
            {
                "id": "kb_test_002",
                "title": "变异测试",
                "category": "testing",
                "content": "变异测试通过对源代码进行微小修改（变异）来评估测试用例的有效性。Kill Rate是衡量测试质量的重要指标，目标应≥70%。",
                "tags": ["mutation_testing", "kill_rate", "quality"],
            },
            {
                "id": "kb_test_003",
                "title": "API测试最佳实践",
                "category": "testing",
                "content": "API测试应验证状态码、响应格式、数据完整性、错误处理和性能。应使用结构化的断言而非仅验证status字段。",
                "tags": ["api_testing", "best_practices", "validation"],
            },
            {
                "id": "kb_governance_001",
                "title": "治理审批流程",
                "category": "governance",
                "content": "所有补丁执行前必须经过审批流程。SECURITY和REFACTORING类型的补丁需要人工审批，FUNCTIONAL类型可自动审批。审批记录有效期为24小时。",
                "tags": ["governance", "approval", "patch"],
            },
            {
                "id": "kb_governance_002",
                "title": "系统收敛",
                "category": "governance",
                "content": "系统收敛通过连续3次收敛事件判定。收敛分数≥0.9视为收敛，低于0.9视为发散。收敛状态变化会触发追踪事件记录。",
                "tags": ["convergence", "baseline", "monitoring"],
            },
        ]

        for entry in default_entries:
            self.knowledge_base[entry["id"]] = KnowledgeEntry(
                id=entry["id"],
                title=entry["title"],
                category=entry["category"],
                content=entry["content"],
                tags=entry["tags"],
            )

    def answer(self, question: str, context: str = None) -> QAAnswer:
        if self.use_fallback:
            return self._answer_fallback(question, context)

        try:
            return self._answer_with_llm(question, context)
        except Exception as e:
            self.logger.warning(f"LLM QA failed: {e}, falling back to knowledge base")
            return self._answer_fallback(question, context)

    def _answer_with_llm(self, question: str, context: str = None) -> QAAnswer:
        retrieved_context = self._retrieve_context(question)
        full_context = "\n".join([retrieved_context, context]) if context else retrieved_context

        prompt = self._build_qa_prompt(question, full_context)

        try:
            import openai
            client = openai.OpenAI(api_key=self.llm_api_key)

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的测试领域问答专家，基于提供的上下文回答问题。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )

            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM response content is None")

            return QAAnswer(
                answer=content,
                confidence=AnswerConfidence.HIGH,
                source=AnswerSource.MODEL_GENERATION,
                context=full_context[:500] if full_context else "",
                references=[],
                follow_up_questions=self._generate_follow_up_questions(question),
            )

        except Exception as e:
            self.logger.error(f"LLM QA error: {e}")
            raise

    def _answer_fallback(self, question: str, context: str = None) -> QAAnswer:
        question_lower = question.lower()
        matched_entries = []

        for entry in self.knowledge_base.values():
            if any(tag.lower() in question_lower for tag in entry.tags):
                matched_entries.append(entry)
            elif entry.title.lower() in question_lower or question_lower in entry.title.lower():
                matched_entries.append(entry)

        if matched_entries:
            answer_parts = []
            references = []
            for entry in matched_entries[:3]:
                answer_parts.append(entry.content)
                references.append(entry.id)

            confidence = (
                AnswerConfidence.HIGH
                if len(matched_entries) >= 2
                else AnswerConfidence.MEDIUM
            )

            return QAAnswer(
                answer="\n\n".join(answer_parts),
                confidence=confidence,
                source=AnswerSource.KNOWLEDGE_BASE,
                context="",
                references=references,
                follow_up_questions=self._generate_follow_up_questions(question),
            )
        else:
            return QAAnswer(
                answer=f"根据现有知识，关于'{question}'的信息有限。建议查看相关文档或联系技术支持。",
                confidence=AnswerConfidence.LOW,
                source=AnswerSource.MODEL_GENERATION,
                context="",
                references=[],
                follow_up_questions=[],
            )

    def _build_qa_prompt(self, question: str, context: str) -> str:
        return f"""
基于以下上下文回答问题：

上下文：
{context}

问题：
{question}

请提供清晰、准确的回答。如果上下文没有相关信息，请基于你的知识回答并说明来源。
"""

    def _retrieve_context(self, question: str) -> str:
        question_lower = question.lower()
        relevant_content = []

        for entry in self.knowledge_base.values():
            if any(tag.lower() in question_lower for tag in entry.tags):
                relevant_content.append(f"【{entry.title}】\n{entry.content}")

        return "\n\n".join(relevant_content)

    def _generate_follow_up_questions(self, question: str) -> List[str]:
        question_lower = question.lower()
        follow_ups = []

        if "测试" in question_lower or "testing" in question_lower:
            follow_ups.append("如何提高测试覆盖率？")
            follow_ups.append("如何设计有效的测试用例？")

        if "审批" in question_lower or "approval" in question_lower:
            follow_ups.append("审批流程的详细步骤是什么？")
            follow_ups.append("审批记录的有效期是多久？")

        if "收敛" in question_lower or "convergence" in question_lower:
            follow_ups.append("系统收敛的判定标准是什么？")
            follow_ups.append("如何提高收敛分数？")

        return follow_ups[:2]

    def add_knowledge(self, entry: KnowledgeEntry):
        self.knowledge_base[entry.id] = entry

    def remove_knowledge(self, entry_id: str):
        if entry_id in self.knowledge_base:
            del self.knowledge_base[entry_id]

    def get_knowledge_by_category(self, category: str) -> List[KnowledgeEntry]:
        return [e for e in self.knowledge_base.values() if e.category == category]

    def search_knowledge(self, query: str) -> List[KnowledgeEntry]:
        query_lower = query.lower()
        results = []
        for entry in self.knowledge_base.values():
            if (
                query_lower in entry.content.lower()
                or query_lower in entry.title.lower()
                or any(query_lower in tag.lower() for tag in entry.tags)
            ):
                results.append(entry)
        return results