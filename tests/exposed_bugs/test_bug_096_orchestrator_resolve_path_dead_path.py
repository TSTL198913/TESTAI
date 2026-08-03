"""BUG-096: _resolve_file_path 对核心处理器组件返回不存在的死路径。

源码位置: src/governance/orchestrator.py:319-335 _resolve_file_path

根因:
    mapping = {"EvalPlatformProcessor": "extensions/eval_platform/processor.py"}
    relative_path = mapping.get(component_name, f"src/components/{component_name}.py")
    项目实际结构是 src/platform/、src/engine/ 等,不存在 src/components/ 目录。
    除 EvalPlatformProcessor 外,所有 component_name 都映射到不存在的路径。

真实影响:
    治理闭环中,executor.apply_patch 需要写入 _resolve_file_path 返回的文件路径。
    HTTPProcessor / AssertionProcessor / GovernanceProcessor 等核心处理器异常时,
    治理补丁会写入不存在的路径 → 补丁应用失败 → 治理闭环在"代码修复"环节断裂。

与 test_bug_040 的区别:
    test_bug_040 断言返回值格式(path == "src/components/X.py"),固化了缺陷行为。
    本测试验证返回路径在文件系统中是否真实存在,暴露缺陷的真实业务影响。
"""
import os

import pytest

from src.governance.orchestrator import GovernanceOrchestrator


class TestResolveFilePathDeadPath:
    """验证 _resolve_file_path 返回的路径在文件系统中真实存在。"""

    @pytest.fixture
    def orchestrator(self):
        return GovernanceOrchestrator()

    @pytest.mark.parametrize(
        "component_name",
        [
            "HTTPProcessor",
            "AssertionProcessor",
            "GovernanceProcessor",
            "DataProcessor",
        ],
    )
    def test_resolved_path_exists_on_disk(self, orchestrator, component_name):
        """_resolve_file_path 返回的路径必须在文件系统中存在,否则补丁写入失败。

        这是治理闭环能真正修复代码的前提:路径不存在 → open(path,'w') 失败 →
        治理补丁无法应用 → 闭环断裂。
        """
        resolved = orchestrator._resolve_file_path(component_name)
        exists = os.path.exists(resolved)

        assert exists, (
            f"组件 {component_name!r} 映射到路径 {resolved!r},"
            f"但该路径在文件系统中不存在。"
            f"治理补丁将写入失败,闭环断裂。"
            f"实际处理器应在 src/engine/processor/ 下。"
        )

    def test_unknown_component_falls_back_to_engine_dir(self, orchestrator):
        """未知组件的回退路径应在 src/engine/processor/ 下,而非 src/components/。"""
        resolved = orchestrator._resolve_file_path("SomeNewProcessor")
        
        # 回退路径应指向 engine 目录
        assert resolved.startswith("src/engine/processor/"), (
            f"未知组件回退路径应在 src/engine/processor/ 下,实际: {resolved}"
        )
        
        # 路径应包含组件名的核心部分
        assert "somenew" in resolved.lower(), (
            f"回退路径应包含组件名核心部分,实际: {resolved}"
        )

    def test_known_processor_path_mapping_is_valid(self, orchestrator):
        """EvalPlatformProcessor 是唯一有显式映射的,验证它确实存在(对照组)。"""
        resolved = orchestrator._resolve_file_path("EvalPlatformProcessor")
        assert os.path.exists(resolved), (
            f"对照组 EvalPlatformProcessor 路径 {resolved!r} 应存在"
        )

    def test_no_path_goes_to_src_components(self, orchestrator):
        """任何组件的路径都不应指向 src/components/ (该目录不存在)。"""
        for name in ["HTTPProcessor", "DataProcessor", "EvalPlatformProcessor"]:
            resolved = orchestrator._resolve_file_path(name)
            assert "src/components" not in resolved, (
                f"组件 {name} 路径 {resolved} 不应指向 src/components/"
            )

    def test_default_mapping_dir_does_not_exist(self):
        """验证 src/components/ 目录在项目中确实不存在(根因)。"""
        assert not os.path.isdir("src/components"), (
            "src/components/ 不应存在——若存在则缺陷已修复,需更新本测试"
        )
