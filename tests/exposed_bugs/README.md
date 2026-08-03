# tests/exposed_bugs/ - 暴露被测试体系掩盖的 Bug

## 背景

本目录的测试用于暴露 `src/` 中被现有测试体系掩盖的 8 个 bug。

**核心矛盾**:测试通过率 97.6%(488/500),但 QC 审查报告显示测试有效度仅 65%。
100% 通过率本身是红色信号——意味着测试要么固化了当前行为(把 bug 当 expected behavior),
要么断言强度不足以触发失败。

## 设计原则

| 原则 | 实现方式 |
|------|----------|
| 断言正确行为,而非当前行为 | 测试断言"应该是什么"(基于业务逻辑),让测试真实失败 |
| 不 Mock 被测对象本身 | 只 Mock 外部依赖(LLM、网络、文件系统);被测函数真实执行 |
| 反向证伪 | 每个测试用 `@pytest.mark.xfail(strict=True)` 标记,配套元测试验证"修复后能通过" |
| 确定性 | 凡涉及随机的,断言两次运行结果一致 |
| 数据隔离 | 每个测试用 fixture 创建独立数据,不依赖类变量、不依赖测试顺序 |
| ci_guard 兼容 | 用 `except SpecificError as e:` 或 `pytest.mark.xfail`,不用 `except Exception: pass` 或 `pytest.skip` |

## 文件结构

```
tests/exposed_bugs/
├── __init__.py
├── conftest.py                          # 共享 fixture:isolated_approval_manager, isolated_tracker 等
├── README.md                            # 本文件
├── test_bug_001_mutation_kill_rate_fake.py          # 变异测试 kill_rate 造假
├── test_bug_002_cyclic_dependency_silent_success.py # 循环依赖静默成功
├── test_bug_003_unknown_task_type_silent_success.py # 未知任务类型静默成功
├── test_bug_004_approver_query_param_forgery.py     # approve_patch 的 approver 可伪造
├── test_bug_005_acknowledge_nonexistent_alert_200.py # 不存在的 alert 返回 200
├── test_bug_006_secure_path_validator_bypass.py     # 路径校验越权
├── test_bug_007_approval_manager_class_var_pollution.py # 类变量污染 + 重复 tx_id
├── test_bug_008_orchestrator_agent_exception_swallowed.py # agent 异常审计断链
└── test_meta_inverse_proof.py           # 元测试:验证每个 xfail 测试可被"修复版"通过
```

## 8 个 Bug 概览

| Bug | 文件 | 根因 | 现有测试反模式 |
|-----|------|------|----------------|
| 001 | src/platform/workflow.py:399-481 | kill_rate=random.random(), details=[] 因异常吞没 | `assert 0 <= kill_rate <= 1.0` 永真 |
| 002 | src/platform/workflow.py:360-375 | 循环依赖返回 [] 后仍 COMPLETED | `assert len(order) == 0` 把 bug 固化 |
| 003 | src/platform/workflow.py:33-82 | WorkflowTask dataclass 不校验枚举,无 handler 仍 completed | `assert status == "completed"` 把 bug 固化 |
| 004 | src/platform/api.py:281-301 | approver 是查询参数,可伪造审批人 | `params={"approver":"admin"}` + 仅断言 status_code |
| 005 | src/platform/api.py:341-351 | 不存在的 alert 返回 200 + success=True | `mock_ack.return_value=True` 只测 happy path |
| 006 | src/governance/security.py:25-37 | resolve() 后检查 ..,ALLOWED_DIRS 子串匹配越权 | 没构造"含关键字但越权"的攻击向量 |
| 007 | src/governance/approval.py:63,177 | _approvals 类变量,重复 tx_id 静默返回 | 把"静默返回旧记录"当 expected |
| 008 | src/governance/orchestrator.py:73,191 | agent 异常未捕获,tracker 审计断链,_classify_exception 空实现 | 只测 executor 异常,全 Mock 屏蔽 |

## 弱断言的 5 种典型形态(反模式)

### 1. 永真比较断言
```python
# 反模式:当 kill_rate=0.0 时永真
assert 0 <= result["report"]["kill_rate"] <= 1.0

# 正确:断言具体业务期望
assert report["mutations"] > 0, "变异体数量必须 > 0"
```

