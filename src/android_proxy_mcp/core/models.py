"""
数据模型定义

定义流量记录的数据结构，对标 Chrome DevTools Protocol 的 Network 域。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrafficRecord:
    """
    单条流量记录

    字段设计对标 CDP Network.Request 和 Network.Response 结构。
    """

    # 基础标识
    id: str
    timestamp: float  # Unix 时间戳（秒）

    # 请求信息
    method: str  # HTTP 方法: GET, POST, PUT, DELETE 等
    url: str  # 完整 URL
    domain: str  # 从 URL 提取的域名

    # 响应信息
    status: int  # HTTP 状态码
    resource_type: str  # CDP ResourceType: Document, XHR, Image 等

    # 统计信息
    size: int  # 响应体大小（字节）
    time_ms: float  # 总耗时（毫秒）

    # 详细数据（可选，用于 get_details 接口）
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: bytes | None = None
    request_body_size: int = 0

    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: bytes | None = None

    # CDP 风格的 Timing 信息
    timing: dict[str, float] = field(default_factory=dict)

    # 额外元数据
    error: str | None = None  # 如果请求失败，记录错误信息

    def to_summary(self) -> dict[str, Any]:
        """
        转换为摘要格式（用于列表展示，不含 Body）

        对应 traffic_list_requests 的返回格式。
        """
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "method": self.method,
            "url": self.url,
            "domain": self.domain,
            "status": self.status,
            "type": self.resource_type,
            "size": self.size,
            "time": self.time_ms,
            "error": self.error,
        }

    def to_detail(self) -> dict[str, Any]:
        """
        转换为详情格式（包含完整 Header 和 Body）

        对应 traffic_get_details 的返回格式，兼容 CDP 结构。
        """
        from ..utils.encoding import encode_body

        # 编码请求体
        request_body_encoded = ""
        request_body_base64 = False
        if self.request_body:
            content_type = self.request_headers.get(
                "Content-Type", self.request_headers.get("content-type", "")
            )
            request_body_encoded, request_body_base64 = encode_body(
                self.request_body, content_type
            )

        # 编码响应体
        response_body_encoded = ""
        response_body_base64 = False
        if self.response_body:
            content_type = self.response_headers.get(
                "Content-Type", self.response_headers.get("content-type", "")
            )
            response_body_encoded, response_body_base64 = encode_body(
                self.response_body, content_type
            )

        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "request": {
                "method": self.method,
                "url": self.url,
                "headers": self.request_headers,
                "postData": request_body_encoded,
                "postDataBase64Encoded": request_body_base64,
            },
            "response": {
                "status": self.status,
                "headers": self.response_headers,
                "body": response_body_encoded,
                "base64Encoded": response_body_base64,
                "mimeType": self._extract_mime_type(),
            },
            "resourceType": self.resource_type,
            "timing": self.timing,
            "size": self.size,
            "time": self.time_ms,
            "error": self.error,
        }

    def _extract_mime_type(self) -> str:
        """从响应头提取 MIME 类型"""
        content_type = self.response_headers.get(
            "Content-Type", self.response_headers.get("content-type", "")
        )
        # 去除 charset 等参数
        return content_type.split(";")[0].strip() if content_type else ""
