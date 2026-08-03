import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from src.core.container import ResourceContainer


# =============================================================================
# __init__ 幂等性测试 (Mutations L39, L41)
# =============================================================================
class TestInitIdempotency:
    def test_first_init_sets_initialized_true(self):
        """L41: 首次 __init__ 必须将 _initialized 设为 True"""
        c = ResourceContainer()
        # 必须先删除属性才能触发首次初始化路径
        if hasattr(c, '_initialized'):
            delattr(c, '_initialized')
        c.__init__()
        assert c._initialized is True, (
            "KILL-L41: __init__ 必须设置 _initialized=True；"
            "若变异为 False，则幂等性检查失效，__init__ 可被重复触发"
        )

    def test_second_init_returns_early_without_side_effects(self):
        """L39 negate: _initialized=True 时再次调用 __init__ 必须立即返回，不改变状态"""
        c = ResourceContainer()
        c._initialized = True
        old_client = c._client
        old_repo = c._repo
        old_repo_type = c._repo_type

        c.__init__()

        assert c._initialized is True
        assert c._client == old_client, (
            "KILL-L39: 二次 __init__ 必须立即返回，不应修改 _client；"
            "若 hasattr 检查被取反，会导致 _client 被错误重置"
        )
        assert c._repo == old_repo
        assert c._repo_type == old_repo_type


# =============================================================================
# get_client 全新创建路径 (Mutation L60)
# =============================================================================
class TestGetClientFreshCreation:
    def test_get_client_when_none_creates_new(self):
        """L60: _client is None 时必须创建新 AsyncClient"""
        c = ResourceContainer()
        c._client = None

        async def _run():
            with patch('src.core.container.httpx.AsyncClient') as mock_class:
                new_client = Mock()
                new_client.is_closed = False
                mock_class.return_value = new_client

                result = await c.get_client()

                assert mock_class.call_count == 1, (
                    "KILL-L60: _client 为 None 时必须创建新 client；"
                    "若变异为 is not None，则跳过创建，返回 None 或旧实例"
                )
                assert result is new_client
                assert c._client is new_client

        asyncio.run(_run())


# =============================================================================
# get_client 复用已有开放 client (Mutation L45)
# =============================================================================
class TestGetClientReuse:
    def test_get_client_reuses_open_client_without_creating_new(self):
        """L45: _client 非 None 且未关闭时必须直接返回现有实例"""
        c = ResourceContainer()
        existing = Mock()
        existing.is_closed = False
        existing.aclose = AsyncMock()
        c._client = existing

        async def _run():
            # 关键：设置 _loop 为当前事件循环，避免触发循环检查分支
            existing._loop = asyncio.get_running_loop()

            with patch('src.core.container.httpx.AsyncClient') as mock_class:
                result = await c.get_client()

                assert mock_class.call_count == 0, (
                    "KILL-L45: 已有开放 client 时不得创建新实例；"
                    "若 is not None 被变异为 is None，会错误地创建新 client"
                )
                assert result is existing, (
                    "KILL-L45: 必须返回现有实例，不是新建或其他对象"
                )

        asyncio.run(_run())


# =============================================================================
# get_client 替换已关闭 client (Mutation L46)
# =============================================================================
class TestGetClientClosedReplacement:
    def test_closed_client_gets_replaced(self):
        """L46: _client 已关闭时必须清空并创建新实例"""
        c = ResourceContainer()
        closed_client = Mock()
        closed_client.is_closed = True
        closed_client.aclose = AsyncMock()
        c._client = closed_client

        async def _run():
            with patch('src.core.container.httpx.AsyncClient') as mock_class:
                new_client = Mock()
                new_client.is_closed = False
                mock_class.return_value = new_client

                result = await c.get_client()

                assert mock_class.call_count == 1, (
                    "KILL-L46: 已关闭 client 必须被替换；"
                    "若 is_closed 检查被取反，则已关闭 client 会被当作有效实例返回"
                )
                assert result is new_client
                assert c._client is new_client

        asyncio.run(_run())


