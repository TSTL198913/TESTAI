# D:\workspace\TestAI\scripts\check_db_health.py
from pymongo import MongoClient
import sys


def check_health():
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client["testai"]
        collection = db["execution_results"]

        count = collection.count_documents({})
        last_doc = collection.find_one(sort=[("_id", -1)])

        print(f"--- 系统健康状态 ---")
        print(f"总文档数: {count}")
        if last_doc:
            print(f"最后插入时间: {last_doc.get('timestamp')}")
        print(f"状态: {'[正常]' if count > 0 else '[警告: 无数据]'}")

    except Exception as e:
        print(f"健康检查失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    check_health()