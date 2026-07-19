# src/engine/registry.py
import importlib
import logging

logger = logging.getLogger(__name__)

# 内核只保留核心协议处理器
_PROCESSOR_MAP = {
    "data": "src.engine.processor.data.DataProcessor",
    "assertion": "src.engine.processor.assertion.AssertionProcessor",
    "http": "src.engine.processor.http.HTTPProcessor",
    "grpc": "src.engine.processor.grpc.GrpcProcessor",
    "governance": "src.governance.processor.GovernanceProcessor",
}

def register_processor(name: str, path: str):
    """允许在运行时注册新的处理器，无需修改内核代码"""
    _PROCESSOR_MAP[name] = path
    logger.info(f"Processor registered: {name} -> {path}")

def get_processor_class(name: str):
    path = _PROCESSOR_MAP.get(name)
    if not path:
        raise ValueError(f"Unknown processor: {name}")

    module_path, class_name = path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)

def get_processor_instance(name: str, **kwargs):
    processor_cls = get_processor_class(name)
    return processor_cls(**kwargs)

import warnings


def get_pipeline(pipeline_config: list):
    processors = []
    for name in pipeline_config:
        if name == "request":
            warnings.warn(
                "The 'request' processor alias is deprecated. Use 'http' instead.",
                DeprecationWarning,
                stacklevel=2
            )
            name = "http"
        
        try:
            processors.append(get_processor_instance(name))
        except ValueError:
            logger.warning(f"Skipping unknown processor: {name}")
    return processors