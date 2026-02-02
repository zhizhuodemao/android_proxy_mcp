"""
流量工具

提供流量查询、筛选、详情查看等功能。
从 SQLite 数据库读取流量数据。
"""

from typing import Any

from ..core.sqlite_store import SQLiteTrafficStore


def _get_store() -> SQLiteTrafficStore:
    """获取 SQLite 流量存储实例"""
    return SQLiteTrafficStore()


def traffic_list(
    limit: int = 10,
    offset: int = 0,
    filter_domain: str | None = None,
    filter_type: str | None = None,
    filter_status: str | None = None,
    filter_url: str | None = None,
) -> dict[str, Any]:
    """
    列出捕获的流量

    Args:
        limit: 返回数量限制，默认 10，最大 10
        offset: 跳过前 N 条记录，用于分页（如 offset=10 查看第 11-20 条）
        filter_domain: 按域名筛选（支持通配符，如 *.example.com）
        filter_type: 按资源类型筛选（XHR, Document, Image, Script, etc.）
        filter_status: 按状态码筛选（如 200, 4xx, 500-599）
        filter_url: 按 URL 筛选（支持正则表达式）

    Returns:
        包含流量列表的字典
    """
    store = _get_store()

    # 检查代理是否启动（数据库是否有数据或文件是否存在）
    if not SQLiteTrafficStore.exists():
        return {
            "success": False,
            "message": "代理未启动。请先运行: uv run android-proxy-start",
            "requests": [],
            "total": 0,
        }

    # 限制最大返回数量为 10
    limit = min(limit, 10)

    records = store.query(
        limit=limit,
        offset=offset,
        filter_domain=filter_domain,
        filter_type=filter_type,
        filter_status=filter_status,
        filter_url=filter_url,
    )

    store_size = len(store)

    return {
        "success": True,
        "requests": [r.to_summary() for r in records],
        "returned": len(records),
        "offset": offset,
        "store_size": store_size,
        "has_more": offset + len(records) < store_size,
    }


def traffic_get_detail(request_id: str) -> dict[str, Any]:
    """
    获取单个请求的元数据（请求头、响应头、参数等，不含大 body）

    Args:
        request_id: 请求 ID

    Returns:
        包含请求元数据的字典
    """
    store = _get_store()

    if not SQLiteTrafficStore.exists():
        return {
            "success": False,
            "message": "代理未启动。请先运行: uv run android-proxy-start",
        }

    record = store.get_by_id(request_id)

    if record is None:
        return {
            "success": False,
            "message": f"Request not found: {request_id}",
        }

    # 只返回元数据，不含大 body
    return {
        "success": True,
        "request": {
            "id": record.id,
            "timestamp": record.timestamp,
            "method": record.method,
            "url": record.url,
            "domain": record.domain,
            "status": record.status,
            "resource_type": record.resource_type,
            "response_size": record.size,
            "time_ms": record.time_ms,
            "request_headers": record.request_headers,
            "request_body_size": record.request_body_size or (len(record.request_body) if record.request_body else 0),
            "response_headers": record.response_headers,
            "response_body_size": record.size,
            "timing": record.timing,
            "error": record.error,
        },
        "hint": "使用 traffic_read_body 读取请求体或响应体内容",
    }


def traffic_search(
    keyword: str,
    search_in: list[str] | None = None,
    method: str | None = None,
    domain: str | None = None,
    context_chars: int = 150,
    limit: int = 10,
) -> dict[str, Any]:
    """
    搜索流量内容

    Args:
        keyword: 搜索关键词
        search_in: 搜索范围列表，可选值:
            - "url": URL
            - "request_headers": 请求头
            - "request_body": 请求体
            - "response_headers": 响应头
            - "response_body": 响应体
            - "all": 所有字段（默认）
        method: 限定 HTTP 方法 (GET/POST)
        domain: 限定域名（支持通配符 %）
        context_chars: 返回匹配内容前后字符数，默认 150
        limit: 最多返回几条匹配，默认 10

    Returns:
        包含匹配结果的字典，每个匹配包含 request_id, url, matched_in, snippet 等
    """
    store = _get_store()

    if not SQLiteTrafficStore.exists():
        return {
            "success": False,
            "message": "代理未启动。请先运行: uv run android-proxy-start",
            "matches": [],
        }

    matches = store.search(
        keyword=keyword,
        search_in=search_in,
        method=method,
        domain=domain,
        context_chars=context_chars,
        limit=limit,
    )

    return {
        "success": True,
        "keyword": keyword,
        "search_in": search_in or ["all"],
        "matches": matches,
        "total_matches": len(matches),
    }


def traffic_read_body(
    request_id: str,
    field: str = "response_body",
    offset: int = 0,
    length: int = 4000,
) -> dict[str, Any]:
    """
    分片读取请求体或响应体

    Args:
        request_id: 请求 ID
        field: 读取字段，可选 "request_body" 或 "response_body"（默认）
        offset: 起始位置，默认 0
        length: 读取长度，默认 4000 字符

    Returns:
        包含 content, offset, total_size, has_more 的字典
    """
    store = _get_store()

    if not SQLiteTrafficStore.exists():
        return {
            "success": False,
            "message": "代理未启动。请先运行: uv run android-proxy-start",
        }

    if field not in ("request_body", "response_body"):
        return {
            "success": False,
            "message": f"无效的字段: {field}，只支持 request_body 或 response_body",
        }

    result = store.read_body(
        request_id=request_id,
        field=field,
        offset=offset,
        length=length,
    )

    if result is None:
        return {
            "success": False,
            "message": f"Request not found: {request_id}",
        }

    return {
        "success": True,
        "request_id": request_id,
        "field": field,
        **result,
    }


def traffic_clear() -> dict[str, Any]:
    """
    清空所有捕获的流量

    Returns:
        包含清空状态的字典
    """
    store = _get_store()

    if not SQLiteTrafficStore.exists():
        return {
            "success": False,
            "message": "代理未启动。请先运行: uv run android-proxy-start",
        }

    count = len(store)
    store.clear()

    return {
        "success": True,
        "message": f"Cleared {count} requests",
        "cleared_count": count,
    }


def proxy_status() -> dict[str, Any]:
    """
    获取代理状态

    Returns:
        代理状态信息
    """
    if not SQLiteTrafficStore.exists():
        return {
            "running": False,
            "message": "代理未启动。请先运行: uv run android-proxy-start",
        }

    store = _get_store()
    return {
        "running": True,
        "message": "代理正在运行（通过 android-proxy-start 启动）",
        "traffic_count": len(store),
        "db_path": str(SQLiteTrafficStore.get_default_path()),
    }
