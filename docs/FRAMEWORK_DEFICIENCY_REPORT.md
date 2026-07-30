# Framework Deficiency Report - 测试体系漏测的 8 个 Bug

**提交日期**: 2026-07-26
**提交人**: DevOps 测试专家
**提交对象**: 技术委员会
**文档状态**: 待审批

## 摘要

本报告列出 TestAI 项目 `src/` 中被现有测试体系掩盖的 8 个 bug。这些 bug 已通过 `tests/exposed_bugs/` 下的强断言测试暴露(用 `pytest.mark.xfail(strict=True)` 标记)。根据 `.trae-rules` 第 1-2 条,`src/` 是只读核心,本报告请求技术委员会审批修复方案。

**核心矛盾**:测试通过率 97.6%(488/500),但 QC 审查报告显示测试有效度仅 65%。8 个 bug 被掩盖的根因是测试断言永真、Mock 屏蔽被测对象、把 bug 当 expected behavior 固化。

---

## Bug 列表

### BUG-001: 变异测试 kill_rate 造假 + details 永远为空

| 字段 | 内容 |
|------|------|
| **严重级别** | P0 |
| **文件路径** | `src/platform/workflow.py` |
| **行号** | 399-481(`_handle_mutation_test_task`) |
| **根因** | L450 `is_killed = random.random() > 0.25` 不运行任何测试,kill_rate 是纯随机数;L456 `ast.get_source_segment(mutated_code, node).strip()` 中 `mutated_code` 是 ast.unparse 返回的新字符串,但 node 仍属于原 tree,lineno/col_offset 已被 fix_missing_locations 改写,get_source_segment 返回 None,.strip() 抛 AttributeError;L464-465 `except Exception: pass` 静默吞没,导致 `mutations=[]`、`killed=0`、`survived=0`、`details=[]` |
| **影响范围** | 变异测试功能完全失效,kill_rate 指标不可信 |
| **现有测试漏测原因** | `tests/platform/test_workflow.py:354` `assert 0 <= kill_rate <= 1.0` —— kill_rate=0.0 时永真;L358 `assert mutations == killed + survived` —— 三者都为 0 时永真 |
| **建议修复方案** | 1. 实现真实变异测试运行(运行测试套件判断变异体是否被杀死);2. 移除 `except Exception: pass`,捕获具体异常并记录日志;3. 修复 `ast.get_source_segment` 用法,或在变异前保存 original_code |
| **优先级** | P0(变异测试是核心功能,当前完全失效) |

### BUG-002: 循环依赖静默成功

| 字段 | 内容 |
|------|------|
| **严重级别** | P1 |
| **文件路径** | `src/platform/workflow.py` |
| **行号** | 360-375(`_calculate_execution_order`)+ 295-334(`execute_workflow`) |
| **根因** | `_calculate_execution_order` 用 Kahn 算法,循环依赖返回空列表 `[]`;`execute_workflow` 遍历空列表跳过所有任务,仍设置 `instance.status = WorkflowStatus.COMPLETED`,返回 `{"status": "completed", "task_results": {}}` |
| **影响范围** | 循环依赖工作流被误判为成功,0 个任务执行却返回 completed |
| **现有测试漏测原因** | `tests/platform/test_workflow.py:256-266` 只断言 `len(order) == 0`,把"循环依赖静默丢弃"当 expected behavior,没测试 `execute_workflow` 应返回 failed |
| **建议修复方案** | 1. `_calculate_execution_order` 检测循环依赖,抛 `ValueError("Cyclic dependency detected")`;2. `execute_workflow` 捕获并设置 `instance.status = FAILED`,返回 `{"status": "failed", "error": "Cyclic dependency"}` |
| **优先级** | P1 |

### BUG-003: 未知任务类型静默成功

| 字段 | 内容 |
|------|------|
| **严重级别** | P1 |
| **文件路径** | `src/platform/workflow.py` |
| **行号** | 33-61(`WorkflowTask` dataclass)+ 230-235(`_register_default_handlers`)+ 377-382(`_execute_task`) |
| **根因** | 1. `WorkflowTask` 是 `@dataclass` 而非 Pydantic 模型,`type` 字段不强制校验枚举;2. `_register_default_handlers` 只注册 5 个 handler(GOVERNANCE/MUTATION_TEST/APPROVAL/MONITORING/DELAY),API_TEST 和 CONDITIONAL 无 handler;3. `_execute_task` 在 handler 缺失时返回 `{"status": "skipped"}`,`execute_workflow` 仍设置 COMPLETED |
| **影响范围** | 未知/未注册任务类型"成功完成",违反用户规则"禁止使用弱类型的隐式转换" |
| **现有测试漏测原因** | `tests/platform/test_workflow.py:217-230` `assert result["status"] == "completed"` 把 bug 当 expected behavior 固化 |
| **建议修复方案** | 1. `WorkflowTask` 改为 Pydantic 模型,`type` 字段强制校验 TaskType 枚举;2. `_register_default_handlers` 补全 API_TEST 和 CONDITIONAL handler;3. `_execute_task` 在 handler 缺失时抛异常或返回 failed,`execute_workflow` 检测 skipped 任务后设为 FAILED |
| **优先级** | P1(违反用户规则的强校验要求) |

