# TestAI 系统业务功能文档

> 文档版本：v1.0  
> 创建日期：2026-07-23  
> 项目名称：TestAI — AI驱动的自治测试与智能诊断平台

---

## 一、系统概述

### 1.1 系统定位

TestAI 是一个基于 AI 驱动的自治测试与智能诊断平台，旨在实现测试执行、缺陷分析、AI 治理闭环、工作流自动化和平台管理的一体化解决方案。

### 1.2 核心价值

| 价值维度 | 描述 |
|----------|------|
| **AI 智能诊断** | 利用 LLM 技术自动分析测试失败原因并生成修复建议 |
| **代码自动修复** | 基于 AST 转换实现精确的代码补丁应用 |
| **审批流程闭环** | 安全可控的人工审批机制，支持安全/重构类补丁强制审批 |
| **测试用例生成** | AI 自动生成正向、负向、边界条件测试用例 |
| **质量收敛验证** | 黄金基线验证 + 变异测试确保修复质量 |

### 1.3 技术架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        前端层 (Next.js)                             │
│  ┌─────────┬──────────┬──────────┬──────────┬──────────┐           │
│  │登录页   │仪表盘    │治理流程  │工作流    │监控告警  │用户管理  │...│
│  └────┬────┴────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬────┘           │
└───────┼─────────┼──────────┼──────────┼──────────┼──────────┼──────────────────┘
        │         │          │          │          │          │
┌───────▼─────────▼──────────▼──────────▼──────────▼──────────▼──────────────────┐
│                        API 网关层 (FastAPI)                          │
│  Auth │ Users │ Teams │ Governance │ Workflow │ Monitoring │ Dashboard │ Config │
└───────┬───────────────────────────────────────────────────────────────────────┘
        │
┌───────▼───────────────────────────────────────────────────────────────────────┐
│                        业务逻辑层                                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │认证授权    │  │用户管理    │  │团队管理    │  │工作流引擎  │            │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘            │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │AI治理闭环  │  │AI测试引擎  │  │监控告警    │  │配置管理    │            │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘            │
└───────┬───────────────────────────────────────────────────────────────────────┘
        │
┌───────▼───────────────────────────────────────────────────────────────────────┐
│                        数据存储层                                       │
│  SQLite (治理审批/用户/团队) | JSON (用户配置) | Memory (运行时状态)          │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、认证与授权

### 2.1 用户角色

| 角色 | 描述 | 权限范围 |
|------|------|----------|
| **admin** | 系统管理员 | 全部权限 |
| **tester** | 测试工程师 | 执行测试、查看数据、定义工作流 |
| **viewer** | 查看用户 | 只读权限 |
| **guest** | 访客 | 仅查看健康状态和仪表盘 |

### 2.2 权限矩阵

| 权限 | Admin | Tester | Viewer | Guest |
|------|-------|--------|--------|-------|
| view_health | ✅ | ✅ | ✅ | ✅ |
| view_config | ✅ | ✅ | ✅ | ❌ |
| edit_config | ✅ | ❌ | ❌ | ❌ |
| execute_governance | ✅ | ✅ | ❌ | ❌ |
| view_governance | ✅ | ✅ | ✅ | ❌ |
| view_approvals | ✅ | ✅ | ✅ | ❌ |
| approve_patch | ✅ | ❌ | ❌ | ❌ |
| reject_patch | ✅ | ❌ | ❌ | ❌ |
| view_alerts | ✅ | ✅ | ✅ | ❌ |
| acknowledge_alert | ✅ | ✅ | ❌ | ❌ |
| view_metrics | ✅ | ✅ | ✅ | ❌ |
| view_dashboard | ✅ | ✅ | ✅ | ✅ |
| define_workflow | ✅ | ✅ | ❌ | ❌ |
| execute_workflow | ✅ | ✅ | ❌ | ❌ |
| view_workflow | ✅ | ✅ | ✅ | ❌ |
| manage_users | ✅ | ❌ | ❌ | ❌ |
| view_users | ✅ | ✅ | ✅ | ❌ |
| manage_teams | ✅ | ❌ | ❌ | ❌ |
| view_teams | ✅ | ✅ | ✅ | ❌ |

### 2.3 认证流程

```
用户登录 → 验证用户名密码 → 返回 JWT Token → 请求携带 Token → 验证 Token → 授权访问
```

