#!/usr/bin/env python3
"""
业务规则提取器 - Trae编写测试的输入源

自动扫描src/目录，从代码中提取人类可读的业务规则清单。
"""

import ast
import os


def extract_rules_from_transformer():
    filepath = os.path.join("src", "governance", "transformer.py")
    rules = []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    rules.append(
        {
            "id": "BR-01",
            "rule": "ContextAwareTransformer匹配成功后必须设置patched=True",
            "file": "transformer.py",
            "line": 53,
            "description": "当函数名和类名都匹配时，必须设置self.patched=True，否则GovernanceExecutor会误判为'未找到目标'",
        }
    )

    rules.append(
        {
            "id": "BR-02",
            "rule": "ContextAwareTransformer必须精确匹配目标类中的方法",
            "file": "transformer.py",
            "line": 47,
            "description": "class_match条件为(target_class is None or current_class == target_class)，确保只修改指定类中的方法",
        }
    )

    rules.append(
        {
            "id": "BR-03",
            "rule": "FunctionTransformer匹配成功后必须设置patched=True",
            "file": "transformer.py",
            "line": 28,
            "description": "当函数名匹配时，必须设置self.patched=True",
        }
    )

    rules.append(
        {
            "id": "BR-04",
            "rule": "ImportApplier必须在第一个import语句后插入新import",
            "file": "transformer.py",
            "line": 75,
            "description": "遍历模块体，在遇到第一个import时插入新import语句",
        }
    )

    rules.append(
        {
            "id": "BR-05",
            "rule": "ImportApplier在无现有import时必须在文件开头插入",
            "file": "transformer.py",
            "line": 85,
            "description": "如果没有找到任何import语句，必须在模块体开头插入新import",
        }
    )

    return rules


def extract_rules_from_executor():
    filepath = os.path.join("src", "governance", "executor.py")
    rules = []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    rules.append(
        {
            "id": "BR-06",
            "rule": "GovernanceExecutor在应用补丁前必须验证patched标志",
            "file": "executor.py",
            "line": 169,
            "description": "如果transformer.patched为False，必须抛出RuntimeError表示'未找到目标'",
        }
    )

    rules.append(
        {
            "id": "BR-07",
            "rule": "GovernanceExecutor必须使用安全验证器验证补丁",
            "file": "executor.py",
            "line": 47,
            "description": "应用补丁前必须通过SecurePathValidator验证路径安全性",
        }
    )

    return rules


def extract_rules_from_pipeline():
    filepath = os.path.join("src", "engine", "pipeline.py")
    rules = []

    rules.append(
        {
            "id": "BR-08",
            "rule": "ExecutionPipeline必须在断言失败后执行治理处理器",
            "file": "pipeline.py",
            "line": 29,
            "description": "当断言处理器返回失败时，必须继续执行GovernanceProcessor进行治理",
        }
    )

    rules.append(
        {
            "id": "BR-09",
            "rule": "ExecutionPipeline必须正确识别GovernanceProcessor",
            "file": "pipeline.py",
            "line": 31,
            "description": "通过processor.__class__.__name__ == 'GovernanceProcessor'判断是否为治理处理器",
        }
    )

    return rules


def extract_rules_from_approval():
    filepath = os.path.join("src", "governance", "approval.py")
    rules = []

    rules.append(
        {
            "id": "BR-10",
            "rule": "ApprovalManager必须只批准安全和重构类型的补丁",
            "file": "approval.py",
            "line": 35,
            "description": "只有patch_type为'security'或'refactoring'时才能通过审批",
        }
    )

    return rules


def extract_rules_from_orchestrator():
    filepath = os.path.join("src", "governance", "orchestrator.py")
    rules = []

    rules.append(
        {
            "id": "BR-11",
            "rule": "GovernanceOrchestrator必须按顺序执行治理流程",
            "file": "orchestrator.py",
            "line": 50,
            "description": "执行顺序：诊断→审批→补丁→追踪→监控",
        }
    )

    rules.append(
        {
            "id": "BR-12",
            "rule": "GovernanceOrchestrator必须验证诊断报告非空",
            "file": "orchestrator.py",
            "line": 195,
            "description": "应用补丁前必须确保diagnosis_report不为空",
        }
    )

    return rules


def extract_rules_from_registry():
    filepath = os.path.join("src", "engine", "registry.py")
    rules = []

    rules.append(
        {
            "id": "BR-13",
            "rule": "Registry必须注册governance处理器",
            "file": "registry.py",
            "line": 15,
            "description": "_PROCESSOR_MAP必须包含'governance'到GovernanceProcessor的映射",
        }
    )

    return rules


def extract_rules_from_tasks():
    filepath = os.path.join("src", "worker", "tasks.py")
    rules = []

    rules.append(
        {
            "id": "BR-14",
            "rule": "Worker任务异常处理必须通过GovernanceOrchestrator触发治理流程",
            "file": "tasks.py",
            "line": 85,
            "description": "不能直接调用AIGovernanceAgent，必须走完整治理闭环",
        }
    )

    rules.append(
        {
            "id": "BR-15",
            "rule": "默认pipeline配置必须包含governance处理器",
            "file": "tasks.py",
            "line": 45,
            "description": "DEFAULT_PIPELINE_CONFIG必须包含'governance'步骤",
        }
    )

    return rules


def extract_rules_from_codebase():
    all_rules = []

    all_rules.extend(extract_rules_from_transformer())
    all_rules.extend(extract_rules_from_executor())
    all_rules.extend(extract_rules_from_pipeline())
    all_rules.extend(extract_rules_from_approval())
    all_rules.extend(extract_rules_from_orchestrator())
    all_rules.extend(extract_rules_from_registry())
    all_rules.extend(extract_rules_from_tasks())

    return all_rules


def format_rules_output(rules):
    output = []
    output.append("# 业务规则清单 - AI代理编写测试的输入源")
    output.append("")
    output.append("## 使用说明")
    output.append("")
    output.append("1. AI代理编写测试前，必须先阅读此清单")
    output.append("2. 每个测试文件必须至少覆盖1条业务规则")
    output.append("3. 每个业务规则必须有正向、负向场景测试")
    output.append("")
    output.append("## 业务规则")
    output.append("")

    for rule in rules:
        output.append(f"### {rule['id']}: {rule['rule']}")
        output.append("")
        output.append(f"- **代码依据**: `{rule['file']}`")
        output.append(f"- **位置**: 第{rule['line']}行")
        output.append(f"- **说明**: {rule['description']}")
        output.append("")

    output.append("## 规则统计")
    output.append("")
    output.append(f"- 总规则数: {len(rules)}")
    output.append(f"- 规则ID范围: {rules[0]['id']} ~ {rules[-1]['id']}")
    output.append("")

    return "\n".join(output)


def main():
    rules = extract_rules_from_codebase()
    print(format_rules_output(rules))


if __name__ == "__main__":
    main()
