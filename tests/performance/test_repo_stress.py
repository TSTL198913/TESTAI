import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.result import StepResult
from src.storage.repository import ResultRepository


@pytest.mark.asyncio
async def test_repository_concurrent_writes():
    """
    压力模拟：并发 100 次写入，验证存储层是否能处理高并发请求
    """

    # 模拟一个有网络延迟的数据库
    async def delayed_insert(*args, **kwargs):
        await asyncio.sleep(0.01)  # 模拟 10ms 的数据库响应时间
        return None

    # 1. 准备 Mock 环境
    mock_db = MagicMock()
    # 模拟 insert_one 需要返回一个 Future 对象 (在 motor 中是 Future)
    mock_collection = AsyncMock()
    mock_db.execution_results = mock_collection

    repo = ResultRepository(db=mock_db)

    # 2. 构造 100 个并发任务
    tasks = []
    for i in range(10000):
        # 使用 StepResult 契约
        result = StepResult(status="PASSED", status_code=200, body={"data": i})
        tasks.append(repo.save_execution(f"step_{i}", result.model_dump()))

    # 3. 并发执行
    await asyncio.gather(*tasks)

    # 4. 验证：确认 insert_one 被调用了 100 次
    assert mock_collection.insert_one.call_count == 10000


@pytest.mark.asyncio
async def test_repository_error_resilience():
    """
    稳定性模拟：验证数据库抛出异常时，Repository 是否正确封装并抛出 ConnectionError
    """
    mock_db = MagicMock()
    # 模拟数据库插入失败
    mock_db.execution_results.insert_one = AsyncMock(
        side_effect=Exception("DB Connection Lost")
    )

    repo = ResultRepository(db=mock_db)

    # 验证是否正确转换异常
    with pytest.raises(ConnectionError, match="Database write failed"):
        await repo.save_execution("step_fail", {"data": "fail"})
