import threading
from typing import Any, Optional

from src.governance.config import GovernanceConfig
from src.governance.resilience import CircuitBreaker


class MockLLMResponse:
    def __init__(self, content: str):
        self.content = content


class MockChoice:
    def __init__(self, message):
        self.message = message


class MockChatResponse:
    def __init__(self, choices):
        self.choices = choices


class GovernanceClientSDK:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._client = None
        self.breaker = CircuitBreaker(
            threshold=GovernanceConfig.CIRCUIT_BREAKER_THRESHOLD,
            recovery_timeout=GovernanceConfig.CIRCUIT_BREAKER_RECOVERY_TIMEOUT
        )
        self._initialized = True

    @property
    def client(self):
        if self._client is None and GovernanceConfig.is_llm_configured():
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=GovernanceConfig.DEEPSEEK_API_KEY,
                base_url=GovernanceConfig.DEEPSEEK_BASE_URL,
                timeout=30.0
            )
        return self._client

    def is_available(self) -> bool:
        return GovernanceConfig.is_llm_configured()

    async def chat_completion(self, messages, model="deepseek-chat", temperature=0.2):
        if not self.is_available():
            raise RuntimeError("LLM service not configured. Set DEEPSEEK_API_KEY environment variable.")

        if not self.breaker.can_execute():
            raise RuntimeError("Circuit Breaker is OPEN: Governance service unavailable.")

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"}
            )
            self.breaker.record_success()

            if response.choices and response.choices[0].message:
                return response.choices[0].message
            raise ValueError("Empty response from AI service")

        except Exception as e:
            self.breaker.record_failure()
            raise e

    async def get_mock_response(self, messages) -> MockLLMResponse:
        user_content = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                break

        import json
        mock_response = {
            "is_fixable": True,
            "reasoning": "Mock diagnosis for testing: Analyzed the error context and identified potential fix.",
            "confidence_score": 0.85,
            "patch_proposal": {
                "patch_type": "functional",
                "target_function": "test_function",
                "suggested_code": "def test_function(): return True",
                "description": "Mock patch for testing purposes"
            }
        }
        return MockLLMResponse(content=json.dumps(mock_response))