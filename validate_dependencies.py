#!/usr/bin/env python3
"""
外部依赖链连通性验证 (本地直接连接, 不经过后端 HTTP API)

验证 4 个生产环境外部依赖:
  1. MongoDB (localhost:27017) - pymongo ping
  2. Redis    (localhost:6379)  - redis-py ping
  3. Git      (本地仓库)        - git status
  4. LLM      (DeepSeek API)    - 最小 chat completion 请求

设计原则:
  - 直接连接各依赖, 不经过后端 :8000, 避免与 pytest 集成测试碰撞
  - 每个测试独立, 单个失败不阻断其他测试
  - LLM 测试用最小 token 请求, 仅验证连通性 + 鉴权
"""

import os
import sys
import subprocess
import time

results = []

def record(name, success, detail, latency_ms=None):
    status = "✅ PASS" if success else "❌ FAIL"
    lat = f" ({latency_ms:.0f}ms)" if latency_ms is not None else ""
    print(f"{status} | {name}{lat}: {detail}")
    results.append((name, success, detail))


# ============================================================
# 1. MongoDB 连通性
# ============================================================
def test_mongodb():
    try:
        from pymongo import MongoClient
        from pymongo.errors import PyMongoError
        uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
        t0 = time.monotonic()
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        ping = client.admin.command("ping")
        latency = (time.monotonic() - t0) * 1000
        ok = ping.get("ok") == 1.0
        # 额外验证: 列出数据库 (确认非只读隔离)
        db_names = client.list_database_names()
        record("MongoDB", ok,
               f"ping={ping}, uri={uri}, dbs={db_names[:5]}", latency)
        client.close()
    except Exception as e:
        record("MongoDB", False, f"连接失败: {type(e).__name__}: {e}")


# ============================================================
# 2. Redis 连通性
# ============================================================
def test_redis():
    try:
        import redis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        t0 = time.monotonic()
        r = redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
        pong = r.ping()
        latency = (time.monotonic() - t0) * 1000
        # 额外验证: 写入+读取 (确认非只读)
        r.setex("_dep_probe", 10, "ok")
        val = r.get("_dep_probe")
        record("Redis", pong and val == b"ok",
               f"ping={pong}, set/get={val}, url={url}", latency)
        r.close()
    except Exception as e:
        record("Redis", False, f"连接失败: {type(e).__name__}: {e}")


# ============================================================
# 3. Git 连通性 (本地仓库操作)
# ============================================================
def test_git():
    try:
        repo = os.path.dirname(os.path.abspath(__file__))
        t0 = time.monotonic()
        # git status 验证仓库可读
        r1 = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo, capture_output=True, text=True, timeout=5)
        # git remote 验证远程仓库配置
        r2 = subprocess.run(
            ["git", "remote", "-v"],
            cwd=repo, capture_output=True, text=True, timeout=5)
        latency = (time.monotonic() - t0) * 1000
        # 验证 git 可执行文件本身
        r3 = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, timeout=5)
        ok = r1.returncode == 0 and r2.returncode == 0 and r3.returncode == 0
        remote_lines = [l for l in r2.stdout.strip().split("\n") if l]
        record("Git", ok,
               f"version={r3.stdout.strip()}, "
               f"status_changes={len(r1.stdout.strip().split(chr(10))) if r1.stdout.strip() else 0}, "
               f"remotes={len(remote_lines)//2 if remote_lines else 0}",
               latency)
    except Exception as e:
        record("Git", False, f"操作失败: {type(e).__name__}: {e}")


# ============================================================
# 4. LLM (DeepSeek API) 连通性 + 鉴权
# ============================================================
def test_llm():
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        record("LLM(DeepSeek)", False, "DEEPSEEK_API_KEY 未设置")
        return
    try:
        import requests
        base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        url = f"{base}/chat/completions"
        # 最小请求: 1 token 输出, 验证连通 + 鉴权
        payload = {
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        t0 = time.monotonic()
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        latency = (time.monotonic() - t0) * 1000

        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            model = data.get("model", "?")
            usage = data.get("usage", {})
            record("LLM(DeepSeek)", True,
                   f"model={model}, content={content!r}, "
                   f"tokens={usage.get('total_tokens')}, http=200", latency)
        elif resp.status_code == 401:
            record("LLM(DeepSeek)", False,
                   f"鉴权失败 (401): API key 无效或过期, key_len={len(key)}")
        else:
            record("LLM(DeepSeek)", False,
                   f"HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        record("LLM(DeepSeek)", False, f"请求失败: {type(e).__name__}: {e}")


# ============================================================
# 主流程
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("外部依赖链连通性验证 (直接连接, 不经过后端 HTTP)")
    print("=" * 70)
    print()
    test_mongodb()
    test_redis()
    test_git()
    test_llm()
    print()
    print("=" * 70)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"汇总: {passed}/{total} 依赖连通")
    for name, ok, detail in results:
        print(f"  {'✅' if ok else '❌'} {name}: {detail[:80]}")
    print("=" * 70)
    sys.exit(0 if passed == total else 1)
