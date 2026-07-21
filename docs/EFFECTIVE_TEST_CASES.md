# TestAI系统有效测试用例梳理

> 文档版本：v1.0  
> 创建日期：2026-07-21  
> 项目名称：TestAI — AI驱动的自治测试与智能诊断平台

---

## 一、有效测试用例定义

**有效测试用例**是指能够真实验证业务逻辑正确性、发现生产环境问题的测试用例，满足以下标准：

| 标准 | 说明 | 示例 |
|------|------|------|
| **业务逻辑验证** | 断言必须验证具体业务逻辑，禁止仅验证status的弱断言 | `assert context.results["httpbin_post_test"]["status"] == "PASSED"` |
| **真实场景覆盖** | 覆盖正向、负向、边界、异常、依赖五种场景 | 见场景分类 |
| **非Mock依赖** | 对核心业务路径避免过度使用Mock，优先使用真实依赖 | `test_real_http_api_full_flow`使用真实httpx客户端 |
| **变异测试有效** | 测试用例能够检测到代码变更（Kill Rate ≥80%） | `CustomMutationTester`验证 |
| **回归防护** | 能够捕捉到历史缺陷的复现 | 黄金数据集验证 |

---

## 二、有效测试用例分类

### 2.1 按有效性等级分类

| 等级 | 定义 | 占比目标 |
|------|------|----------|
| **S级（核心）** | 验证核心业务逻辑，直接影响系统稳定性 | ≥20% |
| **A级（重要）** | 验证重要业务功能，影响用户体验 | ≥40% |
| **B级（一般）** | 验证辅助功能，影响范围有限 | ≤30% |
| **C级（弱）** | 仅验证基本状态，无业务逻辑验证 | ≤10% |

### 2.2 按场景类型分类

| 场景类型 | 定义 | 有效测试特征 |
|----------|------|--------------|
| **正向测试** | 正常输入，预期成功 | 验证输出值、状态、数据完整性 |
| **负向测试** | 异常输入，预期失败 | 验证错误信息、错误码、异常类型 |
| **边界测试** | 边界值输入 | 验证边界条件处理、溢出处理 |
| **异常测试** | 系统异常场景 | 验证异常捕获、降级策略、熔断机制 |
| **依赖测试** | 外部依赖场景 | 验证依赖失败时的处理、Mock策略 |

---

## 三、有效测试用例清单

### 3.1 核心有效测试用例（S级）

| 测试用例 | 文件路径 | 覆盖场景 | 有效特征 |
|----------|----------|----------|----------|
| `test_governance_e2e_loop` | `tests/governance/test_e2e_governance.py` | 完整治理闭环 | 验证补丁应用前后代码变化 |
| `test_real_http_api_full_flow` | `tests/integration/test_real_e2e_business.py` | 真实HTTP API全流程 | 使用真实httpx客户端，验证业务逻辑 |
| `test_baseline_validation_passed` | `tests/governance/test_baseline_convergence.py` | 基线验证通过 | 验证收敛分数计算 |
| `test_approval_requires_approval_security` | `tests/governance/test_approval.py` | 安全补丁审批 | 验证审批规则 |
| `test_token_validation` | `tests/security/test_auth.py` | Token验证 | 验证JWT Token有效性 |

### 3.2 重要有效测试用例（A级）

| 测试用例 | 文件路径 | 覆盖场景 | 有效特征 |
|----------|----------|----------|----------|
| `test_patches_method_in_target_class` | `tests/governance/test_class_match_precision.py` | 类方法精确匹配 | 验证`.patched`标志和代码变更 |
| `test_rejects_method_in_wrong_class` | `tests/governance/test_class_match_precision.py` | 错误类不匹配 | 验证`.patched`为False |
| `test_circuit_breaker_trip` | `tests/governance/test_resilience.py` | 熔断触发 | 验证状态切换 |
| `test_convergence_score_calculation` | `tests/governance/test_baseline_convergence.py` | 收敛分数计算 | 验证分数公式 |
| `test_auth_login` | `tests/platform/test_api.py` | 用户登录 | 验证Token生成 |
| `test_auth_login_invalid_credentials` | `tests/platform/test_api.py` | 无效凭证 | 验证错误处理 |
| `test_workflow_with_dependencies` | `tests/platform/test_workflow.py` | 工作流依赖 | 验证拓扑排序 |

### 3.3 一般有效测试用例（B级）

| 测试用例 | 文件路径 | 覆盖场景 | 有效特征 |
|----------|----------|----------|----------|
| `test_record_event` | `tests/governance/test_tracker.py` | 事件记录 | 验证事件持久化 |
| `test_get_summary` | `tests/governance/test_tracker.py` | 统计摘要 | 验证统计计算 |
| `test_get_config_section` | `tests/platform/test_config_manager.py` | 获取配置 | 验证配置读取 |
| `test_update_config_section` | `tests/platform/test_config_manager.py` | 更新配置 | 验证配置写入 |
| `test_file_lock_acquire_release` | `tests/governance/test_file_lock.py` | 文件锁 | 验证并发控制 |

### 3.4 弱测试用例（C级）

| 测试用例 | 文件路径 | 覆盖场景 | 弱特征 |
|----------|----------|----------|--------|
| `test_health_check` | `tests/platform/test_api.py` | 健康检查 | 仅验证状态码 |
| `test_get_summary` | `tests/platform/test_dashboard.py` | 仪表盘摘要 | 仅验证返回格式 |

---

## 四、有效测试用例特征分析

### 4.1 强断言特征

有效测试用例必须包含以下类型的强断言：

