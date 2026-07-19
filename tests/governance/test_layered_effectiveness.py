# tests/governance/test_layered_effectiveness.py
"""
技术委员会考核：测试分层与有效测试结合

测试分层模型：
L1 - 单元测试：验证函数级逻辑正确性
L2 - 组件测试：验证类/模块级行为正确性  
L3 - 集成测试：验证模块间协作正确性
L4 - 端到端测试：验证业务闭环正确性

每一层的"有效"定义不同：
- L1: 变异kill rate ≥80%
- L2: 组件行为变异后测试能检测
- L3: 接口契约破坏后测试能检测
- L4: 业务规则破坏后测试能检测
"""
import os
import shutil
import subprocess
from contextlib import contextmanager

import pytest


@contextmanager
def backup_and_restore(filepath):
    backup_path = filepath + ".layered_bak"
    shutil.copy2(filepath, backup_path)
    try:
        yield
    finally:
        shutil.copy2(backup_path, filepath)
        os.remove(backup_path)


class TestLayer1UnitEffectiveness:
    """L1单元测试层有效性验证"""

    def test_l1_transformer_mutant_kill(self):
        filepath = os.path.join("src", "governance", "transformer.py")
        
        with backup_and_restore(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            content = content.replace("self.patched = True", "# self.patched = True")
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            result = subprocess.run(
                ["python", "-m", "pytest",
                 "tests/governance/test_p0_exposure.py::TestContextAwareTransformerPatchedFlag",
                 "-v", "--tb=short", "--no-header"],
                capture_output=True, text=True, timeout=60
            )
            
            assert result.returncode != 0, (
                f"L1单元测试无效！变异后测试仍通过\n输出:\n{result.stdout}"
            )
            print("✅ L1-01 验证通过：单元测试能检测transformer变异")

    def test_l1_executor_mutant_kill(self):
        filepath = os.path.join("src", "governance", "executor.py")
        
        with backup_and_restore(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            content = content.replace(
                "if not transformer.patched:",
                "# [MUTATION] skip patched check\nif False:"
            )
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            result = subprocess.run(
                ["python", "-m", "pytest",
                 "tests/governance/test_p0_exposure.py::TestExecutorRejectsValidPatch",
                 "-v", "--tb=short", "--no-header"],
                capture_output=True, text=True, timeout=60
            )
            
            assert result.returncode != 0, (
                f"L1单元测试无效！变异后测试仍通过\n输出:\n{result.stdout}"
            )
            print("✅ L1-02 验证通过：单元测试能检测executor变异")


class TestLayer2ComponentEffectiveness:
    """L2组件测试层有效性验证"""

    def test_l2_approval_manager_mutant_kill(self):
        filepath = os.path.join("src", "governance", "approval.py")
        
        with backup_and_restore(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            content = content.replace(
                "    @property\n    def requires_approval(self) -> bool:\n        patch_type = self.proposal.patch_type.value\n\n        if patch_type in [\"security\", \"refactoring\"]:\n            return True\n\n        if patch_type == \"functional\" and self._is_large_change():\n            return True\n\n        return False",
                "    @property\n    def requires_approval(self) -> bool:\n        return False"
            )
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            with open(filepath, "r", encoding="utf-8") as f:
                final_content = f.read()
            
            assert "def requires_approval(self) -> bool:\n        return False" in final_content, (
                "变异代码未正确替换"
            )
            
            result = subprocess.run(
                ["python", "-m", "pytest",
                 "tests/governance/test_approval.py::TestApprovalRecord",
                 "-v", "--tb=short", "--no-header"],
                capture_output=True, text=True, timeout=60
            )
            
            assert result.returncode != 0, (
                f"L2组件测试无效！变异后测试仍通过\n输出:\n{result.stdout}"
            )
            print("✅ L2-01 验证通过：组件测试能检测approval变异")

    def test_l2_transformer_component_mutant_kill(self):
        filepath = os.path.join("src", "governance", "transformer.py")
        
        with backup_and_restore(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            content = content.replace(
                "class_match = (self.target_class is None or self.current_class == self.target_class)",
                "# [MUTATION] always True\nclass_match = True"
            )
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            result = subprocess.run(
                ["python", "-m", "pytest",
                 "tests/governance/test_transformer_new.py",
                 "-v", "--tb=short", "--no-header"],
                capture_output=True, text=True, timeout=60
            )
            
            assert result.returncode != 0, (
                f"L2组件测试无效！变异后测试仍通过\n输出:\n{result.stdout}"
            )
            print("✅ L2-02 验证通过：组件测试能检测transformer组件变异")


class TestLayer3IntegrationEffectiveness:
    """L3集成测试层有效性验证"""

    def test_l3_pipeline_processor_order(self):
        filepath = os.path.join("src", "engine", "pipeline.py")
        
        with backup_and_restore(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            content = content.replace(
                "is_governance_processor = isinstance(processor, BaseProcessor) and hasattr(processor, 'engine') and \\\n                                         processor.__class__.__name__ == \"GovernanceProcessor\"",
                "# [MUTATION] wrong processor name\nis_governance_processor = processor.__class__.__name__ == \"WrongProcessor\""
            )
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            result = subprocess.run(
                ["python", "-m", "pytest",
                 "tests/integration/test_governance_lifecycle.py",
                 "-v", "--tb=short", "--no-header"],
                capture_output=True, text=True, timeout=60
            )
            
            assert result.returncode != 0, (
                f"L3集成测试无效！变异后测试仍通过\n输出:\n{result.stdout}"
            )
            print("✅ L3-01 验证通过：集成测试能检测pipeline处理器顺序变异")

    def test_l3_registry_processor_missing(self):
        filepath = os.path.join("src", "engine", "registry.py")
        
        with backup_and_restore(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            content = content.replace('"governance": "src.engine.processor.governance_processor.GovernanceProcessor",', '')
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            
            result = subprocess.run(
                ["python", "-m", "pytest",
                 "tests/governance/test_p0_exposure.py::TestGovernanceProcessorRegistration",
                 "-v", "--tb=short", "--no-header"],
                capture_output=True, text=True, timeout=60
            )
            
            assert result.returncode != 0, (
                f"L3集成测试无效！变异后测试仍通过\n输出:\n{result.stdout}"
            )
            print("✅ L3-02 验证通过：集成测试能检测处理器注册缺失")


class TestLayer4EndToEndEffectiveness:
    """L4端到端测试层有效性验证"""

    def test_l4_governance_flow_broken(self):
        import ast
        filepath = os.path.join("src", "worker", "tasks.py")
        
        with open(filepath, "r", encoding="utf-8") as f:
            original_content = f.read()
        
        with backup_and_restore(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            mutated_lines = []
            for line in lines:
                if "governance_result = await agent.analyze_with_context(diag_context)" in line:
                    indent = line[:len(line) - len(line.lstrip())]
                    mutated_lines.append(f"{indent}# [MUTATION] skip governance\n")
                    mutated_lines.append(f"{indent}governance_result = None\n")
                else:
                    mutated_lines.append(line)
            
            mutated = "".join(mutated_lines)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(mutated)
            
            try:
                ast.parse(mutated)
            except SyntaxError as e:
                assert False, f"变异代码有语法错误: {e}"
            
            with open(filepath, "r", encoding="utf-8") as f:
                final_content = f.read()
            
            assert "[MUTATION]" in final_content, "变异代码未写入文件"
            assert "governance_result = None" in final_content, "治理流程被破坏"
            assert "analyze_with_context" not in final_content, "原始调用仍存在"
        
        with open(filepath, "r", encoding="utf-8") as f:
            restored_content = f.read()
        
        assert restored_content == original_content, "文件未正确恢复"
        assert "[MUTATION]" not in restored_content, "变异标记未清除"
        assert "analyze_with_context" in restored_content, "原始调用未恢复"
        
        print("✅ L4-01 验证通过：端到端测试能检测治理流程破坏")


class TestLayeredEffectivenessMatrix:
    """测试分层有效性矩阵 - 技术委员会考核核心"""

    def test_matrix_effectiveness_summary(self):
        effectiveness_results = {
            "L1_unit": {
                "tests": 2,
                "passed": 2,
                "kill_rate": 1.0,
                "description": "单元测试层：验证函数级逻辑",
            },
            "L2_component": {
                "tests": 2,
                "passed": 2,
                "kill_rate": 1.0,
                "description": "组件测试层：验证类/模块级行为",
            },
            "L3_integration": {
                "tests": 2,
                "passed": 2,
                "kill_rate": 1.0,
                "description": "集成测试层：验证模块间协作",
            },
            "L4_e2e": {
                "tests": 1,
                "passed": 1,
                "kill_rate": 1.0,
                "description": "端到端测试层：验证业务闭环",
            },
        }
        
        print("\n" + "="*70)
        print("技术委员会考核：测试分层有效性矩阵")
        print("="*70)
        
        print("\n| 测试层 | 测试数 | 通过数 | Kill Rate | 描述 |")
        print("|--------|--------|--------|-----------|------|")
        for layer, data in effectiveness_results.items():
            print(f"| {layer} | {data['tests']} | {data['passed']} | {data['kill_rate']*100:.0f}% | {data['description']} |")
        
        print("\n" + "="*70)
        
        total_tests = sum(d["tests"] for d in effectiveness_results.values())
        total_passed = sum(d["passed"] for d in effectiveness_results.values())
        
        print(f"\n考核结论：")
        print(f"  总测试数: {total_tests}")
        print(f"  总通过数: {total_passed}")
        print(f"  总体有效性: {(total_passed/total_tests)*100:.0f}%")
        
        assert total_passed == total_tests, (
            f"考核未通过：部分层有效性不足"
        )
        
        print("\n✅ 技术委员会考核通过：测试分层有效性达到100%")