# TestAI系统测试用例梳理

> 文档版本：v2.0  
> 创建日期：2026-07-21  
> 项目名称：TestAI — AI驱动的自治测试与智能诊断平台

---

## 一、测试用例总览

### 1.1 测试分层统计

| 测试层级 | 目录 | 测试文件数 | 测试用例数 | 覆盖率目标 |
|----------|------|------------|------------|------------|
| **治理测试** | `tests/governance/` | 24 | **304** | 95% |
| **平台测试** | `tests/platform/` | 4 | **138** | 97% |
| **安全测试** | `tests/security/` | 3 | **65** | 100% |
| **集成测试** | `tests/integration/` | 8 | **56** | 全链路 |
| **AI模块测试** | `tests/ai/` | 1 | **27** | 90% |
| **单元测试** | `tests/unit/` | 4 | **14** | 核心逻辑 |
| **Worker测试** | `tests/worker/` | 1 | **13** | 100% |
| **性能测试** | `tests/performance/` | 1 | **4** | N/A |
| **合计** | - | 46 | **621** | - |

### 1.2 测试分类统计

| 测试类型 | 数量 | 占比 |
|----------|------|------|
| 正向测试 | ~350 | 56% |
| 负向测试 | ~150 | 24% |
| 边界测试 | ~60 | 10% |
| 异常测试 | ~35 | 6% |
| 依赖测试 | ~26 | 4% |

### 1.3 S级测试统计

| 指标 | 数量 | 占比 |
|------|------|------|
| S级测试总数 | **44** | **100%**（核心模块） |
| S级覆盖模块 | 12 | governance/platform/security/users/teams |

---

## 二、单元测试用例

### 2.1 核心模型测试 (`tests/unit/test_models.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_assertion_model_validation` | Assertion模型字段校验 | 正向 |
| `test_assertion_invalid_type` | 无效断言类型 | 负向 |
| `test_contract_model_validation` | Contract模型字段校验 | 正向 |
| `test_result_model_validation` | Result模型字段校验 | 正向 |

### 2.2 处理器测试 (`tests/unit/test_processors.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_http_processor_success` | HTTP处理器成功请求 | 正向 |
| `test_http_processor_failure` | HTTP处理器失败请求 | 负向 |
| `test_data_processor_transform` | 数据处理器转换 | 正向 |
| `test_assertion_processor_validate` | 断言处理器验证 | 正向 |

### 2.3 管道测试 (`tests/unit/test_pipleline.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_pipeline_execution` | 管道执行流程 | 正向 |
| `test_pipeline_error_handling` | 管道错误处理 | 异常 |

### 2.4 gRPC处理器测试 (`tests/unit/test_grpc_processor.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_grpc_processor_call` | gRPC调用 | 正向 |
| `test_grpc_processor_error` | gRPC错误处理 | 异常 |

---

## 三、治理测试用例

### 3.1 S级核心测试 (`tests/governance/test_s_level_core.py`)

| 测试类 | 测试数量 | 覆盖模块 |
|--------|----------|----------|
| `TestSLevelApprovalPersistence` | 2 | 审批持久化 |
| `TestSLevelGovernanceTracker` | 2 | 治理追踪 |
| `TestSLevelBaselineConvergence` | 2 | 基线收敛 |
| `TestSLevelSecurityValidation` | 2 | 安全校验 |
| `TestSLevelAuthSecurity` | 2 | 认证安全 |
| `TestSLevelUserPersistence` | 2 | 用户持久化 |
| `TestSLevelTeamPersistence` | 2 | 团队持久化 |
| `TestSLevelConfigPersistence` | 2 | 配置持久化 |
| `TestSLevelWorkflowEngine` | 3 | 工作流引擎 |
| `TestSLevelTransformerPrecision` | 2 | 代码转换器 |
| `TestSLevelGovernanceExecutor` | 2 | 治理执行器 |
| `TestSLevelGovernanceOrchestrator` | 1 | 治理编排器 |
| `TestSLevelGitTransaction` | 2 | Git事务 |
| `TestSLevelCircuitBreaker` | 2 | 熔断保护 |
| `TestSLevelFileLock` | 1 | 文件锁 |
| `TestSLevelAPIEndpoints` | 2 | API端点 |
| `TestSLevelPermissionControl` | 2 | 权限控制 |
| `TestSLevelAlertManagement` | 2 | 告警管理 |
| `TestSLevelDatabasePersistence` | 2 | 数据库持久化 |
| `TestSLevelGoldenBaseline` | 2 | 黄金基线 |
| `TestSLevelApprovalWorkflow` | 2 | 审批工作流 |
| `TestSLevelMutationTesting` | 1 | 变异测试 |
| **合计** | **44** | - |

### 3.2 审批机制测试 (`tests/governance/test_approval.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_create_approval` | 创建审批记录 | 正向 |
| `test_approve_patch` | 审批通过 | 正向 |
| `test_reject_patch` | 审批拒绝 | 负向 |
| `test_approval_expires` | 审批过期 | 边界 |
| `test_requires_approval_security` | 安全补丁需要审批 | 依赖 |
| `test_requires_approval_large_change` | 大变更需要审批 | 依赖 |

