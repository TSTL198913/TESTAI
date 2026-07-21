# TestAI系统业务场景梳理

> 文档版本：v1.0  
> 创建日期：2026-07-21  
> 项目名称：TestAI — AI驱动的自治测试与智能诊断平台

---

## 一、业务场景总览

TestAI平台覆盖五大核心业务域：

| 业务域 | 核心场景 | API端点数量 | 实现状态 |
|--------|----------|-------------|----------|
| **测试执行引擎** | HTTP/gRPC测试、测试用例生成、缺陷分析 | 1+ | ✅ 完整 |
| **AI治理闭环** | 诊断→修复→审批→收敛验证 | 4 | ✅ 完整 |
| **工作流自动化** | DAG任务编排、依赖管理、状态追踪 | 3 | ✅ 完整 |
| **平台管理** | 用户管理、团队协作、配置管理、监控告警 | 20+ | ✅ 完整 |
| **质量保障** | 变异测试、黄金数据集、基线验证 | - | ✅ 完整 |

---

## 二、测试执行引擎业务场景

### 2.1 HTTP测试场景

| 场景ID | 场景名称 | 描述 | 技术实现 | 测试覆盖 |
|--------|----------|------|----------|----------|
| TE-001 | 正常HTTP请求 | GET/POST/PUT/DELETE请求执行 | `HTTPProcessor` | ✅ |
| TE-002 | 带认证的HTTP请求 | Bearer Token认证 | `HTTPProcessor` + Header处理 | ✅ |
| TE-003 | 带查询参数的请求 | URL参数传递与解析 | `DataProcessor` | ✅ |
| TE-004 | JSON请求体 | 复杂JSON数据提交 | `DataProcessor` | ✅ |
| TE-005 | 自定义请求头 | 业务Header注入 | `HTTPProcessor` | ✅ |
| TE-006 | 响应断言验证 | 状态码、Body、Header断言 | `AssertionProcessor` | ✅ |
| TE-007 | 错误响应处理 | 4xx/5xx错误处理 | `HTTPProcessor`异常捕获 | ✅ |
| TE-008 | 延迟响应测试 | 响应时间验证 | `HTTPProcessor`超时控制 | ✅ |

### 2.2 AI测试用例生成场景

| 场景ID | 场景名称 | 描述 | 技术实现 | 测试覆盖 |
|--------|----------|------|----------|----------|
| TC-001 | 从需求规范生成用例 | 根据API规范自动生成测试用例 | `TestCaseGenerator.generate_from_spec()` | ✅ |
| TC-002 | 从代码分析生成用例 | 解析Python函数签名生成单元测试 | `TestCaseGenerator.generate_from_code()` | ✅ |
| TC-003 | 正向测试用例 | 正常参数、成功路径 | `_generate_api_test_cases()` | ✅ |
| TC-004 | 负向测试用例 | 无效参数、边界条件 | `_generate_api_test_cases()` | ✅ |
| TC-005 | 边界条件测试 | 参数缺失、类型错误 | `_generate_api_test_cases()` | ✅ |
| TC-006 | LLM降级模式 | API不可用时使用fallback | `_generate_fallback()` | ✅ |

### 2.3 缺陷分析场景

| 场景ID | 场景名称 | 描述 | 技术实现 | 测试覆盖 |
|--------|----------|------|----------|----------|
| DA-001 | 测试结果缺陷分析 | 分析失败测试识别缺陷类型 | `DefectAnalyzer.analyze_test_results()` | ✅ |
| DA-002 | 代码静态分析 | 扫描代码中的安全漏洞 | `DefectAnalyzer.analyze_code()` | ✅ |
| DA-003 | 硬编码密码检测 | 检测源代码中的密码泄露 | `_analyze_code_fallback()`正则匹配 | ✅ |
| DA-004 | 静默异常处理检测 | 检测空except块 | `_analyze_code_fallback()`正则匹配 | ✅ |
| DA-005 | 调试打印检测 | 检测生产代码中的print语句 | `_analyze_code_fallback()`正则匹配 | ✅ |
| DA-006 | None值比较检测 | 检测`== None`错误用法 | `_analyze_code_fallback()`正则匹配 | ✅ |

---

## 三、AI治理闭环业务场景