### BUG-004: approve_patch 的 approver 是查询参数,可伪造审批人身份

| 字段 | 内容 |
|------|------|
| **严重级别** | P1(安全问题) |
| **文件路径** | `src/platform/api.py` |
| **行号** | 281-301(`approve_patch`)+ `src/governance/approval.py:213` |
| **根因** | L284 `approver: str` 是查询参数(无 Depends),L296 `await orchestrator.approve_and_apply(tx_id, approver, reason)` 用查询参数的 approver,`approval.py:213` `record.approved_by = approver` 审计日志记录伪造的 approver。已通过 `require_permission` 获取认证用户 user,但未使用 |
| **影响范围** | 任何持 APPROVE_PATCH 权限的用户可伪造他人审批,审计日志不可信 |
| **现有测试漏测原因** | `tests/platform/test_api.py:143-157` `params={"approver": "admin"}` 传查询参数,仅断言 `status_code == 200`,Mock 掉 `orchestrator.approve_and_apply` 无法验证 approver 来源 |
| **建议修复方案** | 1. 移除 `approver` 查询参数,从 `user: User = Depends(require_permission(...))` 获取;2. `approve_and_apply(tx_id, user.username, reason)`;3. 审计日志记录 `user.username` 而非查询参数 |
| **优先级** | P1(审计日志不可信是合规风险) |

### BUG-005: acknowledge_alert 不存在的 alert 返回 200

| 字段 | 内容 |
|------|------|
| **严重级别** | P2 |
| **文件路径** | `src/platform/api.py` |
| **行号** | 341-351(`acknowledge_alert`) |
| **根因** | L346 `result = alert_manager.acknowledge_alert(alert_id)` 返回 bool,L347-351 不管 result True/False 都返回 `success=True, message="Alert acknowledged"`,不存在的 alert 返回 200 + success=True + acknowledged=False |
| **影响范围** | HTTP 语义错误(应 404),message 误导(说 acknowledged 但实际没找到) |
| **现有测试漏测原因** | `tests/platform/test_api.py:198-204` `mock_ack.return_value = True` 只测 happy path,没测 alert 不存在 |
| **建议修复方案** | 检查 `result`,False 时返回 `HTTPException(status_code=404, detail="Alert not found")` 或 `ApiResponse(success=False, error_code="ALERT_NOT_FOUND")` |
| **优先级** | P2 |

### BUG-006: SecurePathValidator 路径校验失效 + ALLOWED_DIRS 子串匹配越权

| 字段 | 内容 |
|------|------|
| **严重级别** | P1(安全问题) |
| **文件路径** | `src/governance/security.py` |
| **行号** | 7-42(`SecurePathValidator.validate_path`) |
| **根因** | 1. L25 `path = Path(target_path).resolve()` 先 resolve,L30 `if ".." in str(path): return False` 检查永不触发(resolve 后 .. 已被解析,死代码);2. L33-37 遍历 `path.parts`,只要路径中包含 tests/reports/data/output/src 任一目录名就放行,`/etc/tests/passwd` 等越权路径通过校验 |
| **影响范围** | 沙箱越权,攻击者可读写项目目录外的文件 |
| **现有测试漏测原因** | `tests/governance/test_strict_validation.py:180-197` 没构造"含 ALLOWED_DIRS 关键字但越权"的攻击向量;`tests/governance/test_executor.py` 全部 `patch.object(_path_validator, 'validate_path', ...)` 绕过真实校验 |
| **建议修复方案** | 1. 先检查 `..` 再 resolve;2. 改为检查路径是否在项目根目录前缀内(如 `path.startswith(project_root)`),而非检查 parts 是否含 ALLOWED_DIRS |
| **优先级** | P1(沙箱越权是安全漏洞) |

### BUG-007: ApprovalManager 类变量污染 + 重复 tx_id 静默返回

| 字段 | 内容 |
|------|------|
| **严重级别** | P2 |
| **文件路径** | `src/governance/approval.py` |
| **行号** | 63(`_approvals` 类变量)+ 60-77(`__new__`)+ 173-190(`create_approval`) |
| **根因** | 1. L63 `_approvals: Dict[str, ApprovalRecord] = {}` 是类变量声明(类级 `__dict__` 中存在);2. L177-183 `create_approval` 重复 tx_id 时静默返回 existing_record,不抛异常,掩盖 UUID 碰撞或调用方 bug |
| **影响范围** | 测试间数据污染(测试顺序敏感);重复 tx_id 掩盖调用方 bug |
| **现有测试漏测原因** | `tests/governance/test_approval.py:116-118` `setup_method` 用 `_approvals.clear()` 清理共享状态;`test_create_duplicate_approval:145-162` 把"静默返回旧记录"当 expected behavior |
| **建议修复方案** | 1. 移除类变量声明,改为纯实例变量;2. `create_approval` 重复 tx_id 时抛 `ValueError("duplicate tx_id")` |
| **优先级** | P2 |