### 2. Mock 屏蔽被测对象
```python
# 反模式:Mock 掉被测对象本身,测的是 Mock 行为
with patch('src.platform.api.orchestrator.approve_and_apply') as mock:
    mock.return_value = {"status": "FIXED"}
    response = client.post(...)
    assert response.status_code == 200

# 正确:只 Mock 外部依赖,被测函数真实执行
with patch.object(orchestrator.executor, 'apply_patch', new=AsyncMock(return_value=True)):
    response = client.post(...)
    record = approval_manager.get_approval(tx_id)
    assert record.approved_by == "admin"  # 验证真实业务字段
```

### 3. 断言固化 bug(把 bug 当 expected behavior)
```python
# 反模式:未知任务类型仍 completed,测试把这个 bug 当 expected
assert result["status"] == "completed"

# 正确:断言正确行为
assert result["status"] == "failed", "未知任务类型应失败"
```

### 4. 仅验证 status code,不验证响应体
```python
# 反模式:只看 status_code,不看业务字段
assert response.status_code == 200

# 正确:验证响应体的业务字段
assert response.status_code == 404
data = response.json()
assert data["success"] is False
assert data.get("error_code") is not None
```

### 5. 忽略数据隔离
```python
# 反模式:用类变量共享状态,setup_method 清理(测试顺序敏感)
def setup_method(self):
    mgr = ApprovalManager()
    mgr._approvals.clear()  # 类变量,所有测试共享

# 正确:用 fixture 创建独立数据
@pytest.fixture
def isolated_approval_manager(tmp_path):
    ApprovalManager._instance = None
    ApprovalManager._approvals = {}
    mgr = ApprovalManager(db_path=str(tmp_path / "test.db"))
    yield mgr
    ApprovalManager._instance = None
    ApprovalManager._approvals = {}
```

## 强断言的 4 条规则

1. **断言正确行为**:基于业务逻辑断言"应该是什么",让测试真实失败
2. **不 Mock 被测对象**:只 Mock 外部依赖(LLM、网络、文件系统),被测函数真实执行
3. **确定性**:凡涉及随机的,断言两次运行结果一致
4. **反向证伪**:配套元测试验证"修复版"能通过,证明断言不是永真

## xfail(strict=True) 使用场景与陷阱

### 使用场景
- 已知 src/ 有 bug,但 .trae-rules 禁止修改 src/
- 测试断言"正确行为",会真实失败
- 用 xfail 标记,既不阻塞 CI 又记录 bug

### 陷阱
- `strict=True` 意味着如果测试"意外通过"(bug 被修复),CI 会失败
- 这是设计意图:提醒开发者把 xfail 改为正式通过测试
- 元测试(test_meta_inverse_proof.py)验证断言不是永真

### 何时移除 xfail
- 当 src/ 修复了 bug,测试开始"意外通过"
- 此时移除 `@pytest.mark.xfail` 装饰器,测试成为正式通过测试

## 反向元测试机制

`test_meta_inverse_proof.py` 防止"xfail 测试本身又是永真断言":

1. 每个 bug 配 1 个 inverse proof
2. 用 Mock 构造"修复版"返回值
3. 调用 xfail 测试的断言逻辑
4. 验证断言在"代码正确"时能通过

**验证逻辑**:
- 元测试通过 + xfail 测试失败 = 断言有效(不是永真)
- 元测试失败 = 断言本身有问题(可能是永真或断言错误)

## 验证流程

```powershell
# 1. ci_guard 零违规
python tests/ci_guard.py

# 2. 暴露 bug 的测试全部 xfail(预期失败)
python -m pytest tests/exposed_bugs/ -v --tb=short
# 期望:N 个 xfailed,0 个 failed,0 个 passed

# 3. 元测试全部通过(反向证伪机制有效)
python -m pytest tests/exposed_bugs/test_meta_inverse_proof.py -v
# 期望:N 个 passed

# 4. 全量测试未破坏现有测试
python -m pytest tests/ -v --ignore=tests/ui
# 期望:现有测试仍通过,新增 N 个 xfailed
```

## 后续行动

1. 提交缺陷报告给技术委员会
2. 技术委员会审批 src/ 修复方案
3. 修复 src/ 后,移除对应测试的 `@pytest.mark.xfail` 装饰器
4. 把"强断言的 4 条规则"纳入 CI 守卫(ci_guard.py)的检测范围