### 2.4 API 接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/auth/login` | POST | 用户登录 |
| `/auth/refresh` | POST | 刷新 Access Token |
| `/auth/me` | GET | 获取当前用户信息 |

---

## 三、用户管理

### 3.1 功能概述

完整的用户生命周期管理，包括创建、查询、更新、删除、激活、暂停等操作。

### 3.2 用户数据模型

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | string | 用户唯一标识 |
| username | string | 用户名 |
| email | string | 邮箱 |
| role | enum | admin/tester/viewer/guest |
| status | enum | active/inactive/suspended |
| full_name | string | 全名 |
| department | string | 部门 |
| created_at | datetime | 创建时间 |
| last_login_at | datetime | 最后登录时间 |

### 3.3 API 接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/users` | GET | 查询用户列表（支持角色/状态/部门筛选） |
| `/users` | POST | 创建用户 |
| `/users/{user_id}` | GET | 查询单个用户 |
| `/users/{user_id}` | PUT | 更新用户 |
| `/users/{user_id}` | DELETE | 删除用户 |
| `/users/{user_id}/activate` | POST | 激活用户 |
| `/users/{user_id}/suspend` | POST | 暂停用户 |
| `/users/stats` | GET | 用户统计 |

---

## 四、团队管理

### 4.1 功能概述

支持团队创建、成员管理、团队统计等协作功能。

### 4.2 团队数据模型

| 字段 | 类型 | 说明 |
|------|------|------|
| team_id | string | 团队唯一标识 |
| name | string | 团队名称 |
| description | string | 团队描述 |
| members | array | 成员列表 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### 4.3 API 接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/teams` | GET | 查询团队列表 |
| `/teams` | POST | 创建团队 |
| `/teams/{team_id}` | GET | 查询单个团队 |
| `/teams/{team_id}` | PUT | 更新团队 |
| `/teams/{team_id}` | DELETE | 删除团队 |
| `/teams/{team_id}/members` | POST | 添加团队成员 |
| `/teams/{team_id}/members/{user_id}` | DELETE | 移除团队成员 |
| `/teams/{team_id}/members` | GET | 查询团队成员 |
| `/teams/stats` | GET | 团队统计 |

---

## 五、AI 治理闭环

### 5.1 业务流程

```
诊断开始 → AI分析错误上下文 → 生成修复建议 → 判断是否需要审批
    ↓                              ↓
不需要审批                    需要审批
    ↓                              ↓
直接应用补丁              创建审批记录
    ↓                              ↓
验证修复效果              等待人工审批
    ↓                              ↓
完成/失败              审批通过 → 应用补丁 → 验证
                        ↓
                    审批拒绝 → 流程结束
```

### 5.2 核心组件

| 组件 | 职责 | 关键方法 |
|------|------|----------|
| AIGovernanceAgent | AI 诊断分析 | `analyze_with_context()` |
| GovernanceExecutor | 补丁应用执行 | `apply_patch()` |
| ApprovalManager | 审批流程管理 | `create_approval()`, `approve()`, `reject()` |
| FunctionTransformer | 函数级代码转换 | `transform()` |
| GoldenBaselineManager | 基线收敛验证 | `validate_against_baseline()` |
| GovernanceTracker | 全流程追踪 | `record_event()`, `get_summary()` |

### 5.3 API 接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/governance/execute` | POST | 执行治理流程 |
| `/governance/approvals` | GET | 查询审批列表 |
| `/governance/approvals/{tx_id}/approve` | POST | 审批通过 |
| `/governance/approvals/{tx_id}/reject` | POST | 审批拒绝 |
| `/governance/tracker/events` | GET | 查询追踪事件 |
| `/governance/tracker/summary` | GET | 获取追踪摘要 |
| `/governance/baselines` | GET | 查询基线列表 |
| `/governance/baselines/{baseline_id}` | GET | 查询单个基线 |
| `/governance/baselines/{baseline_id}/validate` | POST | 验证基线 |

---

## 六、测试执行引擎

### 6.1 功能概述

支持 HTTP/gRPC 测试、测试用例执行、响应断言验证的自动化测试执行引擎。

### 6.2 核心组件

