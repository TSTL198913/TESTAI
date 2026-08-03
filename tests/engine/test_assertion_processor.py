"""
AssertionProcessor 单元测试
覆盖:
1. status_code 断言 (pass/fail)
2. body_contains 断言 (pass/fail)
3. jsonpath 断言 (pass/fail/异常)
4. 多断言组合
5. 边界场景 (空结果、无断言、JSONPath语法错误)
"""

import pytest

from src.engine.processor.assertion import AssertionProcessor
from src.models.assertion import Assertion
from src.models.contract import HttpRequest
from src.models.result import StepResult
from src.core.exceptions import EngineError


@pytest.fixture
def processor():
    return AssertionProcessor()


@pytest.fixture
def context():
    """带 results 属性的 mock context"""
    class MockContext:
        def __init__(self):
            self.results = {}
    return MockContext()


def _make_step(step_id="s1", assertions=None, **kwargs):
    if assertions is None:
        assertions = []
    return HttpRequest(
        step_id=step_id,
        description="test",
        url="http://localhost",
        method="GET",
        assertions=assertions,
        **kwargs
    )


def _setup_result(context, step_id="s1", status_code=200, body=None, status="PASSED"):
    """在 context.results 中预置一个 StepResult"""
    result = StepResult(
        status=status,
        status_code=status_code,
        body=body,
        error=None
    )
    context.results[step_id] = result.model_dump()


# ==================== status_code 断言 ====================

@pytest.mark.asyncio
async def test_status_code_assertion_pass(processor, context):
    """status_code 断言: 期望匹配 → PASSED"""
    _setup_result(context, status_code=200)
    step = _make_step(assertions=[Assertion(check="status_code", expected=200)])
    
    result = await processor._run(context, step, None)
    
    assert context.results["s1"]["status"] == "PASSED"
    assert context.results["s1"]["assertions_history"][0]["passed"] is True


@pytest.mark.asyncio
async def test_status_code_assertion_fail(processor, context):
    """status_code 断言: 期望不匹配 → FAILED"""
    _setup_result(context, status_code=404)
    step = _make_step(assertions=[Assertion(check="status_code", expected=200)])
    
    with pytest.raises(EngineError) as exc_info:
        await processor._run(context, step, None)
    
    assert "Assertion Failed" in str(exc_info.value)
    assert context.results["s1"]["status"] == "FAILED"
    assert context.results["s1"]["assertions_history"][0]["passed"] is False


# ==================== body_contains 断言 ====================

@pytest.mark.asyncio
async def test_body_contains_assertion_pass(processor, context):
    """body_contains 断言: 子串存在 → PASSED"""
    _setup_result(context, body='{"message": "Success"}')
    step = _make_step(assertions=[Assertion(check="body_contains", expected="Success")])
    
    result = await processor._run(context, step, None)
    
    assert context.results["s1"]["status"] == "PASSED"
    assert context.results["s1"]["assertions_history"][0]["passed"] is True


@pytest.mark.asyncio
async def test_body_contains_assertion_fail(processor, context):
    """body_contains 断言: 子串不存在 → FAILED"""
    _setup_result(context, body='{"message": "Error"}')
    step = _make_step(assertions=[Assertion(check="body_contains", expected="Success")])
    
    with pytest.raises(EngineError):
        await processor._run(context, step, None)
    
    assert context.results["s1"]["status"] == "FAILED"


# ==================== jsonpath 断言 ====================

@pytest.mark.asyncio
async def test_jsonpath_assertion_pass(processor, context):
    """jsonpath 断言: JSONPath 匹配 → PASSED
    
    注意: http.py 将 JSON body 解析为 dict 存入 StepResult.body
    所以 body 必须是 dict, jsonpath_ng 才能正确解析
    """
    _setup_result(context, body={"data": {"value": 42}})
    step = _make_step(
        assertions=[Assertion(check="jsonpath", expected=42, path="$.data.value")]
    )
    
    result = await processor._run(context, step, None)
    
    assert context.results["s1"]["status"] == "PASSED"
    assert context.results["s1"]["assertions_history"][0]["passed"] is True


