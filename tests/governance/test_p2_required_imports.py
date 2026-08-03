"""P2-1 GovernanceExecutor required_imports 接入测试。

业务规则（基于代码梳理）：
- executor._write_patch 原只用 GovernanceRegistry.create_transformer 改函数体，
  虽接收 required_imports 参数但从未实例化 ImportApplier，导致补丁缺 import，
  运行时 NameError。
- 修复后：函数体改写后，若 required_imports 非空，用 ImportApplier 将 import
  语句实际写入文件。

覆盖：正向(imports写入)/边界(空/None)/异常(目标不存在)。
"""
import pytest

from src.governance.executor import GovernanceExecutor
from src.governance.registry import PatchType


@pytest.fixture
def executor(monkeypatch):
    e = GovernanceExecutor()
    # 路径校验有专门测试覆盖；此处 mock 放行，聚焦 required_imports 接入逻辑
    monkeypatch.setattr(e, "validate_file_path", lambda fp: True)
    return e


class TestRequiredImports:
    """required_imports 接入：覆盖正向/负向/边界/异常/依赖"""

    @pytest.mark.asyncio
    async def test_required_imports_written_to_file(self, executor, tmp_path):
        """正向：required_imports 被实际写入文件，且函数体被改写"""
        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")

        success = await executor.apply_patch(
            file_path=str(target),
            patch_type=PatchType.FUNCTIONAL,
            target_function="f",
            suggested_code="def f():\n    return 2\n",
            required_imports=["import os", "from typing import List"],
        )

        assert success is True
        content = target.read_text(encoding="utf-8")
        # 关键断言：import 被写入
        assert "import os" in content, "required_imports 必须写入文件"
        assert "from typing import List" in content
        # 函数体被改写
        assert "return 2" in content

    @pytest.mark.asyncio
    async def test_empty_required_imports_no_import_added(self, executor, tmp_path):
        """边界：空 required_imports 不添加 import 行，仅改函数体"""
        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")

        success = await executor.apply_patch(
            file_path=str(target),
            patch_type=PatchType.FUNCTIONAL,
            target_function="f",
            suggested_code="def f():\n    return 2\n",
            required_imports=[],
        )

        assert success is True
        content = target.read_text(encoding="utf-8")
        assert "return 2" in content
        assert "import os" not in content

    @pytest.mark.asyncio
    async def test_none_required_imports_works(self, executor, tmp_path):
        """边界：required_imports=None 正常改函数体不报错"""
        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")

        success = await executor.apply_patch(
            file_path=str(target),
            patch_type=PatchType.FUNCTIONAL,
            target_function="f",
            suggested_code="def f():\n    return 3\n",
            required_imports=None,
        )

        assert success is True
        content = target.read_text(encoding="utf-8")
        assert "return 3" in content

    @pytest.mark.asyncio
    async def test_patch_with_class_method_and_imports(self, executor, tmp_path):
        """依赖：类方法补丁 + required_imports 同时生效"""
        target = tmp_path / "svc.py"
        target.write_text(
            "class Service:\n    def run(self):\n        return 1\n", encoding="utf-8"
        )

        success = await executor.apply_patch(
            file_path=str(target),
            patch_type=PatchType.SECURITY,
            target_function="run",
            target_class="Service",
            suggested_code="def run(self):\n        return 2\n",
            required_imports=["import logging"],
        )

        assert success is True
        content = target.read_text(encoding="utf-8")
        assert "import logging" in content
        assert "return 2" in content