| 组件 | 职责 | 文件位置 |
|------|------|----------|
| ExecutionPipeline | 测试执行管道，编排多个处理器 | `src/engine/pipeline.py` |
| StepFactory | 测试步骤工厂，创建不同类型的测试步骤 | `src/engine/factory.py` |
| HTTPProcessor | HTTP请求处理器，支持重试机制 | `src/engine/processor/http.py` |
| gRPCProcessor | gRPC请求处理器 | `src/engine/processor/grpc.py` |
| DataProcessor | 数据处理和参数解析 | `src/engine/processor/data.py` |
| AssertionProcessor | 响应断言验证 | `src/engine/processor/assertion.py` |
| Dispatcher | 请求分发器 | `src/engine/processor/dispatcher.py` |
| EnvironmentProcessor | 环境变量处理器 | `src/engine/processor/env.py` |
| GovernanceProcessor | 治理处理器，集成AI治理 | `src/engine/processor/governance_processor.py` |

### 6.3 处理器执行流程

```
原始步骤 → StepFactory创建 → HTTPProcessor执行请求 → DataProcessor处理数据
    ↓                                                          ↓
gRPCProcessor执行请求                                  AssertionProcessor验证
    ↓                                                          ↓
EnvironmentProcessor设置环境                          GovernanceProcessor治理分析
    ↓                                                          ↓
Dispatcher分发请求                                    收集结果 → 返回执行结果
```

### 6.4 测试步骤类型

| 类型 | 描述 | 处理组件 |
|------|------|----------|
| HTTP | HTTP请求测试 | HTTPProcessor |
| gRPC | gRPC请求测试 | gRPCProcessor |
| ASSERTION | 响应断言验证 | AssertionProcessor |
| DATA | 数据处理 | DataProcessor |
| ENV | 环境变量设置 | EnvironmentProcessor |
| GOVERNANCE | AI治理分析 | GovernanceProcessor |

### 6.5 执行特性

| 特性 | 说明 |
|------|------|
| 重试机制 | HTTP请求支持最多3次重试，指数退避等待 |
| 异常处理 | InfrastructureError自动重试，EngineError直接失败 |
| 上下文传递 | 执行上下文在处理器之间传递，支持结果共享 |
| 错误收集 | 收集所有步骤异常，最后抛出第一个异常 |

---

## 七、AI 能力模块

### 7.1 功能概述

基于 LLM 的智能测试用例生成和缺陷分析能力，支持正向、负向、边界条件测试用例自动生成，以及测试结果和代码的缺陷分析。

### 7.2 核心组件

#### 7.2.1 测试用例生成器

**类**: `TestCaseGenerator` (`src/ai/test_case_generator.py`)

**功能**:
- 根据 API 规范生成测试用例
- 根据代码分析生成单元测试用例
- 根据 UI 页面规范生成 UI 测试用例

**测试用例类型**:

| 类型 | 描述 |
|------|------|
| unit | 单元测试 |
| integration | 集成测试 |
| api | API测试 |
| ui | UI测试 |
| e2e | 端到端测试 |

**生成策略**:

| 策略 | 描述 |
|------|------|
| 正向测试 | 正常参数、成功路径 |
| 负向测试 | 无效参数、错误场景 |
| 边界条件 | 参数缺失、类型错误、边界值 |
| 异常场景 | 网络错误、超时、权限错误 |

**降级模式**:
- 当 LLM API 不可用时，自动切换到基于规则的 fallback 模式
- 使用正则表达式分析代码结构生成测试用例

#### 7.2.2 缺陷分析器

**类**: `DefectAnalyzer` (`src/ai/defect_analyzer.py`)

**功能**:
- 分析测试结果识别缺陷类型
- 静态分析代码中的安全漏洞

**缺陷严重程度**:

| 级别 | 描述 |
|------|------|
| CRITICAL | 严重，可能导致系统崩溃或数据丢失 |
| HIGH | 高，影响核心功能或存在安全风险 |
| MEDIUM | 中，影响部分功能或用户体验 |
| LOW | 低，代码质量或可维护性问题 |

**缺陷类型**:

| 类型 | 描述 |
|------|------|
| logic_error | 逻辑错误 |
| performance | 性能问题 |
| security | 安全漏洞 |
| compatibility | 兼容性问题 |
| usability | 可用性问题 |
| data_integrity | 数据完整性问题 |

**静态分析规则**:

