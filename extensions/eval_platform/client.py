# extensions/eval_platform/client.py
import httpx
from extensions.eval_platform.models import EvalRequestContract, DomainResponse

class EvalPlatformClient:
    def __init__(self, base_url="http://192.168.30.134:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def evaluate(self, contract: EvalRequestContract) -> DomainResponse:
        """调用 AI 评测接口并返回结构化结果"""
        try:
            response = await self.client.post(
                contract.endpoint,
                json=contract.request_body.dict()
            )
            response.raise_for_status() # 抛出 HTTP 错误，触发异常治理
            return DomainResponse(**response.json())
        except httpx.HTTPStatusError as e:
            # 这里的异常会被 Pipeline 捕获
            raise RuntimeError(f"EvalPlatform API Error: {e.response.text}") from e
        except Exception as e:
            raise RuntimeError(f"EvalPlatform Connection Failed: {str(e)}") from e