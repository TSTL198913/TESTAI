# 框架缺陷报告：AI 治理响应解析错误

**报告编号**: FD-2026-001  
**报告日期**: 2026-07-16  
**报告级别**: **CRITICAL**  
**受影响模块**: `src/governance/sdk.py`

---

## 一、问题描述

### 1.1 故障现象

测试执行报告显示：
```
gov_test FAILED
故障详情: Unexpected error: Server error 500
AI 治理洞察 (信心指数: 0%)
诊断结论: Agent failed to produce valid JSON: 'ChatCompletion' object has no attribute 'content'
```

### 1.2 根本原因

在 `src/governance/sdk.py` 的 `chat_completion` 方法中：

```python
# 当前实现 (错误)
response = await self.client.chat.completions.create(...)
return response  # 返回的是 ChatCompletion 对象
```

而在 `src/governance/agent.py` 的 `analyze_with_context` 方法中：

```python
# 当前实现 (错误)
raw_content = response.content  # ChatCompletion 对象没有 content 属性
```

**OpenAI Python SDK v1.x 的响应结构**：
- `ChatCompletion` 对象 → `response.choices[0].message.content`
- 直接访问 `response.content` 会抛出 `AttributeError`

### 1.3 影响范围

| 影响层级 | 影响描述 |
|----------|----------|
| **AI 治理** | 所有依赖 AI 诊断的测试失败 |
| **收敛能力** | 迭代分数计算异常（信心指数为 0） |
| **测试报告** | 无法生成有效治理洞察 |
| **生产可用性** | 治理闭环完全失效 |

---

## 二、修复方案

### 2.1 修复代码

```python
# src/governance/sdk.py - chat_completion 方法
async def chat_completion(self, messages, model="deepseek-chat", temperature=0.2):
    if not self.breaker.can_execute():
        raise RuntimeError("Circuit Breaker is OPEN: Governance service unavailable.")

    try:
        response = await self.client.chat.completions.create(
            model=model, messages=messages, temperature=temperature
        )
        self.breaker.record_success()
        
        # 修复：返回 message 对象而不是整个 ChatCompletion
        if response.choices and response.choices[0].message:
            return response.choices[0].message
        raise ValueError("Empty response from AI service")
        
    except Exception as e:
        self.breaker.record_failure()
        raise e
```

### 2.2 验证测试

已在 `tests/governance/test_fixed_sdk.py` 中实现测试用例：

| 测试用例 | 验证内容 | 状态 |
|----------|----------|------|
| `test_chat_completion_returns_message_object` | 返回的对象有 content 属性 | ✅ PASS |
| `test_chat_completion_handles_empty_response` | 空 choices 时抛出 ValueError | ✅ PASS |
| `test_chat_completion_handles_null_message` | null message 时抛出 ValueError | ✅ PASS |

---

## 三、技术委员会决议

**决议编号**: TC-2026-FD-001  
**决议内容**: 
1. 此缺陷为 CRITICAL 级别，必须立即修复
2. 修复方案已通过测试验证，建议纳入下一个迭代
3. 修复后需执行完整回归测试，确保治理闭环恢复正常

**签署**: 技术委员会主席  
**日期**: 2026-07-16

---

**文档版本**: v1.0  
**最后更新**: 2026-07-16