### 3.1 诊断场景

| 场景ID | 场景名称 | 描述 | 技术实现 | 测试覆盖 |
|--------|----------|------|----------|----------|
| DG-001 | AI深度诊断 | LLM分析错误上下文生成修复建议 | `AIGovernanceAgent.analyze_with_context()` | ✅ |
| DG-002 | JSON Schema约束 | 强制AI输出符合规范的JSON | Pydantic `model_validate_json()` | ✅ |
| DG-003 | 响应格式清理 | 自动清理Markdown代码块包装 | `_sanitize_response()` | ✅ |
| DG-004 | 重试机制 | 失败时自动重试 | 配置化max_retries=2 | ✅ |
| DG-005 | Mock诊断模式 | 测试环境使用模拟响应 | `sdk.get_mock_response()` | ✅ |

### 3.2 修复场景

| 场景ID | 场景名称 | 描述 | 技术实现 | 测试覆盖 |
|--------|----------|------|----------|----------|
| FX-001 | 函数级补丁应用 | 精确替换函数体 | `FunctionTransformer` + libcst | ✅ |
| FX-002 | 类方法级补丁 | 精确替换类中的指定方法 | `ContextAwareTransformer` | ✅ |
| FX-003 | 安全代码校验 | 检测危险函数调用(eval/exec) | `SecurityVisitor` | ✅ |
| FX-004 | 路径安全校验 | 防止路径遍历攻击 | `SecurePathValidator` | ✅ |
| FX-005 | 备份与回滚 | 补丁失败时自动恢复 | `shutil.copy2`备份 | ✅ |
| FX-006 | 语法验证 | 补丁后验证代码语法 | `cst.parse_module`二次校验 | ✅ |
| FX-007 | 权限检测与修复 | 自动处理文件写权限 | `_has_write_permission()` + chmod | ✅ |

### 3.3 审批场景

| 场景ID | 场景名称 | 描述 | 技术实现 | 测试覆盖 |
|--------|----------|------|----------|----------|
| AP-001 | 审批创建 | 创建补丁审批记录 | `ApprovalManager.create_approval()` | ✅ |
| AP-002 | 自动审批判断 | 根据补丁类型决定是否需要审批 | `requires_approval`属性 | ✅ |
| AP-003 | 人工审批 | 管理员审批补丁 | `ApprovalManager.approve()` | ✅ |
| AP-004 | 审批拒绝 | 管理员拒绝补丁 | `ApprovalManager.reject()` | ✅ |
| AP-005 | 审批过期 | 30分钟自动过期 | `is_expired`属性 | ✅ |
| AP-006 | 审批记录持久化 | SQLite存储审批历史 | `_save_to_db()` | ✅ |

### 3.4 收敛验证场景

| 场景ID | 场景名称 | 描述 | 技术实现 | 测试覆盖 |
|--------|----------|------|----------|----------|
| CV-001 | 基线验证 | 验证实际输出与基线的一致性 | `GoldenBaselineManager.validate_against_baseline()` | ✅ |
| CV-002 | 收敛分数计算 | 量化验证结果 | `calculate_convergence_score()` | ✅ |
| CV-003 | 变异测试 | 验证测试用例的有效性 | `CustomMutationTester` | ✅ |

---

## 四、工作流自动化业务场景

### 4.1 工作流定义场景

| 场景ID | 场景名称 | 描述 | 技术实现 | 测试覆盖 |
|--------|----------|------|----------|----------|
| WF-001 | 工作流定义 | 创建包含多个任务的工作流 | `WorkflowEngine.define_workflow()` | ✅ |
| WF-002 | 任务依赖管理 | 定义任务之间的执行顺序 | `WorkflowTask.depends_on` | ✅ |
| WF-003 | 拓扑排序执行 | 基于DAG的任务调度 | `_calculate_execution_order()` | ✅ |

### 4.2 工作流执行场景

| 场景ID | 场景名称 | 描述 | 技术实现 | 测试覆盖 |
|--------|----------|------|----------|----------|
| WF-004 | 工作流执行 | 按顺序执行所有任务 | `WorkflowEngine.execute_workflow()` | ✅ |
| WF-005 | 任务结果传递 | 将前序任务结果传递给后续任务 | `prev_results`参数 | ✅ |
| WF-006 | 执行状态追踪 | 记录每个任务的执行状态 | `WorkflowInstance.tasks` | ✅ |
| WF-007 | 执行失败处理 | 捕获并记录执行错误 | try-except + error字段 | ✅ |

