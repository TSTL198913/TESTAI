# 技术委员会迭代方案 - TestAI 平台产品落地

**方案编号**: TC-ITER-2026-001  
**制定日期**: 2026-07-20  
**技术委员会主席**: AI Assistant  
**审核状态**: 待审核

---

## 一、当前状态评估

### 1.1 项目概况

| 指标 | 当前状态 | 目标值 | 差距 |
|------|----------|--------|------|
| 项目版本 | v0.1.0 | v0.2.0 | 升级迭代 |
| 核心测试通过率 | 97.4% (39/40) | ≥98% | 0.6% |
| 代码覆盖率 | 78% | ≥85% | 7% |
| 变异测试Kill Rate | 未达标 | ≥70% | 待验证 |
| 安全漏洞修复率 | 100% (8/8) | 100% | ✅ |
| 并发安全修复率 | 100% (6/6) | 100% | ✅ |

### 1.2 关键技术债务

| 编号 | 问题描述 | 严重程度 | 影响范围 | 优先级 |
|------|----------|----------|----------|--------|
| TD-001 | `transformer.py` 第32/69行 `self.patched = True` 被注释 | 🔴 高危 | 变异测试Kill Rate | P0 |
| TD-002 | CI流水线 `tests/components/` 目录不存在 | 🟡 中危 | CI/CD失败 | P1 |
| TD-003 | API层仅 `/execute` 一个端点 | 🟡 中危 | 功能完整性 | P1 |
| TD-004 | 缺乏健康检查端点 | 🟢 低危 | 运维监控 | P2 |
| TD-005 | AI核心功能为Mock模式 | 🟡 中危 | 产品竞争力 | P1 |

### 1.3 架构合规检查

| 检查项 | 状态 | 说明 |
|--------|------|------|
| .trae-rules 遵守 | ✅ | src/ 目录为只读核心 |
| 治理处理器注册 | ✅ | 已注册到 registry.py |
| 线程安全单例 | ✅ | GoldenBaselineManager |
| 文件锁机制 | ✅ | portalocker 实现 |

---

## 二、迭代方案

### 2.1 P0 - 紧急修复

#### 2.1.1 修复 transformer.py .patched 标志

**问题**: `FunctionTransformer` 和 `ContextAwareTransformer` 的 `leave_FunctionDef` 方法中，`self.patched = True` 被注释掉，导致 `executor.py` 第186行的 `getattr(transformer, "patched", False)` 始终返回 `False`，无法正确验证补丁是否成功应用。

**修复方案**:
```python
# 修改前（第32行/第69行）:
# self.patched = True

# 修改后:
self.patched = True
```

**验证标准**:
- 变异测试 M-0032-P 和 M-0069-P 的 kill rate 达到 100%
- `executor.py` 的 `apply_patch` 方法能够正确检测补丁应用状态

#### 2.1.2 修复 CI流水线组件测试目录

**问题**: `ci.yml` 第74行 `python -m pytest tests/components/ -v` 指向不存在的目录

**修复方案**:
```yaml
# 修改前:
run: python -m pytest tests/components/ -v --tb=short

# 修改后:
run: python -m pytest tests/unit/ tests/integration/ -v --tb=short
```

**验证标准**:
- CI流水线 Component Tests 阶段成功通过

---

### 2.2 P1 - 功能增强

#### 2.2.1 API层扩展

**新增端点**:

| 端点 | 方法 | 描述 | 优先级 |
|------|------|------|--------|
| `/health` | GET | 健康检查 | P1 |
| `/tasks/{task_id}` | GET | 查询任务状态 | P1 |
| `/baselines` | GET | 获取基线列表 | P1 |
| `/baselines/{record_id}` | GET | 获取单个基线 | P1 |
| `/evaluate` | POST | AI评估接口 | P1 |

**设计原则**:
- 使用 FastAPI 标准响应格式
- 统一错误处理
- 添加请求追踪（trace_id）

#### 2.2.2 AI核心功能增强

**新增模块**: `src/ai/`

| 模块 | 功能 | 说明 |
|------|------|------|
| `qa_engine.py` | RAG问答引擎 | 基于向量检索的智能问答 |
| `classifier.py` | 文本分类器 | 测试结果自动分类 |
| `evaluator.py` | AI评估器 | 智能评估测试质量 |