# =============================================================================
# get_client 事件循环不匹配处理 (Mutations L51, L53)
# =============================================================================
class TestGetClientLoopMismatch:
    def test_different_loop_client_gets_closed_and_replaced(self):
        """L51+L53: client._loop != current_loop 时必须关闭旧 client 并新建"""
        c = ResourceContainer()
        old_client = Mock()
        old_client.is_closed = False
        old_client._loop = object()  # 不同的事件循环
        old_client.aclose = AsyncMock()
        c._client = old_client

        async def _run():
            current_loop = asyncio.get_running_loop()

            with patch('src.core.container.httpx.AsyncClient') as mock_class:
                new_client = Mock()
                new_client.is_closed = False
                mock_class.return_value = new_client

                result = await c.get_client()

                assert old_client.aclose.await_count == 1, (
                    "KILL-L51/L53: 事件循环不匹配时必须调用 aclose() 关闭旧 client；"
                    "若条件被取反或 != 变为 ==，旧 client 不会被关闭"
                )
                assert mock_class.call_count == 1, (
                    "KILL-L51/L53: 必须创建新 client 替换循环不匹配的旧实例"
                )
                assert result is new_client

        asyncio.run(_run())

    def test_same_loop_client_is_reused_not_closed(self):
        """L51+L53: client._loop == current_loop 时必须复用，不得关闭"""
        c = ResourceContainer()
        mock_client = Mock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        c._client = mock_client

        async def _run():
            current_loop = asyncio.get_running_loop()
            mock_client._loop = current_loop

            with patch('src.core.container.httpx.AsyncClient') as mock_class:
                result = await c.get_client()

                assert mock_class.call_count == 0, (
                    "KILL-L51/L53: 相同事件循环时不得创建新 client"
                )
                assert mock_client.aclose.await_count == 0, (
                    "KILL-L51/L53: 相同事件循环时不得关闭现有 client"
                )
                assert result is mock_client

        asyncio.run(_run())


# =============================================================================
# reset_client 方法测试 (Mutations L67, L68)
# =============================================================================
class TestResetClient:
    def test_reset_closes_open_client_and_sets_none(self):
        """L67+L68: 有未关闭 client 时，reset 必须关闭它并清空引用"""
        c = ResourceContainer()
        mock_client = Mock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        c._client = mock_client

        async def _run():
            await c.reset_client()

            assert mock_client.aclose.await_count == 1, (
                "KILL-L67/L68: reset_client 必须对未关闭 client 调用 aclose()；"
                "若条件被取反，则 open client 不会被关闭，造成资源泄漏"
            )
            assert c._client is None, (
                "KILL-L67/L68: reset_client 必须将 _client 置为 None"
            )

        asyncio.run(_run())

    def test_reset_on_already_closed_client_is_safe(self):
        """L68: 已关闭 client 调用 reset 不应重复调用 aclose"""
        c = ResourceContainer()
        closed_client = Mock()
        closed_client.is_closed = True
        closed_client.aclose = AsyncMock()
        c._client = closed_client

        async def _run():
            await c.reset_client()

            assert closed_client.aclose.await_count == 0, (
                "KILL-L68: 已关闭 client 不应重复调用 aclose()；"
                "若 not is_closed 被变异为 is_closed，会对已关闭 client 重复调用 aclose"
            )
            assert c._client is None

        asyncio.run(_run())

    def test_reset_when_no_client_is_idempotent(self):
        """L67: _client 为 None 时调用 reset 不应报错"""
        c = ResourceContainer()
        c._client = None

        async def _run():
            await c.reset_client()
            assert c._client is None, (
                "KILL-L67: _client 为 None 时 reset 必须安全无副作用；"
                "若 if self._client 被取反，None 情况下会尝试访问 aclose 而报错"
            )

        asyncio.run(_run())


# =============================================================================
# 原有测试：get_repo 和 close（已验证可杀死 7 个变异）
# =============================================================================
class TestRepoResourceLeak:
    def test_repo_not_initialized_calls_aenter(self):
        """测试get_repo在repo未初始化时正确调用__aenter__"""
        container = ResourceContainer()
        container._initialized = False
        container.__init__()
        container._repo = None

        mock_repo_class = Mock()
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        async def _run():
            with patch('src.core.container.ResultRepository', mock_repo_class):
                await container.get_repo()
                assert mock_repo_class.call_count == 1
                assert mock_repo.__aenter__.await_count == 1

        asyncio.run(_run())

    def test_repo_already_exists_no_reinitialization(self):
        """测试repo已存在时不会重新初始化"""
        container = ResourceContainer()
        container._initialized = False
        container.__init__()

        mock_repo = AsyncMock()

        async def _run():
            container._repo = mock_repo
            await container.get_repo()
            assert mock_repo.__aenter__.await_count == 0

        asyncio.run(_run())

    def test_close_calls_aexit(self):
        """测试close方法正确调用__aexit__"""
        container = ResourceContainer()
        container._initialized = False
        container.__init__()

        mock_repo = AsyncMock()
        mock_client = AsyncMock()
        mock_client.is_closed = False

        async def _run():
            container._repo = mock_repo
            container._client = mock_client
            await container.close()
            assert mock_repo.__aexit__.await_count == 1
            assert mock_client.aclose.await_count == 1

        asyncio.run(_run())
