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
        
        # 验证实现了必要的接口方法
        assert hasattr(repo, '__aenter__'), "Should implement __aenter__"
        assert hasattr(repo, '__aexit__'), "Should implement __aexit__"
        assert hasattr(repo, 'save_execution'), "Should implement save_execution"
    
    def test_fallback_is_thread_safe(self):
        """验证 fallback 机制在并发环境下是线程安全的。"""
        import threading
        
        mock_sqlite_repo = MagicMock()
        mock_sqlite_repo.__aenter__ = AsyncMock(return_value=mock_sqlite_repo)
        mock_sqlite_repo.__aexit__ = AsyncMock()
        mock_sqlite_repo.save_execution = AsyncMock()
        
        with patch('src.core.container.settings') as mock_settings:
            mock_settings.MONGO_URI = None
            with patch('src.core.container.SQLiteResultRepository', return_value=mock_sqlite_repo):
                errors = []
                results = []
                
                def get_repo_thread(thread_id):
                    try:
                        container = ResourceContainer()
                        repo = asyncio.run(container.get_repo())
                        
                        # 验证返回的是同一个 mock 对象
                        results.append(id(repo))
                        
                        asyncio.run(repo.save_execution(f"thread_test_{thread_id}", {"thread": thread_id}))
                        
                    except Exception as e:
                        errors.append((thread_id, str(e)))
                
                threads = [threading.Thread(target=get_repo_thread, args=(i,)) for i in range(5)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                
                # 验证没有错误
                assert len(errors) == 0, f"Thread errors: {errors}"
                
                # 验证所有线程获取的是同一个 repo 实例 (单例)
                assert len(set(results)) == 1, "All threads should get the same repo instance"
    
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
        
        # 验证方法存在
        assert hasattr(repo, '__aenter__'), "Should have __aenter__"
        assert hasattr(repo, '__aexit__'), "Should have __aexit__"
        assert hasattr(repo, 'save_execution'), "Should have save_execution"
    
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