### BUG-008: orchestrator agent 异常未捕获 + tracker 审计断链 + _classify_exception 空实现

| 字段 | 内容 |
|------|------|
| **严重级别** | P1 |
| **文件路径** | `src/governance/orchestrator.py` |
| **行号** | 46-95(`execute_governance_flow`)+ 191-192(`_classify_exception`) |
| **根因** | 1. L73 `diagnosis = await self.agent.analyze_with_context(context)` 无 try/except,agent 抛异常时向上抛出,tracker 只记录了 L48-53 的 DIAGNOSE_START,无 DIAGNOSE_FAILED 或 PATCH_FAILED,审计链路断链;2. L175-189 的 try/except 只包裹 `governance_transaction` + `executor.apply_patch`,不包裹 agent 调用;3. L191-192 `_classify_exception` 空实现,永远返回 AI_DIAGNOSE,所有异常(包括系统级网络错误)都送 AI 诊断,浪费资源 |
| **影响范围** | agent 异常时审计断链(无法追溯失败原因);网络异常等系统错误被误送 AI 诊断 |
| **现有测试漏测原因** | `tests/governance/test_orchestrator.py:187-228` 只测 `executor.apply_patch.side_effect = Exception`,没测 `agent.analyze_with_context` 异常;全 Mock 屏蔽真实代码;`test_classify_exception:218-228` 只断言返回 AI_DIAGNOSE(把空实现当 expected) |
| **建议修复方案** | 1. 用 try/except 包裹 `agent.analyze_with_context`,捕获异常后 `tracker.record_event(action_type=DIAGNOSE_FAILED)`,返回 `{"status": "FAILED", ...}`;2. 实现 `_classify_exception`,根据 `context.exception_trace` 区分网络异常(RETRY)、代码异常(AI_DIAGNOSE)、系统异常(MANUAL_REQUIRED) |
| **优先级** | P1(审计断链是合规风险) |

---

## 优先级汇总

| 优先级 | Bug 数量 | Bug 编号 |
|--------|----------|----------|
| P0 | 1 | BUG-001 |
| P1 | 5 | BUG-002, BUG-003, BUG-004, BUG-006, BUG-008 |
| P2 | 2 | BUG-005, BUG-007 |

---

## 测试体系改进建议(超出 8 个 bug 修复)

### 1. 强化 ci_guard.py 检测规则

当前 ci_guard.py 不检测以下反模式,建议新增检测:

- **永真比较断言**:如 `assert 0 <= x <= 1.0`、`assert count >= 0`、`assert len(x) >= 0`
- **仅 status code 断言**:如 `assert response.status_code == 200` 后无响应体验证
- **Mock 被测对象**:如 `patch('src.platform.api.被测函数')`(应只 Mock 外部依赖)
- **断言固化当前行为**:测试断言与代码现状完全一致,无独立业务依据

### 2. 建立反向元测试机制

`tests/exposed_bugs/test_meta_inverse_proof.py` 已建立机制,建议扩展到所有测试模块:
- 每个 xfail 测试必须配套 1 个 inverse proof
- 元测试通过 + xfail 测试失败 = 断言有效

### 3. 引入 mutation testing 真实执行

当前变异测试功能(BUG-001)完全失效,建议:
- 短期:用 cosmic-ray 或 mutmut 在 CI 中运行真实变异测试
- 中期:设置 kill rate ≥ 80% 质量门禁
- 长期:把变异测试纳入 nightly 流水线

### 4. 测试设计哲学转变

从"以通过为目标"转向"以证伪为目标":
- 测试用例从"代码能跑通"出发 → 从"业务逻辑应该是什么"出发
- Mock 从"便捷工具"出发 → 从"无奈的妥协"出发(只 Mock 外部依赖)
- expected behavior 从"代码现状"出发 → 从"需求文档/业务逻辑"出发

---

## 审批请求

请技术委员会审批:

1. **8 个 bug 的修复方案**(需修改 src/,违反 .trae-rules 第 1 条,需特批)
2. **ci_guard.py 强化检测规则**(tests/ 下,无需特批)
3. **mutation testing CI 集成**(CI/CD 配置,需审批)

修复后,`tests/exposed_bugs/` 下的 xfail 测试应移除 `@pytest.mark.xfail` 装饰器,成为正式通过测试。

**审核签字**: _______________(技术委员会主席)

**审核日期**: _______________
