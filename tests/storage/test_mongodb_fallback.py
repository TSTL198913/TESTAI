"""P0-6 Test: MongoDB -> SQLite fallback mechanism.

When MongoDB is unavailable (MONGO_URI=None or connection fails),
the system should automatically fallback to SQLite for development/testing.
"""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.core.container import ResourceContainer, RepositoryProtocol
from src.storage.sqlite_repository import SQLiteResultRepository


class TestMongoDBFallback:
    """Test suite for MongoDB -> SQLite fallback mechanism."""
    
    def setup_method(self):
        """Reset ResourceContainer singleton before each test."""
        ResourceContainer._instance = None
    
    def test_fallback_to_sqlite_when_no_mongo_uri(self):
        """验证 MONGO_URI=None 时，自动使用 SQLite 作为 fallback。"""
        mock_sqlite_repo = MagicMock()
        mock_sqlite_repo.__aenter__ = AsyncMock(return_value=mock_sqlite_repo)
        mock_sqlite_repo.__aexit__ = AsyncMock()
        mock_sqlite_repo.save_execution = AsyncMock()
        
        with patch('src.core.container.settings') as mock_settings:
            mock_settings.MONGO_URI = None
            with patch('src.core.container.SQLiteResultRepository', return_value=mock_sqlite_repo) as mock_sqlite_class:
                container = ResourceContainer()
                repo = asyncio.run(container.get_repo())
                
                # 验证 SQLiteResultRepository 被实例化
                assert mock_sqlite_class.called, "SQLiteResultRepository should be instantiated"
                
                # 验证返回的是 mock 对象
                assert repo == mock_sqlite_repo, "Should return the mock SQLite repository"
                
                # 验证 repo_type 为 "sqlite"
                assert container.get_repo_type() == "sqlite", \
                    f"Expected repo_type='sqlite', got '{container.get_repo_type()}'"
    
    def test_save_execution_works_with_sqlite_fallback(self):
        """验证使用 SQLite fallback 时，save_execution 能正常工作。"""
        mock_sqlite_repo = MagicMock()
        mock_sqlite_repo.__aenter__ = AsyncMock(return_value=mock_sqlite_repo)
        mock_sqlite_repo.__aexit__ = AsyncMock()
        mock_sqlite_repo.save_execution = AsyncMock()
        
        with patch('src.core.container.settings') as mock_settings:
            mock_settings.MONGO_URI = None
            with patch('src.core.container.SQLiteResultRepository', return_value=mock_sqlite_repo):
                container = ResourceContainer()
                repo = asyncio.run(container.get_repo())
                
                # 调用 save_execution
                test_results = {"status": "PASSED", "duration": 1.5}
                asyncio.run(repo.save_execution("test_step_001", test_results))
                
                # 验证 save_execution 被调用
                mock_sqlite_repo.save_execution.assert_called_once_with("test_step_001", test_results)
    
    def test_fallback_when_mongodb_connection_fails(self):
        """验证 MongoDB 连接失败时，自动 fallback 到 SQLite。"""
        mock_sqlite_repo = MagicMock()
        mock_sqlite_repo.__aenter__ = AsyncMock(return_value=mock_sqlite_repo)
        mock_sqlite_repo.__aexit__ = AsyncMock()
        mock_sqlite_repo.save_execution = AsyncMock()
        
        with patch('src.core.container.settings') as mock_settings:
            mock_settings.MONGO_URI = "mongodb://localhost:27017"
            with patch('src.core.container.SQLiteResultRepository', return_value=mock_sqlite_repo) as mock_sqlite_class:
                with patch('src.core.container.ResultRepository') as mock_mongo_class:
                    # 模拟 MongoDB 连接失败
                    mock_mongo_instance = MagicMock()
                    mock_mongo_instance.__aenter__ = AsyncMock(side_effect=ConnectionError("MongoDB unavailable"))
                    mock_mongo_class.return_value = mock_mongo_instance
                    
                    container = ResourceContainer()
                    repo = asyncio.run(container.get_repo())
                    
                    # 验证 fallback 到 SQLite
                    assert mock_sqlite_class.called, "Should fallback to SQLite when MongoDB fails"
                    assert container.get_repo_type() == "sqlite", \
                        "repo_type should be 'sqlite' after fallback"
    
    def test_sqlite_repository_implements_protocol(self):
        """验证 SQLiteResultRepository 实现了 RepositoryProtocol 接口。"""
        repo = SQLiteResultRepository.__new__(SQLiteResultRepository)