| 断言类型 | 示例 | 说明 |
|----------|------|------|
| **值断言** | `assert response_body["json"]["username"] == "testuser"` | 验证具体值 |
| **状态断言** | `assert context.results["step_id"]["status"] == "PASSED"` | 验证执行状态 |
| **标志断言** | `assert transformer.patched is True` | 验证操作标志 |
| **计数断言** | `assert tree.code.count('return "patched"') == 2` | 验证数量 |
| **存在性断言** | `assert "import json" in result` | 验证内容存在 |
| **不存在性断言** | `assert "Old logic" not in result` | 验证内容不存在 |

### 4.2 弱断言模式（需改进）

| 弱断言类型 | 示例 | 问题 |
|------------|------|------|
| **仅状态码** | `assert response.status_code == 200` | 无法验证业务逻辑 |
| **仅类型检查** | `assert isinstance(result, dict)` | 无法验证具体值 |
| **仅存在检查** | `assert "data" in response` | 无法验证数据完整性 |

---

## 五、真实场景测试用例

### 5.1 真实HTTP API测试

```python
# tests/integration/test_real_e2e_business.py
@pytest.mark.asyncio
async def test_real_http_api_full_flow(self):
    async with httpx.AsyncClient() as real_client:
        context = ExecutionContext(
            case_id="real_http_e2e_001",
            env={"base_url": "https://httpbin.org"},
            vars={"user_id": "12345"},
        )
        test_steps = [...]
        pipeline = ExecutionPipeline(
            processors=[DataProcessor(), HTTPProcessor(), AssertionProcessor()]
        )
        await pipeline.run(context, test_steps, real_client)
        # 强断言验证业务逻辑
        assert context.results["httpbin_post_test"]["status"] == "PASSED"
        assert response_body["json"]["username"] == "testuser"
```

### 5.2 黄金数据集验证

```python
# tests/integration/test_real_e2e_business.py
def test_golden_dataset_full_validation(self):
    baseline_manager = GoldenBaselineManager()
    for baseline_id in baseline_manager.get_all_baseline_ids():
        actual_data = self._generate_actual_data(baseline_id)
        result = baseline_manager.validate_against_baseline(baseline_id, actual_data)
        # 验证基线匹配
        assert result["passed"] is True, f"Baseline {baseline_id} validation failed"
```

---

## 六、变异测试有效性验证

### 6.1 变异测试Kill Rate要求

| 模块 | Kill Rate阈值 | 当前状态 |
|------|--------------|----------|
| 治理模块 | ≥85% | ✅ 达标 |
| 平台模块 | ≥80% | ✅ 达标 |
| 安全模块 | ≥90% | ✅ 达标 |
| AI模块 | ≥75% | ⚠️ 需提升 |

### 6.2 变异测试有效用例示例

```python
# tests/utils/custom_mutation_test.py
def test_mutation_kill_rate():
    tester = CustomMutationTester()
    result = tester.run("src/governance/executor.py", "tests/governance/test_executor.py")
    # 验证Kill Rate
    assert result.kill_rate >= 0.85, f"Kill rate {result.kill_rate} below threshold"
    assert result.total_mutations > 0, "No mutations generated"
    assert result.killed_mutations > 0, "No mutations killed"
```

---

## 七、有效测试用例优化建议

### 7.1 当前问题

| 问题 | 影响 | 建议 |
|------|------|------|
| C级测试占比偏高 | 无法有效验证业务逻辑 | 将弱断言升级为强断言 |
| AI模块变异测试Kill Rate偏低 | 测试用例不够有效 | 增加更多负向和边界测试 |
| 部分Mock测试过度 | 无法验证真实场景 | 增加真实依赖测试 |

### 7.2 优化方向

1. **升级弱断言**：将`test_health_check`等仅验证状态码的测试升级为验证具体业务逻辑
2. **增加真实场景测试**：扩展`test_real_e2e_business.py`，增加更多真实API测试
3. **增强AI模块测试**：为AI模块增加更多变异测试和边界测试
4. **完善依赖测试**：增加对外部依赖（数据库、消息队列）的测试

---

## 八、有效测试用例执行策略

### 8.1 测试执行优先级

```
执行优先级:
┌──────────────────────────────────────────────────────────────────────┐
│ P0: S级测试          ██████████████████████                         │
│     (核心业务逻辑)                                                    │
├──────────────────────────────────────────────────────────────────────┤
│ P1: A级测试          █████████████████████████████████              │
│     (重要业务功能)                                                    │
├──────────────────────────────────────────────────────────────────────┤
│ P2: B级测试          ███████████████████                            │
│     (辅助功能)                                                        │
├──────────────────────────────────────────────────────────────────────┤
│ P3: C级测试          ████                                           │
│     (基本状态验证)                                                    │
└──────────────────────────────────────────────────────────────────────┘
```

### 8.2 CI/CD集成策略

| 阶段 | 执行测试 | 失败条件 |
|------|----------|----------|
| PR检查 | P0 + P1 | 任一测试失败 |
| 预发布 | P0 + P1 + P2 | 任一测试失败 |
| 生产发布 | 全部测试 | 任一测试失败 |

---

## 九、有效测试用例统计

### 9.1 有效性分布

| 等级 | 数量 | 占比 |
|------|------|------|
| S级 | ~5 | 2% |
| A级 | ~60 | 22% |
| B级 | ~180 | 66% |
| C级 | ~26 | 10% |

### 9.2 场景类型分布

| 场景类型 | 数量 | 占比 |
|----------|------|------|
| 正向测试 | ~120 | 44% |
| 负向测试 | ~80 | 30% |
| 边界测试 | ~35 | 13% |
| 异常测试 | ~20 | 7% |
| 依赖测试 | ~16 | 6% |

---

*文档结束*