| 规则 | 检测内容 | 严重程度 |
|------|----------|----------|
| 硬编码密码检测 | `password = "xxx"` | CRITICAL |
| 静默异常处理 | `except: pass` | MEDIUM |
| 调试打印检测 | `print()`在生产代码中 | LOW |
| None值比较检测 | `== None`而非`is None` | LOW |

#### 7.2.3 结果分析器

**类**: `ResultAnalyzer` (`src/ai/result_analyzer.py`)

**功能**:
- 分析测试执行结果
- 生成测试报告摘要
- 识别测试覆盖率问题

### 7.3 AI 能力工作流程

```
输入（规范/代码/测试结果）
    ↓
判断是否有LLM API Key
    ↓           ↓
有API Key    无API Key
    ↓           ↓
调用GPT-4o   降级模式（规则匹配）
    ↓           ↓
生成测试用例/分析缺陷
    ↓
返回结果（成功/失败+错误信息）
```

### 7.4 API 集成

AI 能力模块通过工作流引擎集成到系统中：
- 工作流任务类型 `GOVERNANCE` 调用治理流程
- 工作流任务类型 `MUTATION_TEST` 调用变异测试
- 治理流程内部调用 `AIGovernanceAgent` 进行 AI 诊断

---

## 八、工作流引擎

### 8.1 功能概述

支持 DAG 任务编排、依赖管理、状态追踪的工作流自动化引擎。

### 8.2 任务类型

| 任务类型 | 描述 | 处理逻辑 |
|----------|------|----------|
| GOVERNANCE | AI 治理分析任务 | 调用 GovernanceOrchestrator |
| MUTATION_TEST | 变异测试任务 | 调用 CustomMutationTester |
| APPROVAL | 审批任务 | 调用 ApprovalManager |
| MONITORING | 监控任务 | 调用 HealthMonitor/AlertManager |
| DELAY | 延时任务 | asyncio.sleep() |
| CONDITIONAL | 条件分支任务 | 预留 |

### 8.3 工作流状态

| 状态 | 描述 |
|------|------|
| DEFINED | 已定义 |
| RUNNING | 运行中 |
| COMPLETED | 已完成 |
| FAILED | 失败 |
| PAUSED | 已暂停 |

### 8.4 API 接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/workflow` | GET | 查询工作流列表 |
| `/workflow/define` | POST | 定义工作流 |
| `/workflow/{workflow_id}/execute` | POST | 执行工作流 |
| `/workflow/{workflow_id}/status` | GET | 查询工作流状态 |

### 8.5 核心组件

| 组件 | 职责 | 文件位置 |
|------|------|----------|
| WorkflowEngine | 工作流引擎核心 | `src/platform/workflow.py` |
| WorkflowRegistry | 工作流定义注册中心 | `src/platform/workflow.py` |
| TaskExecutor | 任务执行器 | `src/platform/workflow.py` |
| ExecutionStateManager | 执行状态管理 | `src/platform/workflow.py` |

### 8.6 执行流程

```
工作流定义 → 注册到 WorkflowRegistry → 触发执行
    ↓
WorkflowEngine 解析任务依赖 → TaskExecutor 按顺序执行
    ↓
ExecutionStateManager 更新状态 → 完成/失败
```

### 8.7 工作流定义结构

| 字段 | 类型 | 说明 |
|------|------|------|
| workflow_id | string | 工作流唯一标识 |
| name | string | 工作流名称 |
| description | string | 工作流描述 |
| tasks | array | 任务列表 |
| dependencies | array | 任务依赖关系 |
| created_at | datetime | 创建时间 |

### 8.8 任务定义结构

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | string | 任务唯一标识 |
| type | enum | 任务类型 |
| config | dict | 任务配置 |
| retry_policy | dict | 重试策略 |
| timeout | int | 超时时间（秒） |

---

## 九、监控与告警

### 9.1 功能概述

系统健康监控、告警管理、指标收集。

### 9.2 告警级别

| 级别 | 描述 |
|------|------|
| CRITICAL | 严重告警 |
| ERROR | 错误告警 |
| WARNING | 警告 |
| INFO | 信息 |

### 9.3 API 接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/monitoring/alerts` | GET | 查询告警列表 |
| `/monitoring/alerts/{alert_id}/acknowledge` | POST | 确认告警 |
| `/monitoring/metrics` | GET | 获取指标 |

### 9.4 核心组件

