# tests/governance/test_effectiveness_gate.py
"""
测试有效性反向验证门控

本测试验证测试体系能否检测到已知bug。如果本测试失败，说明测试体系无效。

验证逻辑：
1. 故意引入 NEW-003 的 bug（删除 transformer.py 中的 self.patched=True）
2. 运行相关测试，验证测试能检测到该 bug
3. 恢复代码

如果本测试通过，说明测试体系有效；如果失败，说明测试体系无效。
"""
import os
import shutil
import subprocess
from contextlib import contextmanager

import pytest


@contextmanager
def _backup_and_restore(filepath):
    backup_path = filepath + ".effectiveness_bak"
    shutil.copy2(filepath, backup_path)
    try:
        yield
    finally:
        shutil.copy2(backup_path, filepath)
        os.remove(backup_path)


class TestEffectivenessGate:
    """验证测试体系能检测到已知bug"""

    def test_can_detect_patched_flag_missing(self):
        """
        验证测试体系能检测到 NEW-003 问题：
        ContextAwareTransformer 缺失 patched=True

        如果测试体系有效，修改代码后相关测试应该失败。
        """
        transformer_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "src", "governance", "transformer.py"
        )
        
        with _backup_and_restore(transformer_path):
            with open(transformer_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if "self.patched = True" not in content:
                pytest.fail("transformer.py 中未找到 self.patched = True 标记")
            
            lines = content.split("\n")
            new_lines = []
            i = 0
            while i < len(lines):
                if "self.patched = True" in lines[i]:
                    i += 1
                    continue
                new_lines.append(lines[i])
                i += 1
            
            with open(transformer_path, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines))
            
            result = subprocess.run(
                [
                    "python", "-m", "pytest",
                    "tests/governance/test_p0_exposure.py::TestContextAwareTransformerPatchedFlag",
                    "-v", "--tb=short", "--no-header"
                ],
                cwd=os.path.dirname(__file__) + "/../..",
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                pytest.fail(
                    "测试体系无法检测到 NEW-003 bug！\n"
                    "这意味着测试体系无效——修改代码后测试仍然通过。\n"
                    f"测试输出:\n{result.stdout}"
                )
            
            print("✅ 测试体系有效性验证通过：成功检测到 NEW-003 bug")

    def test_can_detect_missing_governance_processor(self):
        """
        验证测试体系能检测到 NEW-004 问题：
        GovernanceProcessor 未注册到 _PROCESSOR_MAP

        如果测试体系有效，修改代码后相关测试应该失败。
        """
        registry_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "src", "engine", "registry.py"
        )
        
        with _backup_and_restore(registry_path):
            with open(registry_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            if '"governance"' not in content:
                pytest.fail("registry.py 中未找到 governance 注册")
            
            lines = content.split("\n")
            new_lines = []
            for line in lines:
                if '"governance"' in line:
                    continue
                new_lines.append(line)
            
            with open(registry_path, "w", encoding="utf-8") as f:
                f.write("\n".join(new_lines))
            
            result = subprocess.run(
                [
                    "python", "-m", "pytest",
                    "tests/governance/test_p0_exposure.py::TestGovernanceProcessorRegistration",
                    "-v", "--tb=short", "--no-header"
                ],
                cwd=os.path.dirname(__file__) + "/../..",
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                pytest.fail(
                    "测试体系无法检测到 NEW-004 bug！\n"
                    f"测试输出:\n{result.stdout}"
                )
            
            print("✅ 测试体系有效性验证通过：成功检测到 NEW-004 bug")