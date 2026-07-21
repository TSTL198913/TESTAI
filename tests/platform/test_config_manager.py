"""
Platform ConfigManager测试 - 覆盖五种场景
目标覆盖率≥80%
"""
import pytest
import tempfile
import os
import json

from src.platform.config_manager import ConfigManager, ConfigSection


class TestConfigManager:
    """ConfigManager测试类"""

    def setup_method(self):
        """使用临时目录隔离测试数据"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "test_config.json")

    def teardown_method(self):
        """清理临时目录"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # === 正向场景 ===
    def test_get_section_returns_config(self):
        """正向：获取存在的配置节"""
        config = ConfigManager(config_file=self.config_file)
        result = config.get_section("platform")
        
        assert result is not None
        assert result.get("name") == "TestAI Platform"
        assert "description" in result
        assert result.get("version") == "1.0.0"
        assert result.get("debug") is False

    def test_get_all_returns_all_sections(self):
        """正向：获取所有配置节"""
        config = ConfigManager(config_file=self.config_file)
        result = config.get_all()
        
        assert isinstance(result, dict)
        assert "platform" in result
        assert "api" in result
        assert "workflow" in result
        assert "governance" in result
        assert "mutation_test" in result
        assert "monitoring" in result

    def test_update_section_modifies_config(self):
        """正向：更新配置节"""
        config = ConfigManager(config_file=self.config_file)
        config.update_section("api", {"port": 9000, "host": "127.0.0.1"})
        
        result = config.get_section("api")
        assert result["port"] == 9000
        assert result["host"] == "127.0.0.1"
        assert result["cors_enabled"] is True

    def test_set_value_updates_single_key(self):
        """正向：设置单个配置值"""
        config = ConfigManager(config_file=self.config_file)
        config.set_value("platform", "debug", True)
        
        result = config.get_section("platform")
        assert result["debug"] is True

    def test_get_value_returns_value(self):
        """正向：获取单个配置值"""
        config = ConfigManager(config_file=self.config_file)
        value = config.get_value("api", "port")
        
        assert value == 8000

    def test_add_section_creates_new_section(self):
        """正向：添加新配置节"""
        config = ConfigManager(config_file=self.config_file)
        config.add_section("new_section", {"key": "value"}, "New Section", readonly=False)
        
        result = config.get_section("new_section")
        assert result is not None
        assert result["key"] == "value"

    def test_remove_section_deletes_section(self):
        """正向：删除配置节"""
        config = ConfigManager(config_file=self.config_file)
        config.add_section("temp_section", {"data": "test"})
        
        assert config.get_section("temp_section") is not None
        
        config.remove_section("temp_section")
        assert config.get_section("temp_section") is None

    def test_list_sections_returns_list(self):
        """正向：列出所有配置节"""
        config = ConfigManager(config_file=self.config_file)
        sections = config.list_sections()
        
        assert isinstance(sections, list)
        assert len(sections) >= 6
        section_names = [s["name"] for s in sections]
        assert "platform" in section_names
        assert "api" in section_names

    # === 负向场景 ===
    def test_get_section_returns_none_for_nonexistent(self):
        """负向：获取不存在的配置节返回None"""
        config = ConfigManager(config_file=self.config_file)
        result = config.get_section("nonexistent")
        
        assert result is None

    def test_get_value_returns_default_for_nonexistent(self):
        """负向：获取不存在的键返回默认值"""
        config = ConfigManager(config_file=self.config_file)
        value = config.get_value("platform", "nonexistent_key", "default_value")
        
        assert value == "default_value"

    def test_add_existing_section_raises_error(self):
        """负向：添加已存在的配置节抛出异常"""
        config = ConfigManager(config_file=self.config_file)
        
        with pytest.raises(ValueError, match="already exists"):
            config.add_section("platform", {"test": "data"})

    def test_remove_nonexistent_section_raises_error(self):
        """负向：删除不存在的配置节抛出异常"""
        config = ConfigManager(config_file=self.config_file)
        
        with pytest.raises(ValueError, match="does not exist"):
            config.remove_section("nonexistent")

    def test_update_readonly_section_raises_error(self):
        """负向：更新只读配置节抛出异常"""
        config = ConfigManager(config_file=self.config_file)
        config.add_section("readonly_section", {"data": "test"}, readonly=True)
        
        with pytest.raises(PermissionError, match="readonly"):
            config.update_section("readonly_section", {"data": "modified"})

    def test_set_value_readonly_section_raises_error(self):
        """负向：在只读配置节设置值抛出异常"""
        config = ConfigManager(config_file=self.config_file)
        config.add_section("readonly_section", {"data": "test"}, readonly=True)
        
        with pytest.raises(PermissionError, match="readonly"):
            config.set_value("readonly_section", "key", "value")

    def test_remove_readonly_section_raises_error(self):
        """负向：删除只读配置节抛出异常"""
        config = ConfigManager(config_file=self.config_file)
        config.add_section("readonly_section", {"data": "test"}, readonly=True)
        
        with pytest.raises(PermissionError, match="readonly"):
            config.remove_section("readonly_section")

    # === 边界场景 ===
    def test_empty_config_file_loads_defaults(self):
        """边界：空配置文件加载默认配置"""
        empty_file = os.path.join(self.temp_dir, "empty.json")
        config = ConfigManager(config_file=empty_file)
        
        result = config.get_all()
        assert "platform" in result
        assert "api" in result

    def test_malformed_config_file_loads_defaults(self):
        """边界：格式错误的配置文件加载默认配置"""
        malformed_file = os.path.join(self.temp_dir, "malformed.json")
        with open(malformed_file, "w") as f:
            f.write("invalid json")
        
        config = ConfigManager(config_file=malformed_file)
        
        result = config.get_all()
        assert "platform" in result

    def test_config_file_not_exists_loads_defaults(self):
        """边界：配置文件不存在加载默认配置"""
        nonexistent_file = os.path.join(self.temp_dir, "nonexistent.json")
        config = ConfigManager(config_file=nonexistent_file)
        
        result = config.get_all()
        assert "platform" in result

    def test_update_empty_data(self):
        """边界：更新空数据"""
        config = ConfigManager(config_file=self.config_file)
        config.update_section("api", {})
        
        result = config.get_section("api")
        assert result is not None
        assert result["port"] == 8000

    def test_add_section_with_empty_data(self):
        """边界：添加空数据的配置节"""
        config = ConfigManager(config_file=self.config_file)
        config.add_section("empty_section", data=None)
        
        result = config.get_section("empty_section")
        assert result is not None

    def test_config_file_path_with_special_characters(self):
        """边界：配置文件路径包含特殊字符"""
        special_path = os.path.join(self.temp_dir, "config with spaces.json")
        config = ConfigManager(config_file=special_path)
        config.set_value("platform", "test", "value")
        
        assert os.path.exists(special_path)

    # === 依赖场景 ===
    def test_config_persistence_across_instances(self):
        """依赖：配置在不同实例间持久化"""
        config1 = ConfigManager(config_file=self.config_file)
        config1.set_value("platform", "persisted", True)
        
        config2 = ConfigManager(config_file=self.config_file)
        value = config2.get_value("platform", "persisted")
        
        assert value is True

    def test_config_file_format_preserved(self):
        """依赖：配置文件格式保持"""
        config = ConfigManager(config_file=self.config_file)
        config.update_section("api", {"port": 8080})
        
        with open(self.config_file, "r", encoding="utf-8") as f:
            content = f.read()
            data = json.loads(content)
        
        assert "api" in data
        assert data["api"]["data"]["port"] == 8080