### 4.3 任务类型场景

| 任务类型 | 场景描述 | 处理函数 |
|----------|----------|----------|
| GOVERNANCE | AI治理分析任务 | `_handle_governance_task()` |
| MUTATION_TEST | 变异测试任务 | `_handle_mutation_test_task()` |
| APPROVAL | 审批任务 | `_handle_approval_task()` |
| MONITORING | 监控任务 | `_handle_monitoring_task()` |
| DELAY | 延时任务 | `_handle_delay_task()` |
| CONDITIONAL | 条件分支任务 | 预留 |

---

## 五、平台管理业务场景

### 5.1 认证与授权场景

| 场景ID | 场景名称 | 描述 | API端点 | 测试覆盖 |
|--------|----------|------|----------|----------|
| AU-001 | 用户登录 | 用户名密码认证获取Token | `POST /auth/login` | ✅ |
| AU-002 | Token刷新 | 使用Refresh Token获取新的Access Token | `POST /auth/refresh` | ✅ |
| AU-003 | 获取当前用户 | 获取登录用户信息 | `GET /auth/me` | ✅ |
| AU-004 | 权限校验 | 基于角色的权限控制 | `require_permission()`依赖 | ✅ |

### 5.2 用户管理场景

| 场景ID | 场景名称 | 描述 | API端点 | 测试覆盖 |
|--------|----------|------|----------|----------|
| UM-001 | 创建用户 | 创建新用户账户 | `POST /users` | ✅ |
| UM-002 | 查询用户列表 | 按角色/状态/部门筛选 | `GET /users` | ✅ |
| UM-003 | 查询单个用户 | 获取用户详细信息 | `GET /users/{user_id}` | ✅ |
| UM-004 | 更新用户 | 修改用户信息 | `PUT /users/{user_id}` | ✅ |
| UM-005 | 删除用户 | 删除用户账户 | `DELETE /users/{user_id}` | ✅ |
| UM-006 | 激活用户 | 激活被禁用的用户 | `POST /users/{user_id}/activate` | ✅ |
| UM-007 | 暂停用户 | 暂停用户账户 | `POST /users/{user_id}/suspend` | ✅ |
| UM-008 | 用户统计 | 获取用户数量统计 | `GET /users/stats` | ✅ |

### 5.3 团队管理场景

| 场景ID | 场景名称 | 描述 | API端点 | 测试覆盖 |
|--------|----------|------|----------|----------|
| TM-001 | 创建团队 | 创建新团队 | `POST /teams` | ✅ |
| TM-002 | 查询团队列表 | 获取所有团队 | `GET /teams` | ✅ |
| TM-003 | 查询单个团队 | 获取团队详细信息 | `GET /teams/{team_id}` | ✅ |
| TM-004 | 更新团队 | 修改团队信息 | `PUT /teams/{team_id}` | ✅ |
| TM-005 | 删除团队 | 删除团队 | `DELETE /teams/{team_id}` | ✅ |
| TM-006 | 添加团队成员 | 邀请用户加入团队 | `POST /teams/{team_id}/members` | ✅ |
| TM-007 | 移除团队成员 | 移除团队成员 | `DELETE /teams/{team_id}/members/{user_id}` | ✅ |
| TM-008 | 查询团队成员 | 获取团队成员列表 | `GET /teams/{team_id}/members` | ✅ |
| TM-009 | 团队统计 | 获取团队数量统计 | `GET /teams/stats` | ✅ |

### 5.4 配置管理场景

| 场景ID | 场景名称 | 描述 | API端点 | 测试覆盖 |
|--------|----------|------|----------|----------|
| CM-001 | 获取配置 | 获取指定section的配置 | `GET /config` | ✅ |
| CM-002 | 更新配置 | 更新指定section的配置 | `PUT /config/{section}` | ✅ |

### 5.5 监控与告警场景