| 组件 | 职责 | 文件位置 |
|------|------|----------|
| HealthMonitor | 健康监控器 | `src/platform/monitoring.py` |
| AlertManager | 告警管理器 | `src/platform/monitoring.py` |
| MetricsCollector | 指标收集器 | `src/platform/monitoring.py` |
| AlertRuleEngine | 告警规则引擎 | `src/platform/monitoring.py` |

### 9.5 告警数据模型

| 字段 | 类型 | 说明 |
|------|------|------|
| alert_id | string | 告警唯一标识 |
| level | enum | CRITICAL/ERROR/WARNING/INFO |
| category | string | 告警类别 |
| message | string | 告警消息 |
| source | string | 告警来源 |
| timestamp | datetime | 告警时间 |
| acknowledged | bool | 是否已确认 |
| acknowledged_by | string | 确认人 |
| acknowledged_at | datetime | 确认时间 |

### 9.6 指标类型

| 指标 | 描述 |
|------|------|
| cpu_usage | CPU使用率 |
| memory_usage | 内存使用率 |
| request_count | 请求总数 |
| request_errors | 错误请求数 |
| workflow_executions | 工作流执行次数 |
| governance_success_rate | 治理成功率 |
| baseline_convergence_score | 基线收敛分数 |

### 9.7 告警规则

| 规则 | 条件 | 级别 |
|------|------|------|
| CPU高负载 | CPU使用率 > 90% 持续5分钟 | WARNING |
| CPU严重负载 | CPU使用率 > 95% 持续3分钟 | CRITICAL |
| 内存高占用 | 内存使用率 > 85% | WARNING |
| 内存严重占用 | 内存使用率 > 95% | CRITICAL |
| 服务健康异常 | 健康检查失败 | CRITICAL |
| 治理流程失败 | 治理执行失败 | ERROR |
| 工作流执行失败 | 工作流执行失败 | ERROR |

---

## 十、仪表盘

### 10.1 功能概述

平台数据概览、质量趋势分析。

### 10.2 数据维度

| 维度 | 描述 |
|------|------|
| 平台状态 | 系统运行状态、版本信息 |
| 健康指标 | 诊断成功率、补丁成功率 |
| 质量指标 | 测试用例数、通过率、杀变异率 |
| 待办事项 | 待审批数、未确认告警数 |

### 10.3 API 接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/dashboard/summary` | GET | 获取仪表盘摘要 |
| `/dashboard/quality-trend` | GET | 获取质量趋势 |

---

## 十一、配置管理

### 11.1 功能概述

系统配置的读取和更新。

### 11.2 配置模块

| 模块 | 描述 |
|------|------|
| platform | 平台基础配置 |
| api | API 相关配置 |
| workflow | 工作流配置 |
| governance | 治理配置 |
| mutation_test | 变异测试配置 |
| monitoring | 监控配置 |

### 11.3 API 接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/config` | GET | 获取配置 |
| `/config/{section}` | PUT | 更新配置 |

---

## 十二、前端页面功能对照表

### 12.1 页面清单

| 页面路径 | 页面名称 | 功能描述 |
|----------|----------|----------|
| `/login` | 登录页 | 用户认证登录 |
| `/` | 仪表盘 | 平台数据概览 |
| `/governance` | 治理流程 | 审批列表、执行治理 |
| `/workflow` | 工作流 | 工作流列表、执行 |
| `/monitoring` | 监控告警 | 告警列表、系统指标 |
| `/users` | 用户管理 | 用户CRUD、状态管理 |
| `/teams` | 团队管理 | 团队CRUD、成员管理 |
| `/config` | 系统配置 | 配置查看、编辑 |

### 12.2 页面功能详解

#### 登录页 (`/login`)
- 用户名/密码输入
- 登录按钮
- 错误提示

#### 仪表盘 (`/`)
- 平台状态卡片
- 版本信息
- 测试用例统计
- 通过率展示
- 最近告警列表
- 待审批任务数
- 运行中工作流数

#### 治理流程 (`/governance`)
- 审批状态筛选（全部/待审批/已批准/已拒绝）
- 审批列表展示
- 查看详情按钮
- 审批通过/拒绝按钮
- 执行治理按钮

#### 工作流 (`/workflow`)
- 工作流列表展示
- 创建工作流按钮
- 执行工作流按钮
- 重试按钮