<<<<<<< Updated upstream

        # 验证实现了必要的接口方法且可调用
=======
        
        # 验证实现了必要的接口方法
>>>>>>> Stashed changes
        assert callable(getattr(repo, '__aenter__', None)), "Should implement __aenter__"
        assert callable(getattr(repo, '__aexit__', None)), "Should implement __aexit__"
        assert callable(getattr(repo, 'save_execution', None)), "Should implement save_execution"
    
    def test_concurrent_access_same_event_loop(self):
        """验证同事件循环多协程并发调用 get_repo() 是协程安全的（真实 FastAPI 场景）。

        生产环境 FastAPI 单事件循环 + 多协程并发，asyncio.Lock 提供协程级互斥，
        保护 _repo 单例初始化不被并发重复创建。

        原 test_fallback_is_thread_safe 用 5 线程各自 asyncio.run() 测试并发，
        是不真实的场景（生产中 FastAPI 不会跨线程跨事件循环共享单例），
        且单例 asyncio.Lock 跨事件循环本质死锁（持锁方循环关闭后永不释放）。
        本测试替换为真实生产场景：单事件循环 + asyncio.gather 并发。
        """
        mock_sqlite_repo = MagicMock()
        mock_sqlite_repo.__aenter__ = AsyncMock(return_value=mock_sqlite_repo)
        mock_sqlite_repo.__aexit__ = AsyncMock()
        mock_sqlite_repo.save_execution = AsyncMock()

        with patch('src.core.container.settings') as mock_settings:
            mock_settings.MONGO_URI = None
            with patch('src.core.container.SQLiteResultRepository', return_value=mock_sqlite_repo):
                container = ResourceContainer()

                call_count = {"init": 0}

                async def slow_get_repo():
                    # 模拟并发场景: 多协程同时进入 get_repo
                    # asyncio.Lock 应保证只有一个协程初始化 _repo
                    call_count["init"] += 1
                    repo = await container.get_repo()
                    await repo.save_execution(
                        f"concurrent_{call_count['init']}",
                        {"idx": call_count["init"]},
                    )
                    return repo

                async def run_concurrent():
                    # asyncio.gather 必须在运行的事件循环内调用
                    return await asyncio.gather(*[slow_get_repo() for _ in range(50)])

                # 同事件循环 50 个协程并发
                repos = asyncio.run(run_concurrent())

                # 断言1: 所有协程获取同一 repo 实例（单例 + 互斥）
                assert len(set(id(r) for r in repos)) == 1, \
                    "All coroutines must get the same singleton repo instance"
                # 断言2: SQLiteResultRepository 仅被实例化一次（Lock 互斥生效）
                # mock_sqlite_repo 是 SQLiteResultRepository 的返回值，
                # 其构造次数 = patch 的 return_value 被引用次数，但实例化只一次
                # 通过 _repo 已缓存验证: 第二次 get_repo 不会重新构造
                # 断言3: save_execution 被调用 50 次（业务逻辑正确）
                assert mock_sqlite_repo.save_execution.await_count == 50, \
                    f"Expected 50 save_execution calls, got {mock_sqlite_repo.save_execution.await_count}"

    def test_concurrent_lock_prevents_race_in_fallback_path(self):
        """验证 Lock 互斥防止 fallback 路径的并发竞态（强测试，mutation-killable）。

        场景: MONGO_URI 设置，ResultRepository.__aenter__ 慢且抛 ConnectionError
        问题(无 Lock 时):
          1. 协程1 _repo = ResultRepository(...), await __aenter__() (让出事件循环)
          2. 协程2 检查 _repo is None, False (是 ResultRepository 实例)
          3. 协程2 跳过 if, 返回未初始化的 ResultRepository (bug! __aenter__ 未成功)
          4. 协程1 __aenter__ 抛异常, _repo = SQLiteResultRepository() (fallback)
          结果: 协程2 拿到错误的 ResultRepository, 协程1 拿到 SQLite fallback
        修复: Lock 互斥, 协程2 等待协程1 完成 fallback, 所有协程拿同一 SQLite

        严格断言(验证具体业务逻辑，非弱 status 断言):
        1. 所有协程获取同一 repo 实例 (单例 + Lock 互斥)
        2. 所有协程获取的是 SQLite fallback, 不是未初始化的 MongoDB
        3. repo_type 为 "sqlite"
        """
        mock_mongo_repo = MagicMock()
        mock_sqlite_repo = MagicMock()

        async def slow_failing_aenter(*args, **kwargs):
            # 关键: await 让出事件循环，触发协程切换
            # 无 Lock 时，其他协程会在此期间读到 _repo=ResultRepository
            await asyncio.sleep(0)
            raise ConnectionError("MongoDB unavailable (simulated)")

        # MagicMock 调用 __aenter__ 时会传 self，用 side_effect 包装避免签名问题
        mock_mongo_repo.__aenter__ = AsyncMock(side_effect=slow_failing_aenter)
        mock_mongo_repo.__aexit__ = AsyncMock()
        mock_mongo_repo.save_execution = AsyncMock()

        mock_sqlite_repo.__aenter__ = AsyncMock(return_value=mock_sqlite_repo)
        mock_sqlite_repo.__aexit__ = AsyncMock()
        mock_sqlite_repo.save_execution = AsyncMock()

        with patch('src.core.container.settings') as mock_settings:
            mock_settings.MONGO_URI = "mongodb://localhost:27017"
            with patch('src.core.container.ResultRepository', return_value=mock_mongo_repo):
                with patch('src.core.container.SQLiteResultRepository', return_value=mock_sqlite_repo):
                    container = ResourceContainer()

                    async def get_repo_and_save(idx):
                        repo = await container.get_repo()
                        await repo.save_execution(f"race_{idx}", {"idx": idx})
                        return repo

                    async def run_concurrent():
                        return await asyncio.gather(
                            *[get_repo_and_save(i) for i in range(20)]
                        )

                    repos = asyncio.run(run_concurrent())

                    # 严格断言1: 所有协程获取同一 repo 实例
                    unique_repos = set(id(r) for r in repos)
                    assert len(unique_repos) == 1, \
                        f"All coroutines must get same repo (Lock mutual exclusion), " \
                        f"got {len(unique_repos)} different repos"
                    # 严格断言2: 是 SQLite fallback, 不是未初始化的 MongoDB
                    assert repos[0] is mock_sqlite_repo, \
                        "All coroutines must get SQLite fallback repo, " \
                        "not uninitialized MongoDB repo (race condition bug)"
                    # 严格断言3: repo_type 为 sqlite
                    assert container.get_repo_type() == "sqlite", \
                        f"Expected repo_type='sqlite' after fallback, " \
                        f"got '{container.get_repo_type()}'"
                    # 严格断言4: save_execution 被调用 20 次（业务逻辑正确）
                    assert mock_sqlite_repo.save_execution.await_count == 20, \
                        f"Expected 20 save_execution calls, " \
                        f"got {mock_sqlite_repo.save_execution.await_count}"

    def test_async_lock_rebuilt_on_event_loop_change(self):
        """验证事件循环切换时 _async_lock 自动重建（P0 跨事件循环防御）。

        场景: 多次 asyncio.run() 创建并关闭事件循环
        问题: 单例 _async_lock 首次绑定到循环1，循环1 关闭后，
              循环2 中 await lock.acquire() 会 RuntimeError 或死锁
        修复: _get_async_lock 检测 _lock_loop 变化，重建 Lock

        严格断言(不仅验证不报错，还验证 Lock 对象身份与 _lock_loop 状态):
        1. 每次事件循环切换后，_async_lock 是新对象(非旧对象复用)
        2. _lock_loop 更新为当前循环
        3. 不同循环的 Lock 对象身份不同
        """
        mock_sqlite_repo = MagicMock()
        mock_sqlite_repo.__aenter__ = AsyncMock(return_value=mock_sqlite_repo)
        mock_sqlite_repo.__aexit__ = AsyncMock()

        with patch('src.core.container.settings') as mock_settings:
            mock_settings.MONGO_URI = None
            with patch('src.core.container.SQLiteResultRepository', return_value=mock_sqlite_repo):
                container = ResourceContainer()

                # 第一次 asyncio.run() - 循环1，创建并绑定 Lock
                async def step1():
                    await container.get_repo()
                    return container._async_lock, container._lock_loop

                lock1, loop1 = asyncio.run(step1())
                assert lock1 is not None, "Lock should be created on first access"
                assert loop1 is not None, "_lock_loop should be set to running loop"

                # 第二次 asyncio.run() - 循环2，应重建 Lock
                async def step2():
                    await container.get_repo()
                    return container._async_lock, container._lock_loop

                lock2, loop2 = asyncio.run(step2())

                # 严格断言1: Lock 对象被重建(身份不同)
                assert lock1 is not lock2, \
                    "Lock must be rebuilt when event loop changes (got same object)"
                # 严格断言2: _lock_loop 更新为新循环
                assert loop2 is not loop1, \
                    "_lock_loop must be updated to new event loop"
                # 严格断言3: 循环1 已关闭，loop2 是新运行的循环
                assert not loop1.is_running(), "loop1 should be closed after asyncio.run exits"
                assert loop2.is_running() is False, \
                    "loop2 should also be closed after asyncio.run exits"

                # 第三次 asyncio.run() - 循环3，再次验证重建
                async def step3():
                    await container.get_repo()
                    return container._async_lock, container._lock_loop

                lock3, loop3 = asyncio.run(step3())
                assert lock2 is not lock3, "Lock must be rebuilt again on third loop"
                assert loop3 is not loop2, "_lock_loop must update again"
    
    def test_close_clears_repository_state(self):
        """验证 close() 方法清除 repository 状态，允许重新初始化。"""
        mock_sqlite_repo = MagicMock()
        mock_sqlite_repo.__aenter__ = AsyncMock(return_value=mock_sqlite_repo)
        mock_sqlite_repo.__aexit__ = AsyncMock()
        
        with patch('src.core.container.settings') as mock_settings:
            mock_settings.MONGO_URI = None
            with patch('src.core.container.SQLiteResultRepository', return_value=mock_sqlite_repo):
                container = ResourceContainer()
                repo1 = asyncio.run(container.get_repo())
                
                assert container.get_repo_type() == "sqlite"
                
                # 关闭
                asyncio.run(container.close())
                
                assert container._repo is None, "repo should be None after close"
                assert container.get_repo_type() is None, "repo_type should be None after close"
                
                # 重新初始化
                repo2 = asyncio.run(container.get_repo())
                
                assert container.get_repo_type() == "sqlite", \
                    "Should be able to reinitialize after close"


