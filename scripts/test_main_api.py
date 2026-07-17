import httpx
import asyncio


async def test_api_execution():
    url = "http://127.0.0.1:8000/execute"

    # 模拟一个真实的测试负载
    payload = {
        "step_id": "step_101",
        "description": "验证用户查询接口",
        "protocol": "http",
        "url": "https://api.test.com/users",
        "method": "GET",
        "params": {"id": "${user}"},
        "assertions": [
            {"check": "status_code", "operator": "eq", "expected": 200},
            {"check": "body_contains", "operator": "contains", "expected": "admin"}
        ]
    }

    async with httpx.AsyncClient() as client:
        print(">>> 正在发送测试请求...")
        response = await client.post(url, json=payload, timeout=10.0)

        if response.status_code == 200:
            data = response.json()
            print(f"✅ 执行成功! 状态: {data['status']}")
            print(f"详情: {data['result']}")
        else:
            print(f"❌ 执行失败: {response.text}")


if __name__ == "__main__":
    asyncio.run(test_api_execution())