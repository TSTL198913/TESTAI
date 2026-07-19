# AI Agent测试编写标准（统一规范）

## 适用范围

本规范适用于所有AI代理（Trae、Cursor、Claude、Codex、GPT等）编写的测试代码。

## 强制约束

### 禁止清单

| 禁止模式 | 错误示例 | 正确示例 |
|----------|----------|----------|
| `assert hasattr(...)` | `assert hasattr(obj, 'attr')` | `assert obj.attr == expected` |
| `pytest.skip()` | `pytest.skip("broken")` | 修复测试或删除 |
| `except Exception: pass` | `try: x() except Exception: pass` | `with pytest.raises(Exception): x()` |
| 仅验证非空 | `assert len(items) > 0` | `assert len(items) == expected_count` |
| 仅验证存在 | `assert result is not None` | `assert result.status == "PASSED"` |

### 必须清单

| 要求 | 说明 |
|------|------|
| 五种场景覆盖 | 正向、负向、边界、异常、依赖 |
| 强断言 | 每个测试至少1个业务逻辑断言 |
| 业务规则覆盖 | 每个测试文件至少覆盖1条业务规则 |
| 测试命名 | `test_{模块}_{场景}_{预期结果}` |

### 质量阈值

| 指标 | 阈值 |
|------|------|
| 变异测试kill rate | ≥80% |
| 断言强度评分 | ≥85分 |
| 五种场景覆盖率 | 100% |
| 测试通过率 | 100% |

## 测试编写流程

1. 阅读业务规则清单 (`tests/business_rules.txt`)
2. 分析被测试代码
3. 设计五种场景测试
4. 编写测试代码（遵守禁止清单和必须清单）
5. 运行 `python tests/utils/auto_mutation_gate.py --test <测试文件>`
6. kill rate ≥80% → 通过；否则返回步骤3重写
7. 运行 `python tests/ci_guard.py` 检查反模式

## 测试模板

```python
"""
测试模块: {模块名}
覆盖业务规则: {BR-ID列表}
"""
import pytest

from {被测试模块}


class Test{ClassName}:
    """{类名}测试"""

    def test_{正向场景}_happy_path(self):
        """正向场景：正常输入→预期输出"""
        # 准备
        # 执行
        # 断言
        assert {业务结果} == {预期值}

    def test_{负向场景}_invalid_input(self):
        """负向场景：异常输入→拒绝处理"""
        # 准备
        # 执行
        # 断言
        with pytest.raises({预期异常}):
            {执行代码}

    def test_{边界场景}_edge_case(self):
        """边界场景：边界值→正确处理"""
        # 准备
        # 执行
        # 断言

    def test_{异常场景}_error_handling(self):
        """异常场景：运行时异常→正确捕获"""
        # 准备
        # 执行
        # 断言

    def test_{依赖场景}_dependency_failure(self):
        """依赖场景：依赖失败→降级处理"""
        # 准备
        # 执行
        # 断言
```

## 验证机制

### 本地验证（开发阶段）
- `python tests/utils/auto_mutation_gate.py --test <测试文件>`
- `python tests/ci_guard.py`

### Git Hook（提交阶段）
- pre-commit hook自动运行CI守卫和变异验证
- 未通过则阻止提交

### CI流水线（PR阶段）
- 自动运行三层验证：CI守卫 → 变异验证门 → 分层有效性验证
- 未通过则阻止合并

## 违规处理

1. 违反禁止清单 → 拒绝提交
2. 未覆盖五种场景 → 拒绝提交
3. kill rate < 80% → 拒绝提交
4. 断言强度 < 85分 → 拒绝提交

## 技术委员会决议

**编号**: TC-2026-006  
**主题**: AI代理测试编写统一标准  
**日期**: 2026-07-18  
**生效**: 立即生效