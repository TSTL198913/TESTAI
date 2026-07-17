import httpx


def sanitize_for_mongo(data):
    """递归地清洗数据，将复杂对象转换为 BSON 可兼容格式"""
    if isinstance(data, dict):
        return {k: sanitize_for_mongo(v) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_for_mongo(item) for item in data]

    # 核心：处理 httpx.Response
    if isinstance(data, httpx.Response):
        return {
            "status_code": data.status_code,
            "url": str(data.url),
            "headers": dict(data.headers),
            "elapsed_seconds": data.elapsed.total_seconds(),
            # 如果需要 Body，请注意处理大小限制
            "text": data.text[:1000] if len(data.text) > 1000 else data.text
        }
    return data