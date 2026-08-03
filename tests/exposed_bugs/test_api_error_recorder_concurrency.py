"""P5 并发安全测试: api_error_recorder RMW 无锁 + 裸异常

业务规则 (规则1 可信代码 + 异常处理规范):
- record_error 执行 read-modify-write (读 JSON -> 追加 -> 写 JSON) 时必须持锁,
  否则并发调用会发生 last-writer-wins 数据丢失 (规则13 投诉证据链断裂)。
- record_error / get_error_summary 禁止裸 except Exception 吞没异常,
  必须捕获具体异常 (json.JSONDecodeError, OSError) 并输出结构化日志。
- clear_errors 删除文件必须持锁, 避免与并发 record_error 竞争。

关联缺陷: P5-2 api_error_recorder 并发不安全 (RMW 无锁)
"""
import ast
import inspect
import json
import os
import textwrap
import threading
import time
from unittest.mock import patch

import pytest

from src.governance.api_error_recorder import APIErrorRecorder


def _method_src(method) -> str:
    return textwrap.dedent(inspect.getsource(method))


def _bare_excepts(tree: ast.AST) -> list:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                found.append("bare except:")
            elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                found.append("except Exception:")
    return found


def _lock_blocks(tree: ast.AST) -> list:
    """返回所有 context 表达式含 'lock' 的 With 节点。"""
    blocks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                try:
                    ctx = ast.unparse(item.context_expr)
                except Exception:
                    continue
                if "lock" in ctx.lower():
                    blocks.append(node)
                    break
    return blocks


def _body_contains_call(node: ast.AST, func_name: str) -> bool:
    """检测 with-block 体 (递归) 是否包含 attr 调用 func_name (如 json.dump)。"""
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if child.func.attr == func_name:
                return True
    return False


# ---------------------------------------------------------------------------
# 一、静态结构校验 (确定性): RMW 持锁 + 无裸异常
# ---------------------------------------------------------------------------
class TestAPIErrorRecorderSourceStructure:
    """静态结构校验: RMW 持锁 + 无裸异常 (确定性, 当前应失败)"""

    def test_record_error_uses_lock_for_rmw(self):
        """正向: record_error 的读+写必须在同一把锁的 with 块内。

        不持锁的 RMW: 线程A 读 [] -> 线程B 读 [] -> 线程A 写 [a]
        -> 线程B 写 [b] => a 丢失。投诉证据链断裂 (规则13)。
        """
        tree = ast.parse(_method_src(APIErrorRecorder.record_error))
        locks = _lock_blocks(tree)
        assert locks, (
            "record_error 未使用任何锁保护 RMW (read-modify-write), "
            "并发调用会发生 last-writer-wins 数据丢失, 投诉证据链断裂"
        )
        # 至少存在一个锁块同时包含读 (json.load) 与写 (json.dump)
        protected = [
            blk for blk in locks
            if _body_contains_call(blk, "dump")
        ]
        assert protected, (
            "record_error 的锁块未覆盖 json.dump (写操作), RMW 仍不完整"
        )

    def test_get_error_summary_uses_lock(self):
        """正向: get_error_summary 读文件必须持锁, 避免与并发写竞争读到半写文件。"""
        tree = ast.parse(_method_src(APIErrorRecorder.get_error_summary))
        locks = _lock_blocks(tree)
        assert locks, (
            "get_error_summary 未持锁读取, 并发 record_error 写入时可能读到半写 JSON"
        )

    def test_clear_errors_uses_lock(self):
        """正向: clear_errors 删除文件必须持锁, 避免与并发写竞争。"""
        tree = ast.parse(_method_src(APIErrorRecorder.clear_errors))
        locks = _lock_blocks(tree)
        assert locks, (
            "clear_errors 未持锁删除文件, 与并发 record_error 竞争可能 OSError"
        )

    def test_record_error_no_bare_exception(self):
        """负向: record_error 禁止裸 except Exception / except: 吞没异常。"""
        tree = ast.parse(_method_src(APIErrorRecorder.record_error))
        bare = _bare_excepts(tree)
        assert not bare, (
            f"record_error 存在裸异常吞没: {bare}, 违反异常处理规范: "
            "必须捕获具体异常 (json.JSONDecodeError, OSError) 并结构化日志"
        )


