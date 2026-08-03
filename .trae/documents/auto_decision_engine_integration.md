# AutoDecisionEngine 接入治理主流程

## Context（为什么做这个改动）

`src/governance/auto_decision_engine.py` 的 AutoDecisionEngine 完整实现（6 规则、5 handler、40+ 测试），但 `src/governance/orchestrator.py` 主流程从未调用它——编排器用自己的内联置信度守卫（`AUTO_APPROVE_CONFIDENCE_THRESHOLD = 0.9`）重复实现了一部分功能。

这造成两个真实问题：

1. **真实安全缺口**：orchestrator 审批步骤（[orchestrator.py:184-234](file:///d:/workspace/TestAI/src/governance/orchestrator.py#L184-L234)）**不检查诊断 `source`**。`AIGovernanceResult.source` 可为 `"llm"/"mock"/"fallback"`（[models.py:28](file:///d:/workspace/TestAI/src/governance/models.py#L28)）。当 LLM 不可用走 mock/fallback 降级诊断时，若降级诊断恰好返回高置信度（≥0.9），orchestrator 会自动批准并写入真实代码补丁——这是将"假诊断"转化为"真实代码变更"的 P0 风险。AutoDecisionEngine 的 `rule_auto_approve_high_confidence` 有 mock 守卫（[auto_decision_engine.py:227-233](file:///d:/workspace/TestAI/src/governance/auto_decision_engine.py#L227-L233)），正好补此缺口。

2. **架构半状态**：一个被 40+ 测试覆盖、被 metrics.py 文档声称"已接入"的组件，实际零业务调用。这违反"真实严格"——组件要么接入要么移除，不应停留在"已实现但未启用"的模糊状态。

**预期结果**：AutoDecisionEngine 成为审批决策的 AI 规则引擎，与 ApprovalManager 的结构性闸门互补；mock/fallback 降级诊断不再被自动批准；消除重复的内联置信度守卫。

---

## 设计方案

### 决策架构（两道闸门，互补不重复）

```
diagnosis → [闸门1: ApprovalManager.requires_approval (结构性)] 
          → [闸门2: AutoDecisionEngine.evaluate (AI/置信度/source)]
          → 决策映射 → 执行
```

- **闸门1（保留不变）**：`ApprovalManager.requires_approval(tx_id)`（[approval.py:33-43](file:///d:/workspace/TestAI/src/governance/approval.py#L33-L43)）处理 `security`/`refactoring` patch_type 与变更行数 ≥20 → 强制人工。**此闸门优先级最高，覆盖闸门2的决策。**
  - 原因：AutoDecisionEngine 的 `rule_security_requires_manual`(P80) 被 `rule_auto_approve_high_confidence`(P100) 遮蔽（[auto_decision_engine.py:124-128](file:///d:/workspace/TestAI/src/governance/auto_decision_engine.py#L124-L128) 按优先级降序），SECURITY+高置信会触发 AUTO_APPROVE。这是 engine 内部已知设计，本次不修（用结构闸门兜底）。
- **闸门2（新增）**：`AutoDecisionEngine.evaluate(context, trace_id)` 处理置信度、source 来源、已知模式等 AI 规则。

### 决策映射（用户已确认：REJECT→PENDING_APPROVAL）

| AutoDecisionEngine.decision | orchestrator 行为 | result["status"] |
|---|---|---|
| `AUTO_APPROVE`（且闸门1通过） | `approval_mgr.approve(approver="system")` + 执行补丁 | `FIXED` |
| `REJECT` | 不批准、不执行补丁 | `PENDING_APPROVAL`（保留人工，零行为变更） |
| `REQUIRE_MANUAL` / `ESCALATE` / `AUTO_ROLLBACK` | 不批准、不执行补丁 | `PENDING_APPROVAL`（AUTO_ROLLBACK 在审批阶段无补丁可回滚，降级人工） |
| 闸门1 `requires_approval=True` | 覆盖 engine 决策 | `PENDING_APPROVAL` |
| engine 异常 | 安全降级 | `PENDING_APPROVAL` |

**关键**：所有非 AUTO_APPROVE 一律 PENDING_APPROVAL。只有 AUTO_APPROVE + 闸门1通过 才进入补丁执行。这保证零行为回退（当前所有非自动批准路径都是 PENDING_APPROVAL）。

### mock/fallback 守卫修复

[auto_decision_engine.py:229](file:///d:/workspace/TestAI/src/governance/auto_decision_engine.py#L229) `source == "mock"` → `source in ("mock", "fallback")`。fallback 是规则降级诊断，与 mock 同等不可信，不应自动批准。

---

## 实现步骤

### A. 修改 src/（业务代码）

#### A1. `src/governance/auto_decision_engine.py`
- **L229**：`if source == "mock":` → `if source in ("mock", "fallback"):`
- **L230-232 日志**：更新为 `source in ('mock','fallback') 诊断不自动批准`

#### A2. `src/governance/models.py`（新增 Pydantic 模型，满足"跨模块通信必须 Pydantic 强校验"规则）
新增 `DecisionContextInput` Pydantic 模型，字段：
```python
class DecisionContextInput(BaseModel):
    confidence: float = 0.0
    is_fixable: bool = False
    source: str = "llm"
    patch_type: str = "functional"
    consecutive_failures: int = 0
    patch_category: str = ""
    status: str = ""
```
orchestrator 构造此模型实例（强校验），再 `.model_dump()` 传给 `engine.evaluate()`（engine 签名 `Dict[str, Any]` 不变，向后兼容 40+ 测试）。

#### A3. `src/governance/orchestrator.py`
- **import 区**（L9-31 之间）：新增 `from src.governance.auto_decision_engine import AutoDecisionEngine` 与 `from src.governance.models import DecisionContextInput`（合并到现有 models import）
- **删除 L33-35**：`AUTO_APPROVE_CONFIDENCE_THRESHOLD = 0.9` 常量及其注释（被 AutoDecisionEngine 规则替代）
- **`__init__`（L62-69）**：`self._metrics = GovernanceMetrics()` 之后新增 `self._decision_engine = AutoDecisionEngine()`（单例，无循环 import 风险）
- **替换 L186-224**（内联置信度守卫块）为：
  1. 用 `DecisionContextInput` 构造并校验决策上下文（`confidence=diagnosis.confidence_score`, `is_fixable=diagnosis.is_fixable`, `source=diagnosis.source`, `patch_type=proposal.patch_type.value`, 其余默认）
  2. `try: engine_decision = self._decision_engine.evaluate(ctx.model_dump(), trace_id=tx_id) except (ValueError, TypeError) as e: engine_decision = None`（安全降级 + 结构化日志）
  3. 闸门1：`structural = self.approval_mgr.requires_approval(tx_id)`；若 True → `effective = "REQUIRE_MANUAL"`
  4. 否则取 `engine_decision.decision`（engine 为 None 时降级 REQUIRE_MANUAL）
  5. 决策映射：AUTO_APPROVE → `approval_mgr.approve()` + tracker `APPROVAL_GRANTED` 事件，**继续落入原有 L236-296 的 governance_transaction 补丁执行块（不动）**；其他 → PENDING_APPROVAL + tracker `APPROVAL_REQUIRED` 事件 + return
- **保留 L184** `create_approval(tx_id, proposal, context)` 调用顺序不变（`requires_approval` 依赖 record 已创建，见 [approval.py:168-177](file:///d:/workspace/TestAI/src/governance/approval.py#L168-L177)）
- **保留 L226-296** governance_transaction + apply_patch + 收敛检查块**完全不动**

### B. 修改 tests/（仅测试文件）

#### B1. `tests/governance/test_p1_confidence_guard.py`
- **更新 docstring L11-13**：删除 `AUTO_APPROVE_CONFIDENCE_THRESHOLD` 引用，改为"AutoDecisionEngine.rule_auto_approve_high_confidence (≥0.9) + source 守卫"
- **5 个测试断言全部不变**（已验证：REJECT→PENDING_APPROVAL 决策下 5 个测试全部通过）：
  - `test_low_confidence_forces_manual_approval`（0.3）：REJECT→PENDING_APPROVAL ✓
  - `test_high_confidence_auto_approved`（0.95, llm）：AUTO_APPROVE→FIXED ✓
  - `test_boundary_confidence_just_below_threshold`（0.89）：默认 REQUIRE_MANUAL→PENDING_APPROVAL ✓
  - `test_boundary_confidence_at_threshold_auto_approved`（0.9）：AUTO_APPROVE→FIXED ✓
  - `test_security_patch_always_manual_even_high_confidence`（SECURITY+0.99）：闸门1覆盖→PENDING_APPROVAL ✓
- **setup_method L46-52**：现有 patch 链未 patch AutoDecisionEngine，orchestrator.__init__ 会实例化单例。需在 setup 末尾增加 `AutoDecisionEngine()._history.clear()` 防止单例 history 跨测试污染（参考 test_auto_decision_engine.py:11-16 的 clean_engine fixture 模式）

#### B2. `tests/exposed_bugs/test_bug_mock_diagnosis_unmarked.py`
- 在 `TestAutoDecisionEngineIgnoresSource` 类新增 `test_fallback_source_does_not_get_auto_approved`：`source="fallback"`, confidence=0.95 → 断言 `decision.decision != "AUTO_APPROVE"`（与 mock 测试对称，验证 fallback 守卫）
- 现有 `test_mock_source_does_not_get_auto_approved`（mock）与 `test_llm_source_can_get_auto_approved`（llm）断言不变，仍通过

#### B3. 新增 `tests/governance/test_orchestrator_decision_engine_integration.py`
覆盖五场景（用户规则：正向/负向/边界/异常/依赖）：

| 场景 | 输入 | 期望 status | approve调用 | apply_patch调用 |
|---|---|---|---|---|
| 正向：高置信 LLM+FUNCTIONAL+小补丁 | conf=0.95, source=llm, type=functional, requires_approval=False | FIXED | 1 | 1 |
| 正向：mock 高置信被拦截（核心修复回归） | conf=0.95, source=mock, type=functional, requires_approval=False | PENDING_APPROVAL | 0 | 0 |
| 正向：fallback 高置信被拦截 | conf=0.95, source=fallback, type=functional, requires_approval=False | PENDING_APPROVAL | 0 | 0 |
| 负向：极低置信 | conf=0.3, source=llm, type=functional, requires_approval=False | PENDING_APPROVAL | 0 | 0 |
| 边界：0.5 阈值 | conf=0.5, source=llm, type=functional | PENDING_APPROVAL | 0 | 0 |
| 边界：0.9 阈值 | conf=0.9, source=llm, type=functional | FIXED | 1 | 1 |
| 依赖：SECURITY+高置信被结构闸门拦截 | conf=0.99, source=llm, type=security, requires_approval=True | PENDING_APPROVAL | 0 | 0 |
| 异常：engine 抛 ValueError | mock engine.evaluate side_effect=ValueError | PENDING_APPROVAL（安全降级） | 0 | 0 |
| 异常：engine 抛 TypeError | 同上 | PENDING_APPROVAL | 0 | 0 |

断言须验证具体业务逻辑（status + approve/apply_patch 调用次数 + tracker 事件类型），禁止仅验证 status 的弱断言。

---

## 关键文件

- [src/governance/orchestrator.py](file:///d:/workspace/TestAI/src/governance/orchestrator.py)（核心改动：import + __init__ + 删常量 + 替换 L186-224）
- [src/governance/auto_decision_engine.py](file:///d:/workspace/TestAI/src/governance/auto_decision_engine.py)（L229 mock→mock/fallback 守卫）
- [src/governance/models.py](file:///d:/workspace/TestAI/src/governance/models.py)（新增 DecisionContextInput）
- [src/governance/approval.py](file:///d:/workspace/TestAI/src/governance/approval.py)（不改，仅参考 requires_approval 逻辑）
- [tests/governance/test_p1_confidence_guard.py](file:///d:/workspace/TestAI/tests/governance/test_p1_confidence_guard.py)（更新 docstring + setup 清理）
- [tests/exposed_bugs/test_bug_mock_diagnosis_unmarked.py](file:///d:/workspace/TestAI/tests/exposed_bugs/test_bug_mock_diagnosis_unmarked.py)（新增 fallback 测试）
- tests/governance/test_orchestrator_decision_engine_integration.py（新增）

---

## 验证

1. **单元测试**：`python -m pytest tests/governance/test_p1_confidence_guard.py tests/governance/test_auto_decision_engine.py tests/governance/test_orchestrator_decision_engine_integration.py tests/exposed_bugs/test_bug_mock_diagnosis_unmarked.py -v` — 全部通过
2. **回归测试**：`python -m pytest tests/governance/ tests/worker/ tests/exposed_bugs/ -q --tb=short` — 0 failed（重点确认 test_e2e_governance_closed_loop.py、test_orchestrator.py、test_bug_014_orchestrator_approval_flow.py、test_s_level_core.py 通过）
3. **全量测试**：`python -m pytest tests/ -q --tb=line --timeout=60` — 与接入前基线对比（1415 passed, 114 skipped），不引入新失败
4. **指标验证**：确认 `testai_governance_flow_total{status="FIXED"}` 与 `testai_governance_decision_total{decision="AUTO_APPROVE"}` 在 AUTO_APPROVE 路径同时递增（不同 Counter，无重复计数）

---

## 已知限制 / 技术债（诚实声明）

1. **`consecutive_failures` 暂传 0**：`rule_escalate_multiple_failures`(P60) 不会触发。未来需从 GovernanceTracker 查询组件历史失败次数。代码中标注 TODO。
2. **`patch_category` 暂传空**：`rule_auto_approve_known_pattern`(P70) 不会触发。未来需从 PatchProposal 派生分类。
3. **engine 内部规则优先级遮蔽**：`rule_security_requires_manual`(P80) 被 P100 遮蔽，SECURITY 守卫实际由 ApprovalManager 结构闸门负责，非 engine。本次不修 engine 内部设计。
4. **AUTO_ROLLBACK 降级**：审批阶段无补丁可回滚，AUTO_ROLLBACK 决策降级为 PENDING_APPROVAL。该规则为收敛阶段设计，审批阶段不适用。
5. **GovernanceHistory 内存存储**：`record_decision` 仅追加内存列表（[governance_history.py:31](file:///d:/workspace/TestAI/src/governance/governance_history.py#L31)），无持久化。测试需清理单例 state。
