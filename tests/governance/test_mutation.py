# tests/governance/test_mutation.py
"""
自定义变异测试 - Windows 兼容版

本测试通过手动注入变异来验证测试体系的有效性。
如果测试能检测到这些变异，说明测试体系有效。
"""
import os
import shutil
import subprocess
from contextlib import contextmanager

import pytest


@contextmanager
def _backup_and_restore(filepath):
    backup_path = filepath + ".mutate_bak"
    shutil.copy2(filepath, backup_path)
    try:
        yield
    finally:
        shutil.copy2(backup_path, filepath)
        os.remove(backup_path)


class TestMutationCoverage:
    """验证测试体系能检测到代码变异"""

    def test_mutate_transformer_patched_flag(self):
        filepath = os.path.join("src", "governance", "transformer.py")
        
        with _backup_and_restore(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            content = content.replace("self.patched = True", "self.patched = False")
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            result = subprocess.run(
                [
                    "python", "-m", "pytest",
                    "tests/governance/test_p0_exposure.py::TestContextAwareTransformerPatchedFlag",
                    "-v", "--tb=short", "--no-header"
                ],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                pytest.fail("变异未被检测到！测试输出:\n" + result.stdout)
            print("✅ 变异检测通过：patched=True → False")

    def test_mutate_registry_governance_processor(self):
        filepath = os.path.join("src", "engine", "registry.py")
        
        with _backup_and_restore(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            lines = content.split("\n")
            new_lines = []
            for line in lines:
                if '"governance"' not in line:
                    new_lines.append(line)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines))
            
            result = subprocess.run(
                [
                    "python", "-m", "pytest",
                    "tests/governance/test_p0_exposure.py::TestGovernanceProcessorRegistration",
                    "-v", "--tb=short", "--no-header"
                ],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                pytest.fail("变异未被检测到！测试输出:\n" + result.stdout)
            print("✅ 变异检测通过：删除 governance 注册")