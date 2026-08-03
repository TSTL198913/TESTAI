"""回归: 禁止裸 except 吞没异常 (用户规范 - 异常处理)

源码位置:
- src/monitoring/alert_manager.py:114  AlertManager._load_alerts
- src/users/user_manager.py:118        UserManager._load_users
- src/teams/team_manager.py:146        TeamManager._load_teams
- src/platform/api.py:616              get_task_status (Celery 后端查询)
- src/platform/workflow.py:550         变异测试 apply

根因:
  上述 5 处曾用 `except Exception:` (无 `as e`、无日志) 静默吞没异常, 违反
  "严禁使用裸 try...except: 吞没异常, 必须捕获具体异常并输出带上下文的结构化日志"。
  最严重风险: user_manager 用户文件损坏时静默 `self.users = {}`, 可锁死全员登录且无任何日志留痕。

修复:
  统一改为 `except Exception as e:` + `logger.error/warning(..., exc_info=True)`,
  保留原有降级行为 (清空/标志/404/continue) 以不破坏 API 契约与既有测试语义。

本测试验证 (真实严格, 非弱断言):
  1. 异常场景: 损坏/空文件加载时, 降级状态正确 (users/teams/alerts 清空, 标志置位)
  2. 可观测性: 结构化 ERROR 日志确实产生, 含异常类型名与文件路径 (证明不再静默)
  3. 边界场景: 空文件 (0 字节) 同样走降级 + 日志
  4. 正向场景: 合法文件加载正常, 不产生 ERROR 日志 (确认修复未破坏正常路径)
  5. 依赖场景: api Celery 后端故障 (ConnectionError) 时, 返回 404 且记录结构化错误

注意: workflow.py:550 变异 apply 路径需 AST 变异环境, 构造成本高; 该处修复为纯增量日志,
  不改变控制流 (仍 continue), 由全量回归套件覆盖行为不变性, 此处不单独构造。
"""
import json
import logging

import pytest

from src.monitoring.alert_manager import AlertManager
from src.users.user_manager import UserManager
from src.teams.team_manager import TeamManager


# ---------------------------------------------------------------------------
# AlertManager (src/monitoring/alert_manager.py)
# ---------------------------------------------------------------------------
class TestAlertManagerLoadNoLongerSilent:
    def test_corrupt_alerts_file_logs_structured_error(self, tmp_path, caplog):
        """损坏的 alerts.json 必须降级为空 且 记录含异常类型的 ERROR 日志。"""
        storage = tmp_path / "alerts_corrupt.json"
        storage.write_text("{ this is : not valid json >>>", encoding="utf-8")

        caplog.set_level(logging.ERROR, logger="src.monitoring.alert_manager")
        am = AlertManager(storage_path=str(storage))

        # 降级行为保留
        assert am.alerts == [], "损坏文件应降级为空 alerts"
        assert am.rules == {}, "损坏文件应降级为空 rules"
        assert am._file_load_failed is True, "损坏文件必须置 _file_load_failed 标志"

        # 可观测性: 不再静默 —— 必须有 ERROR 日志, 含异常类型名与文件路径
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "损坏文件加载必须记录 ERROR 日志 (禁止静默吞异常)"
        joined = " ".join(r.getMessage() for r in error_records)
        assert "JSONDecodeError" in joined, f"日志须含具体异常类型, 实际: {joined}"
        assert str(storage) in joined, f"日志须含文件路径上下文, 实际: {joined}"

    def test_empty_alerts_file_logs_structured_error(self, tmp_path, caplog):
        """边界: 空文件 (0 字节) 同样走降级 + 结构化日志。"""
        storage = tmp_path / "alerts_empty.json"
        storage.write_text("", encoding="utf-8")

        caplog.set_level(logging.ERROR, logger="src.monitoring.alert_manager")
        am = AlertManager(storage_path=str(storage))

        assert am._file_load_failed is True
        assert am.alerts == []
        assert any(r.levelno >= logging.ERROR for r in caplog.records), "空文件也必须记录 ERROR"

    def test_valid_alerts_file_loads_without_error_log(self, tmp_path, caplog):
        """正向: 合法文件正常加载, 不产生 ERROR 日志。"""
        storage = tmp_path / "alerts_valid.json"
        payload = {"alerts": [], "rules": []}
        storage.write_text(json.dumps(payload), encoding="utf-8")

        caplog.set_level(logging.ERROR, logger="src.monitoring.alert_manager")
        am = AlertManager(storage_path=str(storage))

        assert am._file_load_failed is False, "合法文件不应置失败标志"
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR], \
            "合法文件加载不应产生 ERROR 日志"


