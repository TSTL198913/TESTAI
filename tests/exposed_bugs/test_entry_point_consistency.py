"""
入口一致性守卫测试

验证项目中所有指向 FastAPI 应用入口的引用都使用治理平台入口
(src.platform.api:app), 而非旧的测试+AI平台入口 (src.api.main:app)。

背景:
  Dockerfile 已修正为 src.platform.api:app (由 test_docker_entry_validation.py 守卫),
  但 start.sh / README.md / 部署文档仍指向旧入口 src.api.main:app。

  这导致 dev/prod 环境入口不一致:
  - Docker(生产): src.platform.api:app (有治理端点) ✅
  - start.sh(开发): src.api.main:app (无治理端点) ❌

  开发者用 start.sh 启动后, /governance/* 端点全部 404, 治理功能无法在开发环境验证。

业务规则:
  - 治理平台入口 src.platform.api:app 注册了全部 60 条路由 (治理+监控+认证+工作流)
  - 旧入口 src.api.main:app 仅注册 6 条基础路由 (health/metrics/execute/tasks/baselines/evaluate)
  - 所有启动脚本、文档中的 uvicorn 命令必须指向 src.platform.api:app
"""
import pytest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestStartScriptEntry:
    """验证 start.sh 的启动入口。"""

    @pytest.fixture
    def start_sh_path(self) -> Path:
        return PROJECT_ROOT / "start.sh"

    @pytest.fixture
    def start_sh_content(self, start_sh_path) -> str:
        if not start_sh_path.exists():
            pytest.skip("start.sh 不存在")
        return start_sh_path.read_text(encoding="utf-8")

    def test_start_sh_does_not_use_old_entry(self, start_sh_content):
        """start.sh 中不得出现 src.api.main:app (旧入口)。"""
        assert "src.api.main:app" not in start_sh_content, (
            "❌ start.sh 仍使用旧入口 src.api.main:app!\n"
            "旧入口仅注册 6 条基础路由, 无治理端点 (/governance/*)。\n"
            "开发环境无法测试治理功能。应改为 src.platform.api:app。"
        )

    def test_start_sh_uses_platform_api(self, start_sh_content):
        """start.sh 中必须使用 src.platform.api:app (治理平台入口)。"""
        assert "src.platform.api:app" in start_sh_content, (
            "❌ start.sh 未使用 src.platform.api:app!\n"
            "应将 uvicorn src.api.main:app 改为 uvicorn src.platform.api:app。"
        )

    def test_start_sh_dev_mode_uses_correct_entry(self, start_sh_content):
        """start_dev() 函数必须使用 src.platform.api:app。"""
        # 找到 start_dev 函数体, 验证其中的 uvicorn 命令
        lines = start_sh_content.splitlines()
        in_dev = False
        dev_uvicorn_lines = []
        for line in lines:
            if "start_dev()" in line or "start_dev (" in line:
                in_dev = True
            elif in_dev and (line.startswith("start_") or line.startswith("}")):
                in_dev = False
            elif in_dev and "uvicorn" in line:
                dev_uvicorn_lines.append(line.strip())

        assert len(dev_uvicorn_lines) > 0, "start_dev() 中未找到 uvicorn 命令"
        for line in dev_uvicorn_lines:
            assert "src.platform.api:app" in line, (
                f"start_dev() 的 uvicorn 命令未指向 src.platform.api:app:\n  {line}"
            )

    def test_start_sh_prod_mode_uses_correct_entry(self, start_sh_content):
        """start_prod() 函数必须使用 src.platform.api:app。"""
        lines = start_sh_content.splitlines()
        in_prod = False
        prod_uvicorn_lines = []
        for line in lines:
            if "start_prod()" in line or "start_prod (" in line:
                in_prod = True
            elif in_prod and (line.startswith("start_") or line.startswith("}")):
                in_prod = False
            elif in_prod and "uvicorn" in line:
                prod_uvicorn_lines.append(line.strip())

        assert len(prod_uvicorn_lines) > 0, "start_prod() 中未找到 uvicorn 命令"
        for line in prod_uvicorn_lines:
            assert "src.platform.api:app" in line, (
                f"start_prod() 的 uvicorn 命令未指向 src.platform.api:app:\n  {line}"
            )


class TestReadmeEntry:
    """验证 README.md 中的启动命令。"""

    @pytest.fixture
    def readme_content(self) -> str:
        readme = PROJECT_ROOT / "README.md"
        if not readme.exists():
            pytest.skip("README.md 不存在")
        return readme.read_text(encoding="utf-8")

    def test_readme_does_not_use_old_entry(self, readme_content):
        """README.md 中不得出现 src.api.main:app。"""
        assert "src.api.main:app" not in readme_content, (
            "❌ README.md 仍引用旧入口 src.api.main:app!\n"
            "应改为 src.platform.api:app。"
        )

    def test_readme_uses_platform_api(self, readme_content):
        """README.md 中应使用 src.platform.api:app。"""
        assert "src.platform.api:app" in readme_content, (
            "README.md 未引用 src.platform.api:app — 启动命令应指向治理平台入口"
        )


class TestDockerfileEntry:
    """验证 Dockerfile 入口 (已有 test_docker_entry_validation.py, 此处做交叉验证)。"""

    @pytest.fixture
    def dockerfile_content(self) -> str:
        dockerfile = PROJECT_ROOT / "Dockerfile"
        if not dockerfile.exists():
            pytest.skip("Dockerfile 不存在")
        return dockerfile.read_text(encoding="utf-8")

    def test_dockerfile_uses_platform_api(self, dockerfile_content):
        assert "src.platform.api:app" in dockerfile_content

    def test_dockerfile_does_not_use_old_entry(self, dockerfile_content):
        assert "src.api.main:app" not in dockerfile_content


class TestEntryPointRouteCount:
    """验证治理平台入口确实注册了远多于旧入口的路由。

    防止有人"修正"入口但 api.py 实际没注册足够路由的假绿场景。
    """

    def test_platform_api_has_governance_routes(self):
        """src.platform.api:app 必须注册治理端点。"""
        from src.platform.api import app
        paths = {getattr(r, "path", None) for r in app.routes}
        governance_paths = {
            "/governance/execute",
            "/governance/approvals",
            "/governance/tracker/events",
            "/governance/tracker/summary",
            "/governance/baselines",
            "/monitoring/alerts",
            "/monitoring/metrics",
        }
        missing = governance_paths - paths
        assert not missing, f"治理平台入口缺少治理路由: {missing}"

    def test_platform_api_route_count_exceeds_old_entry(self):
        """治理平台入口路由数必须显著多于旧入口(6条)。

        旧入口 src.api.main:app 仅注册:
        /health, /metrics, /execute, /tasks/{task_id}, /baselines, /evaluate
        """
        from src.platform.api import app
        route_count = len([r for r in app.routes if hasattr(r, "path")])
        assert route_count > 20, (
            f"治理平台入口路由数仅 {route_count}, 预期远超旧入口的 6 条 — "
            f"可能 api.py 加载不完整或路由注册失败"
        )
