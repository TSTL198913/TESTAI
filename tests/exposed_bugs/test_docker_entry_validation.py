"""
P0-1 Dockerfile 入口验证测试

验证 Dockerfile 的 CMD 指令是否指向正确的 FastAPI 应用入口。
当前入口为 src.api.main (1路由)，应改为 src.platform.api (59路由)。

关联缺陷: TECH_DEBT_P0_1
"""
import pytest
from pathlib import Path


class TestDockerEntryValidation:
    """Dockerfile 入口验证"""

    @pytest.fixture
    def dockerfile_path(self) -> Path:
        return Path(__file__).parent.parent.parent / "Dockerfile"

    def test_dockerfile_exists(self, dockerfile_path: Path):
        """Dockerfile 必须存在"""
        assert dockerfile_path.exists(), "Dockerfile 不存在，无法验证入口"

    def test_cmd_points_to_platform_api(self, dockerfile_path: Path):
        """
        验证 Dockerfile 的 CMD 指令指向 src.platform.api。
        
        业务规则:
        - src.platform.api:app 挂载了所有 59 个路由（auth/users/teams/governance 等）
        - src.api.main:app 仅挂载了基础路由（health/metrics 等）
        - Dockerfile 应使用 src.platform.api 作为生产入口
        
        此测试将验证 CMD 行是否包含 src.platform.api。
        """
        if not dockerfile_path.exists():
            pytest.skip("Dockerfile 不存在")

        content = dockerfile_path.read_text(encoding="utf-8")
        cmd_lines = []

        # 查找所有包含 CMD 指令的行
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("CMD") or "CMD [" in stripped:
                cmd_lines.append(stripped)

        # 必须有 CMD 指令
        assert len(cmd_lines) > 0, "Dockerfile 中未找到 CMD 指令"

        # 验证至少一个 CMD 行包含 src.platform.api
        platform_api_found = any(
            "src.platform.api" in line for line in cmd_lines
        )

        # 验证不存在指向 src.api.main 的 CMD
        old_entry_found = any(
            "src.api.main" in line for line in cmd_lines
        )

        # 断言: 入口必须是 src.platform.api，不能是 src.api.main
        assert platform_api_found, (
            f"❌ Dockerfile 入口错误!\n"
            f"当前 CMD 行:\n"
            f"{chr(10).join(cmd_lines)}\n\n"
            f"预期: CMD 应指向 src.platform.api:app (59路由)\n"
            f"实际: 未找到 src.platform.api 引用"
        )

        if old_entry_found:
            pytest.fail(
                f"❌ Dockerfile 仍使用旧入口 src.api.main:app!\n"
                f"这是 P0-1 缺陷，应改为 src.platform.api:app"
            )

        print(f"✅ Dockerfile 入口验证通过")
        print(f"   CMD 行: {cmd_lines[0]}")
        print(f"   入口: src.platform.api:app (59路由)")

    def test_no_dev_dependencies_in_production(self, dockerfile_path: Path):
        """
        验证生产 Dockerfile 不安装开发依赖。
        
        业务规则:
        - 生产镜像应最小化，仅包含必要运行时依赖
        - pip install -e ".[dev]" 会安装 pytest/pylint 等开发工具
        - 正确做法: pip install . 或 pip install -r requirements.txt
        """
        if not dockerfile_path.exists():
            pytest.skip("Dockerfile 不存在")

        content = dockerfile_path.read_text(encoding="utf-8")

        # 检查是否包含 [dev] 安装
        has_dev_install = "[dev]" in content and "pip install" in content

        if has_dev_install:
            pytest.fail(
                f"❌ Dockerfile 安装了开发依赖!\n"
                f"包含 [dev] 的 pip install 指令会增大镜像体积\n"
                f"应改为: pip install . 或 pip install -r requirements.txt"
            )

        print("✅ 生产依赖验证通过 (无 [dev] 安装)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])