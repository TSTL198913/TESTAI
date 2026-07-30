"""P1-4: 变异测试真实执行测试。

验证:
1. kill_rate 基于真实测试执行结果,而非 random.random() 造假
2. 变异被测试发现(测试失败) → killed=True
3. 变异未被测试发现(测试通过) → killed=False
4. kill_rate 计算正确(killed/total)
5. 相同输入多次运行结果一致(可重现性,反证 random 造假)
6. 无测试文件时所有变异存活
"""
import os
import sys
import shutil
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.platform.workflow import WorkflowEngine, WorkflowTask, TaskType


@pytest.fixture
def mutation_test_env(tmp_path):
    """创建隔离的变异测试环境:源码 + 对应测试。

    目录结构:
        tmp_path/src/calc.py        # 被测源码(含可变异的 BinOp)
        tmp_path/tests/test_calc.py # 对应测试(能检测到 a+b→a-b 的变异)

    注意:fixture 简化为单个变异点(BinOp),减少 subprocess 调用次数,
    避免测试超时(每个 subprocess 调用约 5-10 秒)。
    """
    # 源码目录
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # 被测源码:简单的 add 函数(含 BinOp 加法,可变异为减法)
    calc_py = src_dir / "calc.py"
    calc_py.write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    # 测试目录
    test_dir = tmp_path / "tests"
    test_dir.mkdir()

    # 对应测试:验证 add(2,3)==5,能检测到 add 变异为减法(2-3=-1 ≠ 5)
    test_calc_py = test_dir / "test_calc.py"
    test_calc_py.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        'sys.path.insert(0, str(Path(__file__).parent.parent / "src"))\n'
        "\n"
        "from calc import add\n"
        "\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    return {
        "root": str(tmp_path),
        "src_dir": str(src_dir),
        "test_dir": str(test_dir),
    }


