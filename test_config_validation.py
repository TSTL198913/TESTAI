import sys
sys.path.insert(0, '.')

from src.governance.config import GovernanceConfig
from src.governance.sdk import GovernanceClientSDK

print("=" * 70)
print("配置验证测试")
print("=" * 70)
print()

config_summary = GovernanceConfig.get_config_summary()
print("【配置状态】")
print("-" * 50)
print(f"  LLM已配置: {'✅' if config_summary['llm_configured'] else '❌'}")
print(f"  告警已配置: {'✅' if config_summary['alert_configured'] else '❌'}")
print(f"  数据库路径: {config_summary['db_path']}")
print(f"  日志级别: {config_summary['log_level']}")
print(f"  最大并发LLM调用: {config_summary['max_concurrent_llm_calls']}")
print()

print("【AI服务可用性测试】")
print("-" * 50)
sdk = GovernanceClientSDK()
print(f"  SDK可用: {'✅' if sdk.is_available() else '❌'}")

if sdk.is_available():
    print("  ⚠️  AI服务已配置，建议在生产环境测试前确保密钥有效")
else:
    print("  ⚠️  AI服务未配置，将使用mock响应进行诊断")

print()

validation_errors = GovernanceConfig.validate_config()
if validation_errors:
    print("【配置验证错误】")
    print("-" * 50)
    for error in validation_errors:
        print(f"  ❌ {error}")
else:
    print("【配置验证】")
    print("-" * 50)
    print("  ✅ 所有配置项验证通过")

print()
print("=" * 70)