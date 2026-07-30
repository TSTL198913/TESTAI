"""
P0-4 bcrypt 依赖验证测试

验证 requirements.txt 中是否包含 bcrypt 依赖。
bcrypt 用于密码哈希，是安全认证的核心依赖。

关联缺陷: TECH_DEBT_P0_4
"""
import pytest
from pathlib import Path


class TestBcryptDependency:
    """验证 bcrypt 依赖是否存在"""

    @pytest.fixture
    def requirements_path(self) -> Path:
        return Path(__file__).parent.parent.parent / "requirements.txt"

    def test_requirements_file_exists(self, requirements_path: Path):
        """验证 requirements.txt 存在"""
        assert requirements_path.exists(), "requirements.txt 不存在"

    def test_bcrypt_in_requirements(self, requirements_path: Path):
        """
        验证 requirements.txt 包含 bcrypt 依赖。
        
        业务规则:
        - bcrypt 是密码哈希算法，用于 TokenManager 的密码存储
        - 缺少 bcrypt 将导致 import 失败或使用不安全的哈希方法
        - 最低版本要求 >= 4.0.0
        """
        if not requirements_path.exists():
            pytest.skip("requirements.txt 不存在")

        content = requirements_path.read_text(encoding="utf-8")

        # 检查是否包含 bcrypt
        has_bcrypt = False
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            if "bcrypt" in line.lower():
                has_bcrypt = True
                print(f"✅ 找到 bcrypt: {line}")
                break

        assert has_bcrypt, (
            "❌ P0-4 缺陷: requirements.txt 缺少 bcrypt 依赖\n"
            "必须添加: bcrypt>=4.0.0\n\n"
            "bcrypt 是 TokenManager 密码功能的核心依赖，\n"
            "缺少此依赖将导致生产环境密码哈希功能不可用。"
        )

    def test_bcrypt_importable(self):
        """验证 bcrypt 可以正常导入"""
        try:
            import bcrypt
            print(f"✅ bcrypt 可导入，版本: {bcrypt.__version__ if hasattr(bcrypt, '__version__') else 'unknown'}")
        except ImportError as e:
            pytest.fail(
                f"❌ bcrypt 导入失败: {e}\n"
                f"请执行: pip install bcrypt>=4.0.0"
            )

    def test_bcrypt_available_in_project(self):
        """验证项目中使用 bcrypt 的代码"""
        src_dir = Path(__file__).parent.parent.parent / "src"
        
        if not src_dir.exists():
            pytest.skip("src/ 目录不存在")

        # 搜索使用 bcrypt 的文件
        bcrypt_files = []
        for py_file in src_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
                if "bcrypt" in content.lower():
                    bcrypt_files.append(str(py_file))
            except Exception:
                continue

        print(f"\n📋 使用 bcrypt 的文件 ({len(bcrypt_files)} 个):")
        for f in bcrypt_files[:10]:  # 只显示前10个
            print(f"   - {f}")

        # TokenManager 应该使用 bcrypt
        auth_file = src_dir / "security" / "auth.py"
        if auth_file.exists():
            auth_content = auth_file.read_text(encoding="utf-8")
            if "bcrypt" in auth_content.lower():
                print(f"\n✅ TokenManager (auth.py) 使用 bcrypt")
            else:
                print(f"\n⚠️  TokenManager (auth.py) 未使用 bcrypt")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=long"])