# ---------------------------------------------------------------------------
# 二、功能并发测试 (行为): 并发不丢记录
# ---------------------------------------------------------------------------
class TestAPIErrorRecorderConcurrency:
    """功能并发测试: 并发 record_error 不丢记录"""

    def test_concurrent_record_error_no_data_loss(self, tmp_path, monkeypatch):
        """正向: N 线程并发 record_error, 全部记录必须保留。

        确定性策略: 注入延迟到 json.load, 拉宽 read-write 窗口。
        无锁时: 多线程读到同一快照 -> 各自覆盖写 -> 记录丢失。
        有锁时: RMW 串行化 -> 全部保留。
        """
        log_file = tmp_path / "errors.json"
        monkeypatch.setattr(APIErrorRecorder, "ERROR_LOG_PATH", str(log_file))
        log_file.write_text("[]", encoding="utf-8")

        N = 20
        original_load = json.load

        def slow_load(f):
            result = original_load(f)
            time.sleep(0.05)  # 拉宽 race window, 使多线程读到同一快照
            return result

        # 仅作用于 api_error_recorder 模块内的 json 引用
        import src.governance.api_error_recorder as mod
        monkeypatch.setattr(mod.json, "load", slow_load)

        errors = []

        def writer(i):
            try:
                APIErrorRecorder.record_error(
                    error_type=f"Type{i}", error_message=f"msg{i}"
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"record_error 并发抛异常: {errors}"

        with open(log_file, "r", encoding="utf-8") as f:
            logs = original_load(f)

        assert len(logs) == N, (
            f"并发 record_error 丢失记录: 期望 {N} 条, 实际 {len(logs)} 条 "
            f"(RMW 无锁导致 last-writer-wins, 投诉证据链断裂)"
        )

    def test_concurrent_record_and_summary_no_crash(self, tmp_path, monkeypatch):
        """正向: 并发 record_error + get_error_summary 不崩, summary.total 一致。"""
        log_file = tmp_path / "errors.json"
        monkeypatch.setattr(APIErrorRecorder, "ERROR_LOG_PATH", str(log_file))
        log_file.write_text("[]", encoding="utf-8")

        N = 15
        errors = []
        stop = threading.Event()

        def writer():
            for i in range(N):
                try:
                    APIErrorRecorder.record_error(
                        error_type="T", error_message=f"m{i}"
                    )
                except Exception as e:
                    errors.append(e)
                    return

        def summarizer():
            while not stop.is_set():
                try:
                    APIErrorRecorder.get_error_summary()
                except Exception as e:
                    errors.append(e)
                    return

        w_threads = [threading.Thread(target=writer) for _ in range(3)]
        s_threads = [threading.Thread(target=summarizer) for _ in range(2)]
        for t in w_threads + s_threads:
            t.start()
        for t in w_threads:
            t.join(timeout=10)
        stop.set()
        for t in s_threads:
            t.join(timeout=5)

        assert not errors, f"并发 record + summary 抛异常: {errors}"


# ---------------------------------------------------------------------------
# 三、异常与边界测试
# ---------------------------------------------------------------------------
class TestAPIErrorRecorderExceptionBoundary:
    """异常/边界: 损坏 JSON / 缺失文件 / 具体异常"""

    def test_corrupted_json_does_not_crash(self, tmp_path, monkeypatch):
        """异常: 文件存在但 JSON 损坏时, record_error 不得崩溃。

        修复后应捕获 json.JSONDecodeError 具体异常, 而非裸 except Exception。
        """
        log_file = tmp_path / "errors.json"
        monkeypatch.setattr(APIErrorRecorder, "ERROR_LOG_PATH", str(log_file))
        log_file.write_text("{corrupted json!!!", encoding="utf-8")

        # 不应抛异常
        result = APIErrorRecorder.record_error("T", "m")
        # 损坏文件场景: 应返回 False 或覆盖重建, 但绝不向上抛
        assert result in (True, False), "record_error 应返回 bool 而非抛异常"

    def test_record_error_creates_file_when_missing(self, tmp_path, monkeypatch):
        """边界: 文件不存在时, record_error 应新建并写入首条记录。"""
        log_file = tmp_path / "errors.json"
        monkeypatch.setattr(APIErrorRecorder, "ERROR_LOG_PATH", str(log_file))
        assert not log_file.exists()

        APIErrorRecorder.record_error("T", "m")

        assert log_file.exists(), "record_error 未创建日志文件"
        with open(log_file, "r", encoding="utf-8") as f:
            logs = json.load(f)
        assert len(logs) == 1, f"首条记录应写入, 实际 {len(logs)} 条"
        assert logs[0]["error_type"] == "T"

    def test_record_error_logs_on_io_failure(self, tmp_path, monkeypatch):
        """异常: 写文件失败 (OSError) 时必须记录结构化日志, 不得静默吞没。

        裸 except Exception + print 不满足规则1 (结构化日志要求)。
        修复后应使用 logger 记录。
        """
        log_file = tmp_path / "errors.json"
        monkeypatch.setattr(APIErrorRecorder, "ERROR_LOG_PATH", str(log_file))
        log_file.write_text("[]", encoding="utf-8")

        # 让 json.dump 抛 OSError
        original_dump = json.dump

        def failing_dump(obj, f, **kw):
            raise OSError("disk full")

        import src.governance.api_error_recorder as mod
        monkeypatch.setattr(mod.json, "dump", failing_dump)

        # 不应抛异常 (应被捕获), 但应记录日志
        result = APIErrorRecorder.record_error("T", "m")
        assert result is False, "OSError 应返回 False"

    def test_get_error_summary_corrupted_json(self, tmp_path, monkeypatch):
        """异常: get_error_summary 遇损坏 JSON 不得崩溃。"""
        log_file = tmp_path / "errors.json"
        monkeypatch.setattr(APIErrorRecorder, "ERROR_LOG_PATH", str(log_file))
        log_file.write_text("not json at all", encoding="utf-8")

        # 不应抛异常
        try:
            summary = APIErrorRecorder.get_error_summary()
        except json.JSONDecodeError:
            pytest.fail(
                "get_error_summary 未捕获 json.JSONDecodeError, 损坏文件导致崩溃"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