#### 监控告警 (`/monitoring`)
- 告警级别筛选（全部/严重/警告/信息）
- 系统指标展示（CPU、内存、请求数）
- 告警列表
- 确认告警按钮

#### 用户管理 (`/users`)
- 搜索功能（用户名/邮箱/部门）
- 用户列表展示
- 创建用户按钮
- 编辑/删除/激活/暂停操作

#### 团队管理 (`/teams`)
- 团队列表展示
- 创建团队按钮
- 成员管理按钮
- 编辑/删除操作

#### 系统配置 (`/config`)
- 配置模块列表
- 配置详情展示
- 编辑配置按钮

---

## 十三、API 完整清单

### 13.1 认证模块

| 接口 | 方法 | 权限 |
|------|------|------|
| `/auth/login` | POST | 公开 |
| `/auth/refresh` | POST | authenticated |
| `/auth/me` | GET | authenticated |

### 13.2 用户模块

| 接口 | 方法 | 权限 |
|------|------|------|
| `/users` | GET | VIEW_USERS |
| `/users` | POST | MANAGE_USERS |
| `/users/{user_id}` | GET | VIEW_USERS |
| `/users/{user_id}` | PUT | MANAGE_USERS |
| `/users/{user_id}` | DELETE | MANAGE_USERS |
| `/users/{user_id}/activate` | POST | MANAGE_USERS |
| `/users/{user_id}/suspend` | POST | MANAGE_USERS |
| `/users/stats` | GET | VIEW_USERS |

### 13.3 团队模块

| 接口 | 方法 | 权限 |
|------|------|------|
| `/teams` | GET | VIEW_TEAMS |
| `/teams` | POST | MANAGE_TEAMS |
| `/teams/{team_id}` | GET | VIEW_TEAMS |
| `/teams/{team_id}` | PUT | MANAGE_TEAMS |
| `/teams/{team_id}` | DELETE | MANAGE_TEAMS |
| `/teams/{team_id}/members` | POST | MANAGE_TEAMS |
| `/teams/{team_id}/members/{user_id}` | DELETE | MANAGE_TEAMS |
| `/teams/{team_id}/members` | GET | VIEW_TEAMS |
| `/teams/stats` | GET | VIEW_TEAMS |

### 13.4 治理模块

| 接口 | 方法 | 权限 |
|------|------|------|
| `/governance/execute` | POST | EXECUTE_GOVERNANCE |
| `/governance/approvals` | GET | VIEW_APPROVALS |
| `/governance/approvals/{tx_id}/approve` | POST | APPROVE_PATCH |
| `/governance/approvals/{tx_id}/reject` | POST | REJECT_PATCH |
| `/governance/tracker/events` | GET | VIEW_GOVERNANCE |
| `/governance/tracker/summary` | GET | VIEW_GOVERNANCE |
| `/governance/baselines` | GET | VIEW_GOVERNANCE |
| `/governance/baselines/{baseline_id}` | GET | VIEW_GOVERNANCE |
| `/governance/baselines/{baseline_id}/validate` | POST | EXECUTE_GOVERNANCE |

### 13.5 工作流模块

| 接口 | 方法 | 权限 |
|------|------|------|
| `/workflow` | GET | VIEW_WORKFLOW |
| `/workflow/define` | POST | DEFINE_WORKFLOW |
| `/workflow/{workflow_id}/execute` | POST | EXECUTE_WORKFLOW |
| `/workflow/{workflow_id}/status` | GET | VIEW_WORKFLOW |

### 13.6 监控模块

| 接口 | 方法 | 权限 |
|------|------|------|
| `/health` | GET | VIEW_HEALTH |
| `/monitoring/alerts` | GET | VIEW_ALERTS |
| `/monitoring/alerts/{alert_id}/acknowledge` | POST | ACKNOWLEDGE_ALERT |
| `/monitoring/metrics` | GET | VIEW_METRICS |

### 13.7 仪表盘模块

| 接口 | 方法 | 权限 |
|------|------|------|
| `/dashboard/summary` | GET | VIEW_DASHBOARD |
| `/dashboard/quality-trend` | GET | VIEW_DASHBOARD |

### 13.8 配置模块

| 接口 | 方法 | 权限 |
|------|------|------|
| `/config` | GET | VIEW_CONFIG |
| `/config/{section}` | PUT | EDIT_CONFIG |

---