### 3.3 基线收敛测试 (`tests/governance/test_baseline_convergence.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_baseline_validation_passed` | 基线验证通过 | 正向 |
| `test_baseline_validation_failed` | 基线验证失败 | 负向 |
| `test_convergence_score_calculation` | 收敛分数计算 | 正向 |
| `test_convergence_score_boundary` | 收敛分数边界 | 边界 |

### 3.4 类匹配精确性测试 (`tests/governance/test_class_match_precision.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_patches_method_in_target_class` | 正确类中的方法被修改 | 正向 |
| `test_rejects_method_in_wrong_class` | 错误类中的方法不被修改 | 负向 |
| `test_handles_no_class_filter` | 无类过滤时匹配所有同名方法 | 边界 |
| `test_raises_error_on_invalid_syntax` | 无效语法抛出异常 | 异常 |

### 3.5 并发控制测试 (`tests/governance/test_concurrency.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_thread_safe_approval` | 审批管理器线程安全 | 正向 |
| `test_thread_safe_tracker` | 追踪器线程安全 | 正向 |

### 3.6 收敛循环测试 (`tests/governance/test_convergence_loop.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_convergence_loop_single_iteration` | 单轮收敛循环 | 正向 |
| `test_convergence_loop_multiple_iterations` | 多轮收敛循环 | 正向 |
| `test_convergence_loop_failure` | 收敛循环失败 | 异常 |

### 3.7 E2E治理测试 (`tests/governance/test_e2e_governance.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_governance_e2e_loop` | 完整治理闭环 | 正向 |

### 3.8 执行器转换器测试 (`tests/governance/test_executor_transformers.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_import_and_function_patching` | 导入和函数补丁 | 正向 |

### 3.9 文件锁测试 (`tests/governance/test_file_lock.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_file_lock_acquire_release` | 文件锁获取和释放 | 正向 |
| `test_file_lock_timeout` | 文件锁超时 | 边界 |

### 3.10 Git管理器测试 (`tests/governance/test_git_manager.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_git_transaction_start_commit` | Git事务开始和提交 | 正向 |
| `test_git_transaction_rollback` | Git事务回滚 | 异常 |

### 3.11 安全测试 (`tests/governance/test_security.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_security_visitor_forbidden_functions` | 检测危险函数 | 正向 |
| `test_security_visitor_forbidden_attrs` | 检测危险属性 | 正向 |
| `test_path_validation` | 路径安全校验 | 正向 |

### 3.12 追踪器测试 (`tests/governance/test_tracker.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_record_event` | 记录事件 | 正向 |
| `test_get_events_by_trace` | 按trace_id查询事件 | 正向 |
| `test_get_summary` | 获取统计摘要 | 正向 |

---

## 四、平台测试用例

### 4.1 API测试 (`tests/platform/test_api.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_health_check` | 健康检查端点 | 正向 |
| `test_auth_login` | 用户登录 | 正向 |
| `test_auth_login_invalid_credentials` | 无效凭证登录 | 负向 |
| `test_auth_refresh_token` | 刷新Token | 正向 |
| `test_get_baseline` | 获取基线 | 正向 |
| `test_get_baseline_not_found` | 获取不存在的基线 | 负向 |
| `test_validate_baseline` | 验证基线 | 正向 |
| `test_get_baseline_convergence` | 获取基线收敛 | 正向 |
| `test_get_baseline_convergence_not_found` | 获取不存在的收敛 | 负向 |
| `test_unauthorized_access` | 未授权访问 | 负向 |
| `test_invalid_token` | 无效Token | 负向 |
| `test_insufficient_permissions` | 权限不足 | 负向 |

### 4.2 配置管理器测试 (`tests/platform/test_config_manager.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_get_config_section` | 获取配置section | 正向 |
| `test_update_config_section` | 更新配置section | 正向 |
| `test_get_all_config` | 获取全部配置 | 正向 |

### 4.3 仪表盘测试 (`tests/platform/test_dashboard.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_get_summary` | 获取仪表盘摘要 | 正向 |
| `test_get_quality_trend` | 获取质量趋势 | 正向 |

### 4.4 工作流测试 (`tests/platform/test_workflow.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_define_workflow` | 定义工作流 | 正向 |
| `test_execute_workflow` | 执行工作流 | 正向 |
| `test_workflow_with_dependencies` | 带依赖的工作流 | 依赖 |

---

## 五、安全测试用例

### 5.1 认证测试 (`tests/security/test_auth.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_password_hash` | 密码哈希 | 正向 |
| `test_password_verify` | 密码验证 | 正向 |
| `test_token_creation` | Token创建 | 正向 |
| `test_token_validation` | Token验证 | 正向 |
| `test_token_expiration` | Token过期 | 边界 |

### 5.2 权限测试 (`tests/security/test_permissions.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_permission_check` | 权限检查 | 正向 |
| `test_insufficient_permission` | 权限不足 | 负向 |
| `test_role_based_permissions` | 基于角色的权限 | 依赖 |