@pytest.mark.asyncio
async def test_jsonpath_assertion_fail(processor, context):
    """jsonpath 断言: JSONPath 值不匹配 → FAILED"""
    _setup_result(context, body={"data": {"value": 99}})
    step = _make_step(
        assertions=[Assertion(check="jsonpath", expected=42, path="$.data.value")]
    )
    
    with pytest.raises(EngineError):
        await processor._run(context, step, None)
    
    assert context.results["s1"]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_jsonpath_no_match(processor, context):
    """jsonpath 断言: JSONPath 路径不存在 → FAILED (actual='NOT_FOUND')"""
    _setup_result(context, body={"data": {}})
    step = _make_step(
        assertions=[Assertion(check="jsonpath", expected="missing", path="$.data.value")]
    )
    
    with pytest.raises(EngineError):
        await processor._run(context, step, None)
    
    assert context.results["s1"]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_jsonpath_missing_path_field(processor, context):
    """jsonpath 断言: path 字段缺失 → 断言异常被捕获,标记为 FAILED"""
    _setup_result(context, body={"data": 1})
    # 无 path 字段 → 会触发 ValueError
    step = _make_step(assertions=[Assertion(check="jsonpath", expected=1)])
    
    with pytest.raises(EngineError):
        await processor._run(context, step, None)
    
    assert context.results["s1"]["status"] == "FAILED"


# ==================== 多断言组合 ====================

@pytest.mark.asyncio
async def test_multiple_assertions_all_pass(processor, context):
    """多断言: 全部通过 → PASSED
    
    body 使用 dict 格式, 匹配 http.py 真实数据流
    """
    _setup_result(context, status_code=200, body={"data": {"status": "ok"}})
    step = _make_step(assertions=[
        Assertion(check="status_code", expected=200),
        Assertion(check="body_contains", expected="ok"),
        Assertion(check="jsonpath", expected="ok", path="$.data.status"),
    ])
    
    result = await processor._run(context, step, None)
    
    assert context.results["s1"]["status"] == "PASSED"
    assert len(context.results["s1"]["assertions_history"]) == 3
    for rec in context.results["s1"]["assertions_history"]:
        assert rec["passed"] is True


@pytest.mark.asyncio
async def test_multiple_assertions_one_fails(processor, context):
    """多断言: 一个失败 → 整体 FAILED,后续断言不执行"""
    _setup_result(context, status_code=200, body={"data": {"status": "error"}})
    step = _make_step(assertions=[
        Assertion(check="status_code", expected=200),       # pass
        Assertion(check="jsonpath", expected="ok", path="$.data.status"),  # fail
        Assertion(check="body_contains", expected="error"),  # 不会执行
    ])
    
    with pytest.raises(EngineError):
        await processor._run(context, step, None)
    
    assert context.results["s1"]["status"] == "FAILED"
    # 只有前两个断言被执行 (第二个失败后抛出异常)
    assert len(context.results["s1"]["assertions_history"]) == 2


# ==================== 边界场景 ====================

@pytest.mark.asyncio
async def test_no_assertions(processor, context):
    """无断言: 直接标记 PASSED"""
    _setup_result(context)
    step = _make_step(assertions=[])
    
    result = await processor._run(context, step, None)
    
    assert context.results["s1"]["status"] == "PASSED"
    assert len(context.results["s1"]["assertions_history"]) == 0


@pytest.mark.asyncio
async def test_no_result_in_context(processor, context):
    """context.results 中无对应 step_id → RuntimeError"""
    step = _make_step(assertions=[Assertion(check="status_code", expected=200)])
    
    with pytest.raises(RuntimeError) as exc_info:
        await processor._run(context, step, None)
    
    assert "No result found for step_id" in str(exc_info.value)


@pytest.mark.asyncio
async def test_body_contains_with_none_body(processor, context):
    """body_contains: body 为 None → result.body or '' → 空字符串
    
    代码: body_str = str(result.body or "")
    当 body 为 None, None or "" 返回 "", 查找子串会失败
    """
    _setup_result(context, body=None)
    step = _make_step(assertions=[Assertion(check="body_contains", expected="None")])
    
    # body=None → body or "" = "" → str("") = "" → 查找 "None" 会失败
    with pytest.raises(EngineError):
        await processor._run(context, step, None)
    
    assert context.results["s1"]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_jsonpath_with_invalid_json(processor, context):
    """jsonpath: body 为非 JSON 字符串 → jsonpath_ng 可能报错
    
    注意: 实际数据流中 body 可能是 dict (JSON 解析后) 或 str (text)
    如果 body 是 str 类型, jsonpath_ng.parse 后的 find 可能抛异常
    """
    _setup_result(context, body="not a json string")
    step = _make_step(
        assertions=[Assertion(check="jsonpath", expected="val", path="$.key")]
    )
    
    # jsonpath_ng 对字符串 body 的处理: 可能返回空或抛异常
    # 这里测试实际行为: 抛异常被 except 捕获 → FAILED
    try:
        await processor._run(context, step, None)
        # 如果没抛异常, 检查状态
        assert context.results["s1"]["status"] == "FAILED", \
            f"字符串 body 的 jsonpath 应失败, 实际状态: {context.results['s1']['status']}"
    except EngineError:
        # 预期行为
        assert context.results["s1"]["status"] == "FAILED"
        failed_record = context.results["s1"]["assertions_history"][-1]
        assert failed_record["passed"] is False