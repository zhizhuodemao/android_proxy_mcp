"""
SQLite 流量存储

基于 SQLite 的流量存储，支持跨进程访问。
启动脚本写入，MCP 读取。
"""

import json
import sqlite3
from pathlib import Path
from threading import Lock

from .models import TrafficRecord

# 默认数据库路径
DEFAULT_DB_PATH = Path("/tmp/android-proxy-traffic.db")


class SQLiteTrafficStore:
    """
    SQLite 流量存储

    特性：
    - 跨进程访问（启动脚本写入，MCP 读取）
    - 自动清理旧记录
    - 线程安全
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH, max_size: int = 2000):
        """
        初始化 SQLite 存储

        Args:
            db_path: 数据库文件路径
            max_size: 最大存储条数
        """
        self.db_path = Path(db_path)
        self.max_size = max_size
        self._lock = Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """初始化数据库表"""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS traffic (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    method TEXT NOT NULL,
                    url TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    status INTEGER NOT NULL,
                    resource_type TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    time_ms REAL NOT NULL,
                    request_headers TEXT,
                    request_body BLOB,
                    request_body_size INTEGER DEFAULT 0,
                    response_headers TEXT,
                    response_body BLOB,
                    timing TEXT,
                    error TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON traffic(timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_domain ON traffic(domain)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON traffic(status)
            """)
            conn.commit()

    def add(self, record: TrafficRecord) -> None:
        """
        添加流量记录

        Args:
            record: 流量记录
        """
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO traffic (
                        id, timestamp, method, url, domain, status,
                        resource_type, size, time_ms, request_headers,
                        request_body, request_body_size, response_headers,
                        response_body, timing, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.id,
                    record.timestamp,
                    record.method,
                    record.url,
                    record.domain,
                    record.status,
                    record.resource_type,
                    record.size,
                    record.time_ms,
                    json.dumps(record.request_headers),
                    record.request_body,
                    record.request_body_size,
                    json.dumps(record.response_headers),
                    record.response_body,
                    json.dumps(record.timing),
                    record.error,
                ))
                conn.commit()

                # 清理旧记录
                self._cleanup(conn)

    def _cleanup(self, conn: sqlite3.Connection) -> None:
        """清理超出容量的旧记录"""
        count = conn.execute("SELECT COUNT(*) FROM traffic").fetchone()[0]
        if count > self.max_size:
            # 删除最旧的记录
            delete_count = count - self.max_size
            conn.execute("""
                DELETE FROM traffic WHERE id IN (
                    SELECT id FROM traffic ORDER BY timestamp ASC LIMIT ?
                )
            """, (delete_count,))
            conn.commit()

    def query(
        self,
        limit: int = 10,
        offset: int = 0,
        filter_domain: str | None = None,
        filter_type: str | None = None,
        filter_status: str | None = None,
        filter_url: str | None = None,
    ) -> list[TrafficRecord]:
        """
        查询流量记录

        Args:
            limit: 返回最近的 N 条，最大 10
            offset: 跳过前 N 条记录，用于分页
            filter_domain: 按域名筛选，支持通配符
            filter_type: 按资源类型筛选
            filter_status: 按状态码筛选
            filter_url: 按 URL 正则匹配

        Returns:
            匹配的流量记录列表，按时间倒序
        """
        # 限制最大返回数量为 10
        limit = min(limit, 10)

        conditions = []
        params = []

        if filter_domain:
            # 将通配符转换为 SQL LIKE 模式
            pattern = filter_domain.replace("*", "%")
            conditions.append("domain LIKE ?")
            params.append(pattern)

        if filter_type:
            conditions.append("LOWER(resource_type) = LOWER(?)")
            params.append(filter_type)

        if filter_status:
            status_condition = self._build_status_condition(filter_status)
            if status_condition:
                conditions.append(status_condition[0])
                params.extend(status_condition[1])

        if filter_url:
            # SQLite 不支持正则，使用 LIKE
            conditions.append("url LIKE ?")
            params.append(f"%{filter_url}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.extend([limit, offset])

        with self._get_conn() as conn:
            rows = conn.execute(f"""
                SELECT * FROM traffic
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, params).fetchall()

            return [self._row_to_record(row) for row in rows]

    def _build_status_condition(self, pattern: str) -> tuple[str, list] | None:
        """构建状态码查询条件"""
        pattern = pattern.strip().lower()

        # 精确匹配
        if pattern.isdigit():
            return ("status = ?", [int(pattern)])

        # 范围匹配：200-299
        if "-" in pattern:
            try:
                start, end = pattern.split("-")
                return ("status BETWEEN ? AND ?", [int(start), int(end)])
            except ValueError:
                return None

        # xx 模式：2xx, 4xx, 5xx
        if pattern.endswith("xx") and len(pattern) == 3:
            try:
                prefix = int(pattern[0])
                return ("status BETWEEN ? AND ?", [prefix * 100, prefix * 100 + 99])
            except ValueError:
                return None

        return None

    def get_by_id(self, record_id: str) -> TrafficRecord | None:
        """根据 ID 获取记录"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM traffic WHERE id = ?", (record_id,)
            ).fetchone()

            if row:
                return self._row_to_record(row)
            return None

    def clear(self) -> None:
        """清空所有记录"""
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM traffic")
                conn.commit()

    def __len__(self) -> int:
        """返回当前记录数"""
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM traffic").fetchone()[0]

    def _row_to_record(self, row: sqlite3.Row) -> TrafficRecord:
        """将数据库行转换为 TrafficRecord"""
        return TrafficRecord(
            id=row["id"],
            timestamp=row["timestamp"],
            method=row["method"],
            url=row["url"],
            domain=row["domain"],
            status=row["status"],
            resource_type=row["resource_type"],
            size=row["size"],
            time_ms=row["time_ms"],
            request_headers=json.loads(row["request_headers"] or "{}"),
            request_body=row["request_body"],
            request_body_size=row["request_body_size"] or 0,
            response_headers=json.loads(row["response_headers"] or "{}"),
            response_body=row["response_body"],
            timing=json.loads(row["timing"] or "{}"),
            error=row["error"],
        )

    def search(
        self,
        keyword: str,
        search_in: list[str] | None = None,
        method: str | None = None,
        domain: str | None = None,
        context_chars: int = 150,
        limit: int = 10,
    ) -> list[dict]:
        """
        搜索流量记录

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
            context_chars: 返回匹配内容前后字符数
            limit: 最多返回几条匹配

        Returns:
            匹配结果列表，每个元素包含 request_id, url, matched_in, snippet 等
        """
        if search_in is None or "all" in search_in:
            search_in = ["url", "request_headers", "request_body", "response_headers", "response_body"]

        # 构建基础查询条件
        base_conditions = []
        base_params = []

        if method:
            base_conditions.append("UPPER(method) = UPPER(?)")
            base_params.append(method)

        if domain:
            pattern = domain.replace("*", "%")
            base_conditions.append("domain LIKE ?")
            base_params.append(pattern)

        base_where = " AND ".join(base_conditions) if base_conditions else "1=1"

        matches = []

        with self._get_conn() as conn:
            # 对每个搜索字段进行查询
            for field in search_in:
                if field == "url":
                    sql = f"""
                        SELECT id, url, method, domain, size,
                               'url' as matched_in,
                               url as matched_content
                        FROM traffic
                        WHERE {base_where} AND url LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """
                    params = base_params + [f"%{keyword}%", limit]

                elif field == "request_headers":
                    sql = f"""
                        SELECT id, url, method, domain, size,
                               'request_headers' as matched_in,
                               request_headers as matched_content
                        FROM traffic
                        WHERE {base_where} AND request_headers LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """
                    params = base_params + [f"%{keyword}%", limit]

                elif field == "request_body":
                    sql = f"""
                        SELECT id, url, method, domain, size,
                               'request_body' as matched_in,
                               CAST(request_body AS TEXT) as matched_content,
                               LENGTH(request_body) as field_size
                        FROM traffic
                        WHERE {base_where} AND CAST(request_body AS TEXT) LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """
                    params = base_params + [f"%{keyword}%", limit]

                elif field == "response_headers":
                    sql = f"""
                        SELECT id, url, method, domain, size,
                               'response_headers' as matched_in,
                               response_headers as matched_content
                        FROM traffic
                        WHERE {base_where} AND response_headers LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """
                    params = base_params + [f"%{keyword}%", limit]

                elif field == "response_body":
                    sql = f"""
                        SELECT id, url, method, domain, size,
                               'response_body' as matched_in,
                               CAST(response_body AS TEXT) as matched_content,
                               LENGTH(response_body) as field_size
                        FROM traffic
                        WHERE {base_where} AND CAST(response_body AS TEXT) LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """
                    params = base_params + [f"%{keyword}%", limit]

                else:
                    continue

                rows = conn.execute(sql, params).fetchall()

                for row in rows:
                    matched_content = row["matched_content"] or ""
                    # sqlite3.Row doesn't have .get(), use try/except
                    try:
                        field_size = row["field_size"] or len(matched_content)
                    except (KeyError, IndexError):
                        field_size = len(matched_content)

                    # 提取片段
                    snippet = self._extract_snippet(matched_content, keyword, context_chars)

                    # 计算匹配位置
                    match_position = matched_content.lower().find(keyword.lower())

                    matches.append({
                        "request_id": row["id"],
                        "url": row["url"],
                        "method": row["method"],
                        "domain": row["domain"],
                        "response_size": row["size"],
                        "matched_in": row["matched_in"],
                        "snippet": snippet,
                        "match_position": match_position,
                        "field_size": field_size,
                    })

                    if len(matches) >= limit:
                        break

                if len(matches) >= limit:
                    break

        return matches[:limit]

    def _extract_snippet(self, content: str, keyword: str, context_chars: int) -> str:
        """提取包含关键词的片段"""
        if not content:
            return ""

        # 查找关键词位置（不区分大小写）
        lower_content = content.lower()
        lower_keyword = keyword.lower()
        pos = lower_content.find(lower_keyword)

        if pos == -1:
            return content[:context_chars * 2] + "..." if len(content) > context_chars * 2 else content

        # 计算片段范围
        start = max(0, pos - context_chars)
        end = min(len(content), pos + len(keyword) + context_chars)

        snippet = content[start:end]

        # 添加省略号
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        return snippet

    def read_body(
        self,
        request_id: str,
        field: str,
        offset: int = 0,
        length: int = 4000,
    ) -> dict | None:
        """
        分片读取请求体或响应体

        Args:
            request_id: 请求 ID
            field: 读取字段 ("request_body" | "response_body")
            offset: 起始位置
            length: 读取长度

        Returns:
            包含 content, offset, total_size, has_more 的字典
        """
        if field not in ("request_body", "response_body"):
            return None

        with self._get_conn() as conn:
            row = conn.execute(f"""
                SELECT {field}, LENGTH({field}) as total_size
                FROM traffic
                WHERE id = ?
            """, (request_id,)).fetchone()

            if not row:
                return None

            body = row[field]
            total_size = row["total_size"] or 0

            if body is None:
                return {
                    "content": "",
                    "offset": 0,
                    "length": 0,
                    "total_size": 0,
                    "has_more": False,
                }

            # 转换为字符串
            if isinstance(body, bytes):
                try:
                    body_str = body.decode("utf-8")
                except UnicodeDecodeError:
                    body_str = body.decode("latin-1")
            else:
                body_str = str(body)

            # 提取片段
            content = body_str[offset:offset + length]
            has_more = offset + length < len(body_str)

            return {
                "content": content,
                "offset": offset,
                "length": len(content),
                "total_size": len(body_str),
                "has_more": has_more,
            }

    @classmethod
    def get_default_path(cls) -> Path:
        """获取默认数据库路径"""
        return DEFAULT_DB_PATH

    @classmethod
    def exists(cls, db_path: Path | str = DEFAULT_DB_PATH) -> bool:
        """检查数据库文件是否存在"""
        return Path(db_path).exists()
