# Trae测试编写规范（技术委员会制定）

## 一、测试核心哲学

1. **测试目标**: 验证业务逻辑正确性、发现生产环境问题，绝不单纯追求代码覆盖率
2. **五种场景全覆盖**: 正向、负向、边界、异常、依赖
3. **强断言要求**: 必须验证具体业务逻辑，禁止仅验证status的弱断言
4. **无文档时**: 先基于代码梳理业务规则和风险点，再围绕规则设计测试
5. **禁止修改**: 测试代码只允许修改tests/下文件，禁止修改src/等业务代码

---

## 二、禁止清单（违反即CI失败）

### 2.1 禁止弱断言

| 禁止模式 | 错误示例 | 正确示例 |
|----------|----------|----------|
| `assert hasattr(...)` | `assert hasattr(obj, 'attr')` | `assert obj.attr == expected_value` |
| `assert True` | `assert True` | `assert result.status == "PASSED"` |
| `assert len(list) > 0` | `assert len(items) > 0` | `assert len(items) == expected_count` |

### 2.2 禁止失败跳过

| 禁止模式 | 说明 |
|----------|------|
| `pytest.skip()` | 禁止跳过失败测试，必须修复或删除 |
| `pytest.mark.skip()` | 禁止标记跳过，必须修复或删除 |

### 2.3 禁止异常吞没

| 禁止模式 | 错误示例 | 正确示例 |
|----------|----------|----------|
| `except Exception: pass` | `try: x() except Exception: pass` | `with pytest.raises(Exception): x()` |
| `except BaseException: pass` | `try: x() except BaseException: pass` | `with pytest.raises(SpecificError): x()` |

---

## 三、必须清单（缺少即CI失败）

### 3.1 五种场景覆盖

| 场景类型 | 定义 | 示例 |
|----------|------|------|
| **正向场景** | 正常输入→预期输出 | `test_transformer_patches_correct_function` |
| **负向场景** | 异常输入→拒绝/错误处理 | `test_transformer_rejects_wrong_function_name` |
| **边界场景** | 输入边界值→正确处理 | `test_transformer_handles_empty_new_body` |
| **异常场景** | 运行时异常→正确捕获 | `test_executor_raises_error_when_patch_fails` |
| **依赖场景** | 依赖模块异常→降级处理 | `test_transformer_works_with_missing_imports` |

### 3.2 强断言标准

每个测试用例必须包含：
- 至少1个验证**业务逻辑结果**的断言
- 至少1个验证**状态码/错误信息**的断言
- 禁止仅验证"非空"或"存在"

### 3.3 测试命名规范

```python
# 格式：test_<模块>_<场景>_<预期结果>
def test_transformer_patches_correct_function():      # 正向场景
def test_transformer_rejects_wrong_function_name():   # 负向场景  
def test_transformer_handles_empty_new_body():        # 边界场景
def test_executor_raises_error_when_patch_fails():    # 异常场景
```

---

## 四、Trae测试编写流程

