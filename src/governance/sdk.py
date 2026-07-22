import logging
import threading
from typing import Any, Optional

from src.governance.api_error_recorder import APIErrorRecorder
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
        if hasattr(self, "_initialized"):
            return
        self._client = None
        self._logger = logging.getLogger("GovernanceClientSDK")
        self.breaker = CircuitBreaker(
            threshold=GovernanceConfig.CIRCUIT_BREAKER_THRESHOLD,
            recovery_timeout=GovernanceConfig.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
        )
        self._initialized = True

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    @property
    def client(self):
        if self._client is None and GovernanceConfig.is_llm_configured() and not GovernanceConfig.USE_MOCK_LLM:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=GovernanceConfig.DEEPSEEK_API_KEY,
                base_url=GovernanceConfig.DEEPSEEK_BASE_URL,
                timeout=30.0,
            )
        return self._client

    def is_available(self) -> bool:
        if GovernanceConfig.USE_MOCK_LLM:
            return True
        return GovernanceConfig.is_llm_configured()

    def get_api_key_status(self) -> dict:
        return GovernanceConfig.validate_api_key()

    async def chat_completion(self, messages, model="deepseek-chat", temperature=0.2):
        if GovernanceConfig.USE_MOCK_LLM and not GovernanceConfig.TESTAI_RULE_13:
            return await self.get_mock_response(messages)

        if GovernanceConfig.TESTAI_RULE_13 and GovernanceConfig.USE_MOCK_LLM:
            raise RuntimeError(
                "[TESTAI@13] ERROR: USE_MOCK_LLM is enabled but TESTAI@13 requires real API KEY testing. "
                "Set USE_MOCK_LLM=false to comply with TESTAI@13."
            )

        if not self.is_available():
            validation = self.get_api_key_status()
            error_msg = f"LLM service not configured. {validation['message']}"
            APIErrorRecorder.record_error(
                error_type="configuration_error",
                error_message=error_msg,
                api_key=GovernanceConfig.DEEPSEEK_API_KEY,
                endpoint="/v1/chat/completions",
            )
            raise RuntimeError(
                f"{error_msg}. Set DEEPSEEK_API_KEY environment variable."
            )

        if not self.breaker.can_execute():
            error_msg = "Circuit Breaker is OPEN: Governance service unavailable."
            APIErrorRecorder.record_error(
                error_type="circuit_breaker_open",
                error_message=error_msg,
                api_key=GovernanceConfig.DEEPSEEK_API_KEY,
                endpoint="/v1/chat/completions",
            )
            raise RuntimeError(error_msg)

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            self.breaker.record_success()

            if response.choices and response.choices[0].message:
                return response.choices[0].message
            error_msg = "Empty response from AI service"
            APIErrorRecorder.record_error(
                error_type="empty_response",
                error_message=error_msg,
                api_key=GovernanceConfig.DEEPSEEK_API_KEY,
                endpoint="/v1/chat/completions",
                additional_info={"model": model},
            )
            raise ValueError(error_msg)

        except ValueError:
            raise

        except Exception as e:
            self.breaker.record_failure()
            error_msg = str(e)
            
            http_status = None
            if "401" in error_msg or "Unauthorized" in error_msg:
                http_status = 401
                error_type = "authentication_failure"
                detailed_msg = f"API authentication failed. Please check your DEEPSEEK_API_KEY. Error: {error_msg}"
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                http_status = 429
                error_type = "rate_limit_exceeded"
                detailed_msg = f"API rate limit exceeded. Please try again later. Error: {error_msg}"
            elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                http_status = 0
                error_type = "connection_failure"
                detailed_msg = f"Network connection failed. Please check your internet connection. Error: {error_msg}"
            elif "500" in error_msg or "502" in error_msg or "503" in error_msg or "504" in error_msg:
                http_status = int(error_msg[error_msg.find("5"):error_msg.find("5")+3]) if "5" in error_msg else 500
                error_type = "server_error"
                detailed_msg = f"Server error. Error: {error_msg}"
            else:
                http_status = None
                error_type = "unknown_error"
                detailed_msg = f"API call failed. Error: {error_msg}"

            APIErrorRecorder.record_error(
                error_type=error_type,
                error_message=error_msg,
                api_key=GovernanceConfig.DEEPSEEK_API_KEY,
                endpoint="/v1/chat/completions",
                http_status=http_status,
                additional_info={"model": model, "messages_count": len(messages)},
            )

            if GovernanceConfig.TESTAI_RULE_13:
                complaint_report = APIErrorRecorder.generate_complaint_report()
                print("\n" + "=" * 80)
                print("[TESTAI@13] COMPLAINT REPORT GENERATED")
                print("=" * 80)
                print(complaint_report)

            raise RuntimeError(detailed_msg)

    async def get_mock_response(self, messages) -> MockLLMResponse:
        user_content = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                break

        import json
        import re

        context = self._parse_diagnostic_context(user_content)
        target_function = context.get("target_function", "leave_FunctionDef")
        component = context.get("component", "transformer")
        error_type = context.get("error_type", "")

        suggested_code, reasoning = self._generate_contextual_fix(
            component, error_type, target_function
        )

        mock_response = {
            "is_fixable": True,
            "reasoning": reasoning,
            "confidence_score": 0.95,
            "patch_proposal": {
                "patch_type": "functional",
                "target_function": target_function,
                "suggested_code": suggested_code,
                "description": f"Auto-generated fix for {component} component",
            },
        }
        return MockLLMResponse(content=json.dumps(mock_response))

    def _parse_diagnostic_context(self, user_content: str) -> dict:
        import json

        context = {}

        try:
            try:
                parsed = json.loads(user_content)
                if isinstance(parsed, dict):
                    self._extract_context_from_dict(parsed, context)
            except json.JSONDecodeError:
                import re

                json_match = re.search(r"\{.*\}", user_content)
                if json_match:
                    json_str = json_match.group(0)
                    try:
                        parsed = json.loads(json_str)
                        if isinstance(parsed, dict):
                            self._extract_context_from_dict(parsed, context)
                    except json.JSONDecodeError as e:
                        self._logger.debug(f"Failed to parse JSON from response: {e}")
        except Exception as e:
            self._logger.debug(f"Failed to extract context from response: {e}")

        return context

    def _extract_context_from_dict(self, parsed: dict, context: dict):
        if "target_function" in parsed:
            context["target_function"] = parsed["target_function"]
        if "component_name" in parsed:
            context["component"] = parsed["component_name"]
        if "exception_trace" in parsed:
            error_text = str(parsed["exception_trace"])
            if "patched" in error_text.lower():
                context["error_type"] = "patched_missing"
            elif "AttributeError" in error_text:
                context["error_type"] = "attribute_error"
            elif "AssertionError" in error_text:
                context["error_type"] = "assertion_error"

    def _generate_contextual_fix(
        self, component: str, error_type: str, target_function: str
    ) -> tuple:
        if component == "transformer" and error_type == "patched_missing":
            suggested_code = """name_match = (original_node.name.value == self.target_function)
class_match = (self.target_class is None or self.current_class == self.target_class)

if name_match and class_match:
    self.patched = True
    return updated_node.with_changes(body=cst.IndentedBlock(body=self.new_body_nodes))

if name_match and self.target_class and self.current_class != self.target_class:
    print(f"[DEBUG] Class mismatch: Expected {self.target_class}, found {self.current_class}")

return updated_node"""
            reasoning = "诊断发现 transformer 组件中 leave_FunctionDef 方法缺少 self.patched = True 设置。这会导致补丁应用后无法正确标记修补状态，从而使执行器认为目标函数未找到。修复方案是在匹配成功时设置 self.patched = True。"
            return suggested_code, reasoning

        elif component == "transformer":
            suggested_code = """if original_node.name.value == self.target_function:
    self.patched = True
    return updated_node.with_changes(body=cst.IndentedBlock(body=self.new_body_nodes))
return updated_node"""
            reasoning = "诊断发现 transformer 组件存在问题。修复方案是确保在匹配目标函数时正确设置 patched 标记并返回修改后的节点。"
            return suggested_code, reasoning

        elif component == "executor":
            suggested_code = """if not self.is_safe_patch(suggested_code):
    return False

if not self.validate_file_path(file_path):
    self.logger.critical(f"Patch rejected: unsafe file path '{file_path}'")
    return False

try:
    self._write_patch(file_path, patch_type, target_function, suggested_code, required_imports, target_class)
    return True
except Exception as e:
    self.logger.critical(f"Patch failed: {e}")
    return False"""
            reasoning = "诊断发现 executor 组件存在问题。修复方案是确保在应用补丁前进行安全验证和路径验证，并在写入失败时正确处理异常。"
            return suggested_code, reasoning

        else:
            suggested_code = """self.patched = True
return updated_node"""
            reasoning = "诊断发现组件存在问题，已生成通用修复方案。"
            return suggested_code, reasoning