# ---------------------------------------------------------------------------
# UserManager (src/users/user_manager.py) —— 最严重: 静默清空可锁死全员
# ---------------------------------------------------------------------------
class TestUserManagerLoadNoLongerSilent:
    def test_corrupt_users_file_logs_structured_error(self, tmp_path, caplog):
        """损坏的 users.json 必须降级为空 且 记录 ERROR (不可静默锁死全员)。"""
        storage = tmp_path / "users_corrupt.json"
        storage.write_text("<<< not json >>>", encoding="utf-8")

        caplog.set_level(logging.ERROR, logger="src.users.user_manager")
        um = UserManager(storage_path=str(storage), use_database=False)

        # 降级: 损坏文件不崩溃, _load_users 重置为空后由 _initialize_default_users 兜底
        assert len(um.users) >= 1, "损坏文件应优雅降级到默认用户 (非崩溃/非空卡死)"
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "损坏用户文件必须记录 ERROR (禁止静默, 否则全员锁死无留痕)"
        joined = " ".join(r.getMessage() for r in error_records)
        assert "JSONDecodeError" in joined, f"日志须含异常类型, 实际: {joined}"
        assert str(storage) in joined, f"日志须含文件路径, 实际: {joined}"

    def test_empty_users_file_logs_structured_error(self, tmp_path, caplog):
        """边界: 空用户文件也必须记录 ERROR, 不可静默。"""
        storage = tmp_path / "users_empty.json"
        storage.write_text("", encoding="utf-8")

        caplog.set_level(logging.ERROR, logger="src.users.user_manager")
        um = UserManager(storage_path=str(storage), use_database=False)

        assert len(um.users) >= 1, "空文件应优雅降级到默认用户"
        assert any(r.levelno >= logging.ERROR for r in caplog.records), "空文件必须记录 ERROR"

    def test_valid_users_file_loads_without_error_log(self, tmp_path, caplog):
        """正向: 合法用户文件加载, 不产生 ERROR。"""
        storage = tmp_path / "users_valid.json"
        storage.write_text("{}", encoding="utf-8")  # 空字典是合法的 (无用户)

        caplog.set_level(logging.ERROR, logger="src.users.user_manager")
        um = UserManager(storage_path=str(storage), use_database=False)

        assert len(um.users) >= 1, "合法文件加载后应注册默认用户 (正常路径)"
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR], \
            "合法空字典文件不应产生 ERROR"


# ---------------------------------------------------------------------------
# TeamManager (src/teams/team_manager.py)
# ---------------------------------------------------------------------------
class TestTeamManagerLoadNoLongerSilent:
    def test_corrupt_teams_file_logs_structured_error(self, tmp_path, caplog):
        """损坏的 teams.json 必须降级为空 且 记录 ERROR。"""
        storage = tmp_path / "teams_corrupt.json"
        storage.write_text("<<< corrupt >>>", encoding="utf-8")

        caplog.set_level(logging.ERROR, logger="src.teams.team_manager")
        tm = TeamManager(storage_path=str(storage), use_database=False)

        # 降级: 损坏文件不崩溃, 重置后由默认团队注册兜底
        assert len(tm.teams) >= 1, "损坏文件应优雅降级到默认团队 (非崩溃)"
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "损坏团队文件必须记录 ERROR (禁止静默)"
        joined = " ".join(r.getMessage() for r in error_records)
        assert "JSONDecodeError" in joined, f"日志须含异常类型, 实际: {joined}"
        assert str(storage) in joined, f"日志须含文件路径, 实际: {joined}"


# ---------------------------------------------------------------------------
# api.py get_task_status —— Celery 后端故障须可观测 (不可伪装成 "Task not found")
# ---------------------------------------------------------------------------
class TestTaskStatusCeleryErrorLogged:
    def test_celery_backend_error_logged_and_404(self, client, auth_headers, monkeypatch, caplog):
        """Celery 后端故障 (如 Redis 不可达) 必须记录 ERROR, 不可静默伪装成 404。

        依赖场景: 外部 Celery/Redis 故障时, 应保留 404 API 契约, 但必须留下结构化日志
        以便运维区分 "后端宕机" 与 "任务不存在"。
        """
        caplog.set_level(logging.ERROR, logger="src.platform.api")

        def _boom(_task_id):
            raise ConnectionError("Redis unreachable (simulated)")

        # 拦截 celery_app.AsyncResult, 模拟后端连接故障
        monkeypatch.setattr("src.platform.api.celery_app.AsyncResult", _boom)

        response = client.get("/tasks/definitely-nonexistent-task", headers=auth_headers)

        # API 契约保留: 仍 404 (不破坏前端行为)
        assert response.status_code == 404, f"Celery 故障应回退 404, 实际: {response.status_code}"

        # 可观测性: 必须记录 ERROR, 含异常类型与 task_id
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "Celery 后端故障必须记录 ERROR (禁止静默伪装成 404)"
        joined = " ".join(r.getMessage() for r in error_records)
        assert "ConnectionError" in joined, f"日志须含异常类型, 实际: {joined}"
        assert "definitely-nonexistent-task" in joined, f"日志须含 task_id 上下文, 实际: {joined}"