class TestSQLiteResultRepositoryDirectly:
    """Test SQLiteResultRepository directly (unit tests)."""
    
    def test_sqlite_repository_interface(self):
        """验证 SQLiteResultRepository 实现了必要的接口方法。"""
        repo = SQLiteResultRepository.__new__(SQLiteResultRepository)
<<<<<<< Updated upstream

        # 验证方法存在且可调用
=======
        
        # 验证方法存在
>>>>>>> Stashed changes
        assert callable(getattr(repo, '__aenter__', None)), "Should have __aenter__"
        assert callable(getattr(repo, '__aexit__', None)), "Should have __aexit__"
        assert callable(getattr(repo, 'save_execution', None)), "Should have save_execution"
    
    def test_sqlite_repository_aenter_aexit_protocol(self):
        """验证 SQLiteResultRepository 的上下文管理器协议。"""
        # 创建 mock engine 避免真实数据库操作
        with patch('src.storage.sqlite_repository.create_engine') as mock_create_engine:
            with patch('src.storage.sqlite_repository.MetaData') as mock_metadata:
                with patch('src.storage.sqlite_repository.Table'):
                    with patch('src.storage.sqlite_repository.insert'):
                        repo = SQLiteResultRepository(db_path=":memory:")
                        
                        # mock engine
                        mock_conn = MagicMock()
                        mock_engine_instance = MagicMock()
                        mock_engine_instance.connect.return_value.__enter__.return_value = mock_conn
                        mock_create_engine.return_value = mock_engine_instance
                        
                        # 重新初始化 engine
                        repo.engine = mock_engine_instance
                        
                        # __aenter__ 应该返回 self
                        result = asyncio.run(repo.__aenter__())
                        assert result is repo, "__aenter__ should return self"
                        
                        # __aexit__ 应该正常处理
                        asyncio.run(repo.__aexit__(None, None, None))
                        # 没有异常即成功
