import httpx
import time
from typing import Optional, Dict, Any, Tuple
from .schema import HTTPMethod


class APITestClient:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def send_request(
        self,
        method: HTTPMethod,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, Any], float, Dict[str, str]]:
        full_url = f"{self.base_url}{url}" if url.startswith("/") else url
        
        start_time = time.time()
        
        try:
            response = await self.client.request(
                method=method.value,
                url=full_url,
                headers=headers or {},
                params=params or {},
                json=body,
                timeout=self.timeout,
            )
            response_time = (time.time() - start_time) * 1000
            
            try:
                response_body = response.json()
            except ValueError:
                response_body = {"content": response.text}
            
            return (
                response.status_code,
                response_body,
                response_time,
                dict(response.headers),
            )
        except httpx.TimeoutException:
            response_time = (time.time() - start_time) * 1000
            return (0, {"error": "Request timed out"}, response_time, {})
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return (0, {"error": str(e)}, response_time, {})

    async def close(self):
        await self.client.aclose()

    async def get(self, url: str, **kwargs) -> Tuple[int, Dict[str, Any], float, Dict[str, str]]:
        return await self.send_request(HTTPMethod.GET, url, **kwargs)

    async def post(self, url: str, **kwargs) -> Tuple[int, Dict[str, Any], float, Dict[str, str]]:
        return await self.send_request(HTTPMethod.POST, url, **kwargs)

    async def put(self, url: str, **kwargs) -> Tuple[int, Dict[str, Any], float, Dict[str, str]]:
        return await self.send_request(HTTPMethod.PUT, url, **kwargs)

    async def delete(self, url: str, **kwargs) -> Tuple[int, Dict[str, Any], float, Dict[str, str]]:
        return await self.send_request(HTTPMethod.DELETE, url, **kwargs)