class TestMutationTestRealExecution:
    """P1-4: 验证变异测试基于真实测试执行。"""

    @pytest.mark.timeout(60)
    @pytest.mark.asyncio
    async def test_kill_rate_reproducible(self, mutation_test_env):
        """反证 random 造假:相同输入多次运行 kill_rate 必须一致。

        random.random() 每次运行结果不同,真实测试执行结果稳定。
        只运行 2 次(而非 3 次)以减少 subprocess 调用时间。
        """
        engine = WorkflowEngine()
        task = WorkflowTask(
            type=TaskType.MUTATION_TEST,
            name="Mutation Test",
            params={"target_dir": mutation_test_env["src_dir"]},
        )

        # 运行 2 次,kill_rate 必须完全相同
        results = []
        for _ in range(2):
            result = await engine._handle_mutation_test_task(task, {}, {})
            results.append(result["report"]["kill_rate"])

        assert results[0] == results[1], (
            f"kill_rate 必须可重现(反证 random 造假), 实际 2 次结果: {results}"
        )

    @pytest.mark.timeout(60)
    @pytest.mark.asyncio
    async def test_mutation_killed_when_test_fails(self, mutation_test_env):
        """变异被测试发现(测试失败) → killed=True。

        add 函数 a+b 变异为 a-b,test_add 期望 2+3==5 但变异后 2-3=-1,
        测试必然失败,该变异应被 killed。
        """
        engine = WorkflowEngine()
        task = WorkflowTask(
            type=TaskType.MUTATION_TEST,
            name="Mutation Test",
            params={"target_dir": mutation_test_env["src_dir"]},
        )

        result = await engine._handle_mutation_test_task(task, {}, {})
        report = result["report"]

        # 至少有一个变异被 killed(因为测试能检测到 a+b→a-b)
        assert report["killed"] >= 1, (
            f"测试能检测到 add 的 BinOp 变异, killed 应 >= 1, 实际: {report['killed']}"
        )

        # 验证 details 中存在 killed=True 的变异
        details = report.get("details", [])
        killed_mutations = [m for m in details if m.get("killed") is True]
        assert len(killed_mutations) >= 1, (
            f"details 中必须存在 killed=True 的变异, 实际 details: {details}"
        )

    @pytest.mark.timeout(60)
    @pytest.mark.asyncio
    async def test_kill_rate_calculation_correct(self, mutation_test_env):
        """kill_rate = killed / total_mutations,且 total = killed + survived。"""
        engine = WorkflowEngine()
        task = WorkflowTask(
            type=TaskType.MUTATION_TEST,
            name="Mutation Test",
            params={"target_dir": mutation_test_env["src_dir"]},
        )

        result = await engine._handle_mutation_test_task(task, {}, {})
        report = result["report"]

        total = report["mutations"]
        killed = report["killed"]
        survived = report["survived"]

        # 一致性校验
        assert total == killed + survived, (
            f"total 必须等于 killed + survived, "
            f"实际: total={total}, killed={killed}, survived={survived}"
        )

        # kill_rate 计算正确
        if total > 0:
            expected_kill_rate = round(killed / total, 2)
            assert report["kill_rate"] == expected_kill_rate, (
                f"kill_rate 必须等于 killed/total, "
                f"实际: {report['kill_rate']}, 期望: {expected_kill_rate}"
            )
        else:
            assert report["kill_rate"] == 0.0

    @pytest.mark.timeout(60)
    @pytest.mark.asyncio
    async def test_no_test_file_all_survived(self, tmp_path):
        """无对应测试文件时,所有变异应标记为 survived(无法验证)。"""
        # 创建源码但无测试
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "calc.py").write_text(
            "def add(a, b):\n"
            "    return a + b\n",
            encoding="utf-8",
        )

        engine = WorkflowEngine()
        task = WorkflowTask(
            type=TaskType.MUTATION_TEST,
            name="Mutation Test",
            params={"target_dir": str(src_dir)},
        )

        result = await engine._handle_mutation_test_task(task, {}, {})
        report = result["report"]

        # 无测试时 killed 必须为 0(无法检测变异)
        assert report["killed"] == 0, (
            f"无测试文件时所有变异应 survived(killed=0), 实际 killed: {report['killed']}"
        )
        assert report["survived"] == report["mutations"]

    @pytest.mark.timeout(60)
    @pytest.mark.asyncio
    async def test_mutation_uses_subprocess_not_random(self, mutation_test_env):
        """验证实现使用 subprocess 执行测试,而非 random.random()。"""
        engine = WorkflowEngine()
        task = WorkflowTask(
            type=TaskType.MUTATION_TEST,
            name="Mutation Test",
            params={"target_dir": mutation_test_env["src_dir"]},
        )

        # 监控 random.random 是否被调用(mock random 模块本身)
        with patch("random.random") as mock_random:
            mock_random.return_value = 0.5
            result = await engine._handle_mutation_test_task(task, {}, {})

        # random.random 不应被调用(已弃用 random 造假)
        mock_random.assert_not_called()

    @pytest.mark.timeout(60)
    @pytest.mark.asyncio
    async def test_mutation_details_contain_real_test_result(self, mutation_test_env):
        """details 中每个变异的 killed 字段必须基于真实测试结果,而非随机值。"""
        engine = WorkflowEngine()
        task = WorkflowTask(
            type=TaskType.MUTATION_TEST,
            name="Mutation Test",
            params={"target_dir": mutation_test_env["src_dir"]},
        )

        result = await engine._handle_mutation_test_task(task, {}, {})
        report = result["report"]

        # 至少存在 1 个变异点
        assert report["mutations"] >= 1, "应至少检测到 1 个变异点"

        # details 必须包含变异详情
        details = report.get("details", [])
        assert len(details) >= 1, "details 不能为空"

        # 每个变异必须包含 file/type/original/mutated/killed 字段
        for m in details:
            assert "file" in m, f"变异详情缺少 file 字段: {m}"
            assert "type" in m, f"变异详情缺少 type 字段: {m}"
            assert "killed" in m, f"变异详情缺少 killed 字段: {m}"
            assert isinstance(m["killed"], bool), (
                f"killed 必须是 bool 类型, 实际: {type(m['killed'])}"
            )

