from src.governance.sdk import GovernanceClientSDK
import asyncio

async def test():
    sdk = GovernanceClientSDK()
    
    test_context = {
        "component_name": "transformer",
        "target_function": "leave_FunctionDef",
        "exception_trace": "AssertionError: patched flag not set"
    }
    
    import json
    messages = [{'role': 'user', 'content': json.dumps(test_context)}]
    print(f"User content: {messages[0]['content']}")
    
    context = sdk._parse_diagnostic_context(messages[0]['content'])
    print(f"Parsed context: {context}")
    
    response = await sdk.get_mock_response(messages)
    data = json.loads(response.content)
    print('=== Mock Response Test ===')
    print(f'Is fixable: {data["is_fixable"]}')
    print(f'Confidence: {data["confidence_score"]}')
    print(f'Reasoning: {data["reasoning"]}')
    print(f'Target function: {data["patch_proposal"]["target_function"]}')
    print(f'Suggested code:\n{data["patch_proposal"]["suggested_code"]}')

asyncio.run(test())