**接口定义**:
```python
class AIQAEngine:
    def answer(self, question: str, context: str = None) -> str:
    
class AITextClassifier:
    def classify(self, text: str) -> str:
    
class AIEvaluator:
    def evaluate(self, output: str, expected: str) -> dict:
```

---

### 2.3 P2 - 运维能力

#### 2.3.1 健康检查端点

```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "0.2.0",
        "components": {
            "database": "connected",
            "redis": "connected",
            "celery": "running"
        }
    }
```

#### 2.3.2 监控指标

- 添加 Prometheus 指标采集
- 关键指标：请求数、延迟、错误率、任务队列长度

---

## 三、测试策略

### 3.1 测试覆盖要求

| 测试类型 | 覆盖场景 | 数量要求 |
|----------|----------|----------|
| 单元测试 | 正向、负向、边界、异常 | ≥20 |
| 治理测试 | 审批机制、安全边界、收敛验证 | ≥150 |
| 集成测试 | API层、Worker层、全链路 | ≥5 |
| 变异测试 | Kill Rate ≥70% | 全部通过 |

### 3.2 关键测试用例

**P0修复验证**:
- `test_transformer_patched_flag_set_on_match` - 验证补丁标志正确设置
- `test_executor_detects_patched_status` - 验证执行器检测补丁状态

**API扩展测试**:
- `test_health_check_returns_healthy` - 健康检查正向测试
- `test_health_check_with_downstream_failure` - 健康检查异常测试
- `test_task_status_query` - 任务状态查询

**AI功能测试**:
- `test_qa_engine_returns_relevant_answer` - QA引擎正向测试
- `test_classifier_categorizes_test_results` - 分类器测试
- `test_evaluator_scores_output_correctly` - 评估器测试

---

## 四、实施计划

### 4.1 时间线

| 阶段 | 时间 | 任务 | 负责人 |
|------|------|------|--------|
| 第一阶段 | 第1-2天 | P0紧急修复 | 技术委员会 |
| 第二阶段 | 第3-5天 | API层扩展 | 开发组 |
| 第三阶段 | 第6-8天 | AI核心功能 | AI研发组 |
| 第四阶段 | 第9-10天 | 测试验证 | QA组 |
| 第五阶段 | 第11-12天 | CI/CD验证 | DevOps |

### 4.2 里程碑

| 里程碑 | 完成标准 | 日期 |
|--------|----------|------|
| M1 | 变异测试Kill Rate ≥70% | 第2天 |
| M2 | CI流水线全绿 | 第5天 |
| M3 | API扩展完成 | 第8天 |
| M4 | AI功能集成 | 第10天 |
| M5 | 版本发布 v0.2.0 | 第12天 |

---

## 五、风险评估

| 风险项 | 风险等级 | 影响 | 缓解措施 |
|--------|----------|------|----------|
| transformer.py 修改影响现有测试 | 🟡 中 | 测试失败 | 先运行全量测试验证 |
| AI功能引入新依赖 | 🟡 中 | 依赖冲突 | 使用虚拟环境隔离 |
| CI流水线变更 | 🟢 低 | 构建失败 | 本地验证后再推送 |
| 并发测试回归 | 🟢 低 | 并发问题 | 运行并发测试套件 |

---

## 六、审核请求

### 6.1 审核维度

| 维度 | 评估标准 | 当前状态 | 审核意见 |
|------|----------|----------|----------|
| 代码质量 | 可读性、可维护性 | ✅ 良好 | [ ] |
| 测试覆盖 | 正向、负向、边界、异常 | ✅ 充分 | [ ] |
| 架构合规 | 符合 .trae-rules | ✅ 合规 | [ ] |
| 安全性 | 无安全漏洞 | ✅ 通过 | [ ] |
| 文档完整性 | 变更说明、API文档 | ⚠️ 待补充 | [ ] |

### 6.2 投票

| 委员 | 批准 | 有条件批准 | 拒绝 | 意见 |
|------|------|------------|------|------|
| 主席 | [ ] | [ ] | [ ] | |
| 委员1 | [ ] | [ ] | [ ] | |
| 委员2 | [ ] | [ ] | [ ] | |
| 委员3 | [ ] | [ ] | [ ] | |

### 6.3 决议

- 结论: [ ] 批准 [ ] 有条件批准 [ ] 拒绝
- 条件/建议: _________________________
- 签名: _________________________
- 日期: _________________________

---

**文档版本**: v1.0  
**最后更新**: 2026-07-20  
**审批状态**: 待审核