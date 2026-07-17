import pytest
from unittest.mock import AsyncMock, MagicMock
from src.governance.sdk import GovernanceClientSDK


class TestGovernanceClientSDK:

    @pytest.mark.asyncio
    async def test_chat_completion_returns_message_object(self):
        sdk = GovernanceClientSDK()
        
        mock_message = MagicMock()
        mock_message.content = '{"is_fixable": true, "reasoning": "test"}'
        
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        
        sdk.client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        result = await sdk.chat_completion([{"role": "user", "content": "test"}])
        
        assert hasattr(result, 'content')
        assert result.content == '{"is_fixable": true, "reasoning": "test"}'

    @pytest.mark.asyncio
    async def test_chat_completion_handles_empty_response(self):
        sdk = GovernanceClientSDK()
        
        mock_response = MagicMock()
        mock_response.choices = []
        
        sdk.client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        with pytest.raises(ValueError, match="Empty response"):
            await sdk.chat_completion([{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_chat_completion_handles_null_message(self):
        sdk = GovernanceClientSDK()
        
        mock_choice = MagicMock()
        mock_choice.message = None
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        
        sdk.client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        with pytest.raises(ValueError, match="Empty response"):
            await sdk.chat_completion([{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_chat_completion_sends_json_response_format(self):
        sdk = GovernanceClientSDK()
        
        mock_message = MagicMock()
        mock_message.content = '{"is_fixable": true}'
        
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        
        sdk.client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        await sdk.chat_completion([{"role": "user", "content": "test"}])
        
        sdk.client.chat.completions.create.assert_called_once()
        call_args = sdk.client.chat.completions.create.call_args[1]
        assert call_args['response_format'] == {"type": "json_object"}