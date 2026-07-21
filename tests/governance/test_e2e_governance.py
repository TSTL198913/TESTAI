import asyncio
import os
import shutil

import pytest

from src.governance.executor import GovernanceExecutor
from src.governance.registry import PatchType


BUGGY_CODE = """
def calculate_score(a, b):
    # 错误逻辑：应该相加，这里写错了
    return a - b 
"""


async def setup_lab(temp_dir):
    target_file = os.path.join(temp_dir, "test_target.py")
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(BUGGY_CODE)
    return target_file


@pytest.mark.asyncio
async def test_governance_e2e_loop():
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    temp_dir = os.path.join(project_dir, "data", "e2e_test")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        target_file = await setup_lab(temp_dir)

        executor = GovernanceExecutor()

        result = await executor.apply_patch(
            file_path=target_file,
            patch_type=PatchType.FUNCTIONAL,
            target_function="calculate_score",
            suggested_code="return a + b",
            required_imports=[],
        )
        print(f"DEBUG: result = {result}")

        assert result is True, f"补丁应用失败"

        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "return a + b" in content
            assert "return a - b" not in content

        print("\n✅ E2E 治理闭环测试通过：成功诊断并修复了目标代码！")

    finally:
        import logging

        logger = logging.getLogger(__name__)
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for file in files:
                try:
                    os.remove(os.path.join(root, file))
                except PermissionError as e:
                    logger.warning(f"无法删除文件 {os.path.join(root, file)}: {e}")
                except Exception as e:
                    logger.warning(
                        f"清理文件失败 {os.path.join(root, file)}: {type(e).__name__}: {e}"
                    )
            for dir in dirs:
                try:
                    os.rmdir(os.path.join(root, dir))
                except OSError as e:
                    logger.warning(f"无法删除目录 {os.path.join(root, dir)}: {e}")
        try:
            os.rmdir(temp_dir)
        except OSError as e:
            logger.warning(f"无法删除临时目录 {temp_dir}: {e}")


if __name__ == "__main__":
    asyncio.run(test_governance_e2e_loop())
