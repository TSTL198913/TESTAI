from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.governance.sdk import GovernanceClientSDK


class TestGovernanceClientSDK:

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        GovernanceClientSDK.reset_instance()
        yield
        GovernanceClientSDK.reset_instance()

    @pytest.mark.asyncio
    async def test_chat_completion_returns_message_object(self):
        with patch.object(GovernanceClientSDK, 'is_available', return_value=True):
            sdk = GovernanceClientSDK()

            mock_message = MagicMock()
            mock_message.content = '{"is_fixable": true, "reasoning": "test"}'

            mock_choice = MagicMock()
            mock_choice.message = mock_message

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]

            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            sdk._client = mock_client

            result = await sdk.chat_completion([{"role": "user", "content": "test"}])

            assert getattr(result, "content", None) == '{"is_fixable": true, "reasoning": "test"}'

    @pytest.mark.asyncio
    async def test_chat_completion_handles_empty_response(self):
        with patch.object(GovernanceClientSDK, 'is_available', return_value=True):
            sdk = GovernanceClientSDK()

            mock_response = MagicMock()
            mock_response.choices = []

            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            sdk._client = mock_client

            with pytest.raises(ValueError, match="Empty response"):
                await sdk.chat_completion([{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_chat_completion_handles_null_message(self):
        with patch.object(GovernanceClientSDK, 'is_available', return_value=True):
            sdk = GovernanceClientSDK()

            mock_choice = MagicMock()
            mock_choice.message = None

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]

            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            sdk._client = mock_client

            with pytest.raises(ValueError, match="Empty response"):
                await sdk.chat_completion([{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_chat_completion_sends_json_response_format(self):
        with patch.object(GovernanceClientSDK, 'is_available', return_value=True):
            sdk = GovernanceClientSDK()

            mock_message = MagicMock()
            mock_message.content = '{"is_fixable": true}'

            mock_choice = MagicMock()
            mock_choice.message = mock_message

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]

            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            sdk._client = mock_client

            await sdk.chat_completion([{"role": "user", "content": "test"}])

            mock_client.chat.completions.create.assert_called_once()
            call_args = mock_client.chat.completions.create.call_args[1]
            assert call_args["response_format"] == {"type": "json_object"}