| 场景ID | 场景名称 | 描述 | API端点 | 测试覆盖 |
|--------|----------|------|----------|----------|
| MO-001 | 健康检查 | 获取系统健康状态 | `GET /health` | ✅ |
| MO-002 | 获取告警列表 | 按级别筛选告警 | `GET /monitoring/alerts` | ✅ |
| MO-003 | 确认告警 | 标记告警为已处理 | `POST /monitoring/alerts/{alert_id}/acknowledge` | ✅ |
| MO-004 | 获取指标 | 获取治理指标 | `GET /monitoring/metrics` | ✅ |

### 5.6 仪表盘场景

| 场景ID | 场景名称 | 描述 | API端点 | 测试覆盖 |
|--------|----------|------|----------|----------|
| DB-001 | 获取仪表盘摘要 | 获取平台概览数据 | `GET /dashboard/summary` | ✅ |
| DB-002 | 获取质量趋势 | 获取指定天数的质量趋势 | `GET /dashboard/quality-trend` | ✅ |

---

## 六、质量保障业务场景

### 6.1 变异测试场景

| 场景ID | 场景名称 | 描述 | 技术实现 |
|--------|----------|------|----------|
| MT-001 | True/False交换 | 替换return True/False | `_generate_mutations()` |
| MT-002 | ==/!=交换 | 替换相等性判断 | `_generate_mutations()` |
| MT-003 | and/or交换 | 替换逻辑运算符 | `_generate_mutations()` |
| MT-004 | if条件置假 | 将if条件置为False | `_generate_mutations()` |
| MT-005 | not取反移除 | 移除not关键字 | `_generate_mutations()` |
| MT-006 | 临时目录隔离 | 在临时目录中执行变异测试 | `tempfile.TemporaryDirectory()` |
| MT-007 | 智能测试匹配 | 根据变异文件自动选择测试 | `_build_pytest_args()` |

### 6.2 黄金数据集场景

| 场景ID | 场景名称 | 描述 | 数据规模 |
|--------|----------|------|----------|
| GD-001 | API基线验证 | 20个真实API测试基线 | 20个 |
| GD-002 | 已知缺陷用例 | 4个经典缺陷场景 | 4个 |
| GD-003 | 除零错误 | 缺少除数非零检查 | high |
| GD-004 | 无限循环 | 缺少终止条件 | critical |
| GD-005 | 递归性能 | 斐波那契指数级复杂度 | medium |
| GD-006 | 硬编码密钥 | 安全风险 | critical |

---

## 七、业务场景优先级矩阵

### 7.1 核心场景（P0 - 必须实现）

| 场景 | 说明 |
|------|------|
| TE-001 | 基础HTTP测试能力 |
| DG-001 | AI诊断核心能力 |
| FX-001 | 代码修复核心能力 |
| AP-001 | 审批流程核心能力 |
| AU-001 | 用户认证核心能力 |

### 7.2 重要场景（P1 - 应该实现）

| 场景 | 说明 |
|------|------|
| TC-001 | AI测试用例生成 |
| DA-001 | 缺陷分析 |
| WF-001 | 工作流定义 |
| UM-001 | 用户管理 |
| MT-001 | 变异测试 |

### 7.3 一般场景（P2 - 可以实现）

| 场景 | 说明 |
|------|------|
| TM-001 | 团队管理 |
| MO-001 | 监控告警 |
| DB-001 | 仪表盘 |
| CM-001 | 配置管理 |

---

## 八、业务场景依赖关系

```
┌──────────────────────────────────────────────────────────────────┐
│                     用户认证 (AU-001)                           │
│                           │                                     │
│           ┌───────────────┼───────────────┐                     │
│           ▼               ▼               ▼                     │
│   用户管理(UM)      团队管理(TM)      配置管理(CM)               │
│           │               │               │                     │
│           └───────────────┼───────────────┘                     │
│                           ▼                                     │
│                   工作流引擎 (WF)                                │
│                           │                                     │
│           ┌───────────────┼───────────────┐                     │
│           ▼               ▼               ▼                     │
│   测试执行(TE)      AI治理(DG/FX)    监控告警(MO)               │
│           │               │               │                     │
│           └───────────────┼───────────────┘                     │
│                           ▼                                     │
│                   质量保障 (MT/GD)                               │
└──────────────────────────────────────────────────────────────────┘
```

---

*文档结束*