### 5.3 密码哈希与密钥管理测试 (`tests/security/test_password_hash_and_key_management.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_bcrypt_hash` | bcrypt哈希 | 正向 |
| `test_pbkdf2_fallback` | PBKDF2降级方案 | 异常 |
| `test_secret_key_validation` | 密钥验证 | 边界 |

---

## 六、集成测试用例

### 6.1 API集成测试 (`tests/integration/test_api.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_api_full_lifecycle` | API完整生命周期 | 正向 |
| `test_api_error_handling` | API错误处理 | 异常 |

### 6.2 全生命周期测试 (`tests/integration/test_full_lifecycle.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_full_lifecycle` | 治理完整生命周期 | 正向 |

### 6.3 全系统E2E测试 (`tests/integration/test_full_system_e2e.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_full_system_e2e` | 全系统端到端测试 | 正向 |

### 6.4 真实业务场景测试 (`tests/integration/test_real_e2e_business.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_real_http_api_full_flow` | 真实HTTP API全流程 | 正向 |
| `test_real_http_api_with_auth` | 带认证的真实HTTP API | 正向 |
| `test_real_http_error_handling` | 真实HTTP错误处理 | 异常 |
| `test_workflow_full_lifecycle` | 工作流完整生命周期 | 正向 |
| `test_workflow_with_governance_task` | 包含治理任务的工作流 | 依赖 |
| `test_api_login_and_protected_endpoint` | 登录和受保护端点 | 正向 |
| `test_golden_dataset_baseline` | 黄金数据集基线验证 | 正向 |
| `test_golden_dataset_actual_verification` | 黄金数据集真实验证 | 正向 |
| `test_golden_dataset_full_validation` | 完整黄金数据集验证 | 正向 |

---

## 七、AI模块测试用例

### 7.1 AI模块测试 (`tests/ai/test_ai_modules.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_test_case_generator_from_spec` | 从规范生成测试用例 | 正向 |
| `test_test_case_generator_from_code` | 从代码生成测试用例 | 正向 |
| `test_test_case_generator_fallback` | 降级模式生成 | 异常 |
| `test_defect_analyzer_analyze_test_results` | 分析测试结果 | 正向 |
| `test_defect_analyzer_analyze_code` | 分析代码 | 正向 |
| `test_defect_analyzer_fallback` | 降级模式分析 | 异常 |

---

## 八、Worker测试用例

### 8.1 Worker任务测试 (`tests/worker/test_tasks.py`)

| 测试用例 | 覆盖场景 | 断言类型 |
|----------|----------|----------|
| `test_run_test_pipeline` | 运行测试管道任务 | 正向 |
| `test_task_error_handling` | 任务错误处理 | 异常 |
| `test_task_concurrency` | 任务并发执行 | 依赖 |

---

## 九、测试用例分布图表

### 9.1 按模块分布

```
测试用例数量分布:
┌──────────────────────────────────────────────────────────────────────┐
│ 治理测试          ████████████████████████████████████████████  304 │
│ 平台测试          ██████████████████████                       138 │
│ 安全测试          ███████████                                  65 │
│ 集成测试          █████████                                   56 │
│ AI模块测试        █████                                        27 │
│ 单元测试          ███                                         14 │
│ Worker测试        ███                                         13 │
│ 性能测试          █                                           4 │
└──────────────────────────────────────────────────────────────────────┘
```

### 9.2 按测试类型分布

```
测试类型分布:
┌──────────────────────────────────────────────────────────────────────┐
│ 正向测试          ██████████████████████████████                   350 │
│ 负向测试          █████████████████                              150 │
│ 边界测试          █████████                                        60 │
│ 异常测试          ██████                                           35 │
│ 依赖测试          ████                                              26 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 十、测试执行命令汇总

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行治理测试
python -m pytest tests/governance/ -v

# 运行平台测试
python -m pytest tests/platform/ -v

# 运行安全测试
python -m pytest tests/security/ -v

# 运行集成测试
python -m pytest tests/integration/ -v

# 运行AI模块测试
python -m pytest tests/ai/ -v

# 运行Worker测试
python -m pytest tests/worker/ -v

# 运行性能测试
python -m pytest tests/performance/ -v --timeout=120

# 生成覆盖率报告
python -m pytest tests/ --cov=src --cov-report=html

# 仅运行S级测试
python -m pytest tests/governance/test_s_level_core.py -v
```

---

## 十一、核心模块覆盖率

| 模块 | 覆盖率 | 说明 |
|------|--------|------|
| `src/governance/agent.py` | 98% | AI诊断核心 |
| `src/governance/approval.py` | 95% | 审批管理 |
| `src/governance/executor.py` | 92% | 执行器 |
| `src/governance/orchestrator.py` | 100% | 编排器 |
| `src/governance/tracker.py` | 98% | 追踪器 |
| `src/governance/transformer.py` | 96% | 代码转换器 |
| `src/platform/api.py` | 97% | API端点 |
| `src/platform/workflow.py` | 91% | 工作流引擎 |
| `src/security/auth.py` | 94% | 认证 |
| `src/security/permissions.py` | 96% | 权限控制 |

---

*文档结束*