## 十四、数据模型汇总

### 14.1 核心数据模型

| 模型 | 文件位置 | 用途 |
|------|----------|------|
| User | `src/security/auth.py` | 认证用户 |
| UserProfile | `src/users/user_manager.py` | 用户详细信息 |
| Team | `src/teams/team_manager.py` | 团队信息 |
| TeamMember | `src/teams/team_manager.py` | 团队成员 |
| ApprovalRecord | `src/governance/approval.py` | 审批记录 |
| PatchProposal | `src/governance/models.py` | 补丁提案 |
| DiagnosticContext | `src/governance/models.py` | 诊断上下文 |
| WorkflowDefinition | `src/platform/workflow.py` | 工作流定义 |
| WorkflowTask | `src/platform/workflow.py` | 工作流任务 |
| WorkflowInstance | `src/platform/workflow.py` | 工作流实例 |

---

## 十五、系统安全规范

### 15.1 安全原则

| 原则 | 描述 |
|------|------|
| 最小权限 | 每个角色仅授予完成工作所需的最小权限 |
| 审计追踪 | 所有关键操作必须记录审计日志 |
| 数据加密 | 敏感数据传输和存储必须加密 |
| 输入验证 | 所有外部输入必须进行严格验证 |
| 安全编码 | 遵循安全编码最佳实践，防止常见漏洞 |

### 15.2 认证安全

| 机制 | 说明 |
|------|------|
| JWT Token | 使用 HS256 算法签名，密钥长度 ≥ 32 字节 |
| Token 刷新 | Access Token 过期后使用 Refresh Token 刷新 |
| 密码策略 | 密码长度 ≥ 8 位，包含大小写字母和数字 |
| 登录尝试限制 | 5次失败登录后锁定账户15分钟 |

### 15.3 数据安全

| 措施 | 说明 |
|------|------|
| 敏感数据脱敏 | 日志输出中敏感字段（密码、Token）必须脱敏 |
| 配置文件加密 | 敏感配置项（API Key、密钥）使用环境变量 |
| 数据库加密 | SQLite 数据库文件权限限制为仅应用程序可读 |

### 15.4 传输安全

| 措施 | 说明 |
|------|------|
| HTTPS | 生产环境必须使用 HTTPS 协议 |
| CORS 配置 | 限制允许的来源、方法和头信息 |
| CSRF 防护 | 前端请求携带 CSRF Token |

### 15.5 安全审计

| 审计项 | 记录内容 |
|--------|----------|
| 用户登录 | 用户名、IP、时间、结果 |
| 用户操作 | 操作类型、目标对象、时间、操作者 |
| 权限变更 | 变更前后权限、操作者、时间 |
| 审批操作 | 审批类型、结果、操作者、时间 |
| 系统配置变更 | 配置项、变更值、操作者、时间 |

---

## 附录：技术栈与依赖

### A.1 后端技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 编程语言 |
| FastAPI | 0.100+ | Web 框架 |
| Uvicorn | 0.23+ | ASGI 服务器 |
| Pydantic | 2.0+ | 数据验证 |
| SQLAlchemy | 2.0+ | ORM |
| SQLite | 3.30+ | 数据库 |
| PyJWT | 2.8+ | JWT 认证 |
| httpx | 0.25+ | HTTP 客户端 |
| pytest | 9.0+ | 测试框架 |

### A.2 前端技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| Next.js | 14.2+ | React 框架 |
| React | 18.2+ | UI 框架 |
| TypeScript | 5.3+ | 类型系统 |
| Tailwind CSS | 3.4+ | 样式框架 |
| Lucide React | 0.310+ | 图标库 |
| Axios | 1.6+ | HTTP 客户端 |
| Zod | 3.22+ | 表单验证 |

### A.3 AI 能力依赖

| 组件 | 用途 |
|------|------|
| OpenAI SDK | LLM API 调用 |
| LangChain | 提示词工程 |
| AST Module | 代码抽象语法树解析 |

### A.4 CI/CD 工具

| 工具 | 用途 |
|------|------|
| GitHub Actions | 持续集成/部署 |
| Flake8 | 静态代码检查 |
| Pylint | 代码质量分析 |
| MyPy | 类型检查 |
| Bandit | 安全扫描 |
| Syft | SBOM 生成 |
| Cosign | 签名验证 |

---

*文档结束*