```
┌─────────────────────────────────────────────────────────────┐
│                    Trae测试编写流程                          │
├─────────────────────────────────────────────────────────────┤
│  1. 代码分析                                                │
│     └─ 读取被测试代码，梳理业务规则和风险点                    │
│                                                             │
│  2. 测试设计                                                │
│     └─ 基于业务规则，设计五种场景的测试用例                    │
│                                                             │
│  3. 代码编写                                                │
│     └─ 按照禁止清单和必须清单编写测试代码                      │
│                                                             │
│  4. 自检CI守卫                                              │
│     └─ 运行 python tests/ci_guard.py                        │
│     └─ 未通过→返回步骤3重写                                  │
│                                                             │
│  5. 运行有效性门控                                          │
│     └─ 运行 pytest tests/governance/test_effectiveness_gate.py│
│     └─ 未通过→返回步骤3重写                                  │
│                                                             │
│  6. 变异测试评估                                            │
│     └─ 运行 pytest tests/governance/test_mutation.py         │
│     └─ kill rate < 80%→返回步骤3重写                        │
│                                                             │
│  7. 全量回归验证                                            │
│     └─ 运行 pytest tests/                                   │
│     └─ 未全部通过→返回步骤3重写                              │
│                                                             │
│  8. 提交代码                                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、质量阈值

| 指标 | 阈值 | 说明 |
|------|------|------|
| **业务规则覆盖率** | ≥90% | 每个业务规则至少一个测试用例 |
| **异常场景覆盖率** | ≥80% | 每个异常分支至少一个测试用例 |
| **变异测试kill rate** | ≥80% | 变异后测试必须失败的比例 |
| **断言强度评分** | ≥85分 | 弱断言扣10分/个，skip扣20分/个 |
| **测试通过率** | 100% | 所有测试必须通过 |

---

## 六、Trae编写测试检查清单

编写测试时，Trae必须逐条确认：

- [ ] ✅ 覆盖正向场景
- [ ] ✅ 覆盖负向场景
- [ ] ✅ 覆盖边界场景
- [ ] ✅ 覆盖异常场景
- [ ] ✅ 覆盖依赖场景
- [ ] ✅ 无弱断言（`assert hasattr`）
- [ ] ✅ 无失败跳过（`pytest.skip`）
- [ ] ✅ 无异常吞没（`except Exception: pass`）
- [ ] ✅ 每个测试至少1个业务逻辑断言
- [ ] ✅ 测试命名符合规范
- [ ] ✅ CI守卫通过
- [ ] ✅ 有效性门控通过
- [ ] ✅ 变异测试kill rate ≥80%
- [ ] ✅ 全量测试通过

---

## 七、示例：Trae编写有效测试的标准模板

```python
# tests/governance/test_transformer.py
"""
Transformer模块测试 - Trae编写标准示例
"""
import pytest
from src.governance.transformer import ContextAwareTransformer


class TestContextAwareTransformer:
    """ContextAwareTransformer测试类"""

    def test_patches_correct_method_in_class(self):
        """
        正向场景：匹配类内方法成功
        验证：patched=True，代码被替换
        """
        source_code = """
class MyClass:
    def target_method(self):
        return "original"
"""
        transformer = ContextAwareTransformer(
            target_function="target_method",
            new_body='return "patched"',
            target_class="MyClass"
        )
        
        result = transformer.apply(source_code)
        
        assert transformer.patched is True, "补丁标记应设为True"
        assert 'return "patched"' in result, "代码应被替换"

    def test_rejects_wrong_class_name(self):
        """
        负向场景：类名不匹配
        验证：patched=False，代码不被替换
        """
        source_code = """
class MyClass:
    def target_method(self):
        return "original"
"""
        transformer = ContextAwareTransformer(
            target_function="target_method",
            new_body='return "patched"',
            target_class="WrongClass"
        )
        
        result = transformer.apply(source_code)
        
        assert transformer.patched is False, "补丁标记应保持False"
        assert 'return "original"' in result, "代码应保持不变"

    def test_handles_empty_new_body(self):
        """
        边界场景：空代码块
        验证：正常处理，不抛出异常
        """
        source_code = """
class MyClass:
    def target_method(self):
        return "original"
"""
        transformer = ContextAwareTransformer(
            target_function="target_method",
            new_body="",
            target_class="MyClass"
        )
        
        result = transformer.apply(source_code)
        
        assert transformer.patched is True, "补丁标记应设为True"

    def test_raises_error_on_invalid_syntax(self):
        """
        异常场景：无效语法输入
        验证：抛出SyntaxError
        """
        source_code = "def invalid("
        
        transformer = ContextAwareTransformer(
            target_function="invalid",
            new_body="pass"
        )
        
        with pytest.raises(SyntaxError):
            transformer.apply(source_code)

    def test_works_without_class_filter(self):
        """
        依赖场景：无类过滤依赖
        验证：仅匹配函数名即可成功
        """
        source_code = """
def standalone_func():
    return "original"
"""
        transformer = ContextAwareTransformer(
            target_function="standalone_func",
            new_body='return "patched"'
        )
        
        result = transformer.apply(source_code)
        
        assert transformer.patched is True, "补丁标记应设为True"
        assert 'return "patched"' in result, "代码应被替换"
```

---

## 八、技术委员会决议

**编号**: TC-2026-001  
**主题**: Trae测试编写规范  
**日期**: 2026-07-18  
**决议**: 本规范自发布之日起生效，Trae编写的所有测试用例必须遵守。CI守卫将强制执行本规范，违反者禁止合并代码。

**签字**: 技术委员会主席