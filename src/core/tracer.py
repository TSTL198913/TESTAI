# src/core/tracer.py
import contextvars
import logging
import uuid
from typing import Optional

_trace_id_ctx = contextvars.ContextVar("trace_id", default="system")

class TraceIDFilter(logging.Filter):
    def filter(self, record):
        record.trace_id = _trace_id_ctx.get()
        return True

def set_trace_id(trace_id: Optional[str] = None):
    tid = trace_id or str(uuid.uuid4())[:8]
    return _trace_id_ctx.set(tid) # 返回 token

def reset_trace_id(token):
    _trace_id_ctx.reset(token)

def get_trace_id() -> Optional[str]:
    """获取当前的 Trace ID"""
    return _trace_id_ctx.get()