"""BUG-001: 变异测试 kill_rate 造假 + details 永远为空。

源码位置:src/platform/workflow.py:399-481 _handle_mutation_test_task

根因:
1. L450 `is_killed = random.random() > 0.25` —— 不运行任何测试套件,kill_rate 是纯随机数
2. L456 `ast.get_source_segment(mutated_code, node).strip()` ——
   mutated_code 是 ast.unparse 返回的新字符串,但 node 仍属于原 tree,
   lineno/col_offset 已被 fix_missing_locations 改写,get_source_segment 返回 None,
   .strip() 抛 AttributeError
3. L464-465 `except Exception: pass` —— 静默吞没,导致 mutations=[]、killed=0、survived=0、details=[]

现有测试反模式:tests/platform/test_workflow.py:342-359
- L354 `assert 0 <= kill_rate <= 1.0` —— kill_rate=0.0 时永真
- L358 `assert mutations == killed + survived` —— 三者都为 0 时永真
"""
import pytest

from src.platform.workflow import WorkflowEngine, WorkflowTask, TaskType


@pytest.mark.asyncio
async def test_mutation_test_produces_real_mutations(tmp_path):
    """变异测试必须产生 >0 个变异体,且 details 非空。

    正确行为:给定含 BinOp/Compare 的真实源码,应识别出变异点,
    产生 >0 个变异体,details 列表非空,每个变异体含 original/mutated/killed 字段。
    """
    target = tmp_path / "sample.py"
    target.write_text(
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def compare(x, y):\n"
        "    return x > y\n"
    )

    engine = WorkflowEngine()
    task = WorkflowTask(
        type=TaskType.MUTATION_TEST,
        name="mut",
        params={"target_dir": str(tmp_path)},
    )

    result = await engine._handle_mutation_test_task(task, {}, {})
    report = result["report"]

    assert report["mutations"] > 0, (
        f"变异体数量必须 > 0,当前实现因 .strip() 抛 AttributeError 被 except Exception: pass 吞没返回 0, "
        f"实际 mutations={report['mutations']}, killed={report['killed']}, survived={report['survived']}"
    )
    assert len(report["details"]) > 0, (
        f"details 必须非空,当前实现因异常吞没返回空列表, 实际 details={report['details']}"
    )
    for item in report["details"]:
        assert "original" in item, f"每个变异体必须含 original 字段,实际: {item}"
        assert "mutated" in item, f"每个变异体必须含 mutated 字段,实际: {item}"
        assert "killed" in item, f"每个变异体必须含 killed 字段,实际: {item}"


@pytest.mark.asyncio
async def test_mutation_test_kill_rate_matches_killed_count(tmp_path):
    """kill_rate 必须等于 killed / (killed + survived),且基于真实测试。

    正确行为:产生 >0 个变异体,kill_rate = killed / total,且 killed 基于真实测试运行结果。
    当前实现:ast.get_source_segment(mutated_code, node) 返回 None,
    .strip() 抛 AttributeError 被 except Exception: pass 吞没,
    导致 mutations.append 从未完成,killed=0、survived=0、total=0、kill_rate=0.0。
    kill_rate=0.0 虽然满足公式(0/0 回退为 0.0),但掩盖了"无变异体被执行"的真实缺陷。
    """
    target = tmp_path / "sample.py"
    target.write_text(
        "def add(a, b):\n    return a + b\n"
        "def sub(a, b):\n    return a - b\n"
        "def mul(a, b):\n    return a * b\n"
    )

    engine = WorkflowEngine()
    task = WorkflowTask(
        type=TaskType.MUTATION_TEST,
        name="mut",
        params={"target_dir": str(tmp_path)},
    )

    result = await engine._handle_mutation_test_task(task, {}, {})
    report = result["report"]

    # 必须有变异体被执行,否则 kill_rate 无意义
    total = report["killed"] + report["survived"]
    assert total > 0, (
        f"必须有变异体被执行(killed+survived > 0),当前实现因 .strip() 抛 AttributeError "
        f"被 except Exception: pass 吞没,导致 killed={report['killed']}, "
        f"survived={report['survived']}, total=0, kill_rate 恒为 0.0 掩盖缺陷"
    )

    # kill_rate 必须与 killed/total 一致(基于真实测试运行)
    expected_kill_rate = round(report["killed"] / total, 2)
    assert report["kill_rate"] == expected_kill_rate, (
        f"kill_rate 必须等于 killed/total, 实际 kill_rate={report['kill_rate']}, "
        f"expected={expected_kill_rate}"
    )
