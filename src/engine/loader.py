# src/engine/loader.py (新增文件)
from src.engine.registry import register_processor


def load_extensions():
    # 这里可以扩展为自动扫描 extensions 目录，目前先显式注册
    register_processor(
        "eval_platform",
        "extensions.eval_platform.processor.EvalPlatformProcessor"
    )