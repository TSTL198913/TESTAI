import asyncio
import json
import logging
import re
from typing import Optional

from src.governance.config import GovernanceConfig
from src.governance.models import AIGovernanceResult, DiagnosticContext, PatchProposal
from src.governance.registry import PatchType
from src.governance.sdk import GovernanceClientSDK


class AIGovernanceAgent:
    def __init__(self, max_retries: int = 2):
        self.sdk = GovernanceClientSDK()
        self.logger = logging.getLogger("AIGovernanceAgent")
        self.max_retries = max_retries

    def _sanitize_response(self, content: str) -> str:
        pattern = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
        match = pattern.search(content)
        if match:
            return match.group(1)
        return content.strip()

    async def analyze_with_context(
        self, context: DiagnosticContext
    ) -> AIGovernanceResult:
        context_dict = context.model_dump()
        valid_patch_types = [t.value for t in PatchType]

        json_schema = {
            "type": "object",
            "required": ["is_fixable", "reasoning", "confidence_score"],
            "properties": {
                "is_fixable": {"type": "boolean"},
                "reasoning": {"type": "string"},
                "root_cause": {"type": "string"},
                "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "patch_proposal": {
                    "type": "object",
                    "required": ["target_function", "suggested_code", "patch_type"],
                    "properties": {
                        "target_function": {"type": "string"},
                        "target_class": {"type": "string"},
                        "suggested_code": {"type": "string"},
                        "required_imports": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "patch_type": {"type": "string", "enum": valid_patch_types},
                    },
                },
            },
        }

        prompt = f"""
        你是一名高级 AI 评测平台算法治理专家。
        
        【诊断上下文】：
        {json.dumps(context_dict, default=str, indent=2)}

        【任务】：分析上述错误，判断是否可修复，并生成修复建议。

        【JSON格式要求】：
        {json.dumps(json_schema, indent=2)}

        【规则】：
        1. is_fixable: 如果错误可以通过代码修复，设为true；否则设为false。
        2. reasoning: 详细说明错误原因和修复思路。
        3. confidence_score: 0.0到1.0之间，表示诊断置信度。
        4. patch_proposal: 只有is_fixable为true时才需要提供。
        5. patch_type: 必须是以下之一: {valid_patch_types}。
        6. suggested_code: 提供完整的修复代码。
        7. 输出必须是纯JSON，不要任何额外文本。
        """

        if not self.sdk.is_available():
            self.logger.info("LLM not configured, using mock diagnosis for testing")
            mock_response = await self.sdk.get_mock_response(
                [{"role": "user", "content": prompt}]
            )
            return AIGovernanceResult.model_validate_json(mock_response.content)

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.sdk.chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": "你只输出合法的JSON格式数据。不要Markdown格式，不要任何解释文字。",
                        },
                        {"role": "user", "content": prompt},
                    ]
                )

                raw_content = response.content
                clean_content = self._sanitize_response(raw_content)

                return AIGovernanceResult.model_validate_json(clean_content)

            except Exception as e:
                last_error = str(e)
                self.logger.warning(
                    f"Diagnosis attempt {attempt + 1} failed: {last_error}"
                )
                await asyncio.sleep(0.5 * (attempt + 1))

        self.logger.error(
            f"Deep Diagnosis failed after {self.max_retries + 1} attempts. Root Cause: {last_error}"
        )
        return AIGovernanceResult(
            is_fixable=False,
            reasoning=f"Agent failed to produce valid JSON: {last_error}",
            confidence_score=0.0,
        )
