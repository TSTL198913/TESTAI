# src/conftest.py
import pytest
from src.report.generator import generator
from src.report.storage import registry

GLOBAL_RESULTS = {}


@pytest.fixture(scope="session", autouse=True)
def run_report_generator():
    yield
    # 从单例中获取数据
    all_data = registry.get_all()
    print(f"\n[DEBUG] 正在进入会话销毁阶段，读取到的 Registry 内存地址: {id(registry)}")
    print(f"[DEBUG] Registry 数据大小: {len(all_data)}")

    if all_data:
        report_path = generator.generate(all_data)
        print(f"[SUCCESS] 报告生成成功: {report_path}")
    else:
        print("[WARNING] Registry 为空，没有任何测试数据生成！")