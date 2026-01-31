"""
CDP 转换器

将 mitmproxy 的 HTTPFlow 对象转换为项目的 TrafficRecord 格式。
对标 Chrome DevTools Protocol 的 Network 域数据结构。
"""

from urllib.parse import urlparse

from mitmproxy.http import HTTPFlow

from ..utils.mime_types import infer_resource_type
from .models import TrafficRecord


class CDPConverter:
    """
    CDP 格式转换器

    将 mitmproxy 的 Flow 对象转换为对标 Chrome DevTools Protocol 的数据结构。
    """

    @staticmethod
    def flow_to_record(flow: HTTPFlow, record_id: str) -> TrafficRecord:
        """
        将 mitmproxy HTTPFlow 转换为 TrafficRecord

        Args:
            flow: mitmproxy 的 HTTPFlow 对象
            record_id: 分配给这条记录的唯一 ID

        Returns:
            TrafficRecord 实例
        """
        request = flow.request
        response = flow.response

        # 提取基础信息
        url = request.pretty_url
        domain = CDPConverter.extract_domain(url)
        method = request.method

        # 提取请求头（转换为普通字典）
        request_headers = dict(request.headers)

        # 提取响应信息
        status = response.status_code if response else 0
        response_headers = dict(response.headers) if response else {}

        # 获取 Content-Type
        content_type = ""
        if response:
            content_type = response.headers.get("Content-Type", "")

        # 推断资源类型
        resource_type = infer_resource_type(content_type, url, request_headers)

        # 计算大小
        response_body = response.content if response else None
        size = len(response_body) if response_body else 0

        # 计算时序
        timing = CDPConverter.calculate_timing(flow)
        time_ms = timing.get("total", 0)

        # 请求体
        request_body = request.content if request.content else None
        request_body_size = len(request_body) if request_body else 0

        return TrafficRecord(
            id=record_id,
            timestamp=request.timestamp_start,
            method=method,
            url=url,
            domain=domain,
            status=status,
            resource_type=resource_type,
            size=size,
            time_ms=time_ms,
            request_headers=request_headers,
            request_body=request_body,
            request_body_size=request_body_size,
            response_headers=response_headers,
            response_body=response_body,
            timing=timing,
            error=str(flow.error) if flow.error else None,
        )

    @staticmethod
    def extract_domain(url: str) -> str:
        """
        从 URL 中提取域名

        Args:
            url: 完整的 URL

        Returns:
            域名字符串
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc.split(":")[0]  # 去除端口号
        except Exception:
            return ""

    @staticmethod
    def calculate_timing(flow: HTTPFlow) -> dict[str, float]:
        """
        计算 CDP 风格的 Timing 结构

        基于 mitmproxy 提供的时间戳计算各阶段耗时。

        Args:
            flow: mitmproxy 的 HTTPFlow 对象

        Returns:
            Timing 字典，包含各阶段耗时（毫秒）
        """
        request = flow.request
        response = flow.response

        timing: dict[str, float] = {}

        # 请求开始时间（作为基准）
        request_start = request.timestamp_start
        timing["requestTime"] = request_start

        # 发送阶段
        if request.timestamp_end:
            send_duration = (request.timestamp_end - request_start) * 1000
            timing["sendStart"] = 0  # 相对于 requestTime
            timing["sendEnd"] = send_duration

        # 等待响应（TTFB）
        if response and response.timestamp_start and request.timestamp_end:
            wait_duration = (response.timestamp_start - request.timestamp_end) * 1000
            timing["receiveHeadersEnd"] = timing.get("sendEnd", 0) + wait_duration

        # 下载阶段
        if response and response.timestamp_end and response.timestamp_start:
            download_duration = (response.timestamp_end - response.timestamp_start) * 1000
            timing["responseTime"] = download_duration

        # 总耗时
        if response and response.timestamp_end:
            total = (response.timestamp_end - request_start) * 1000
            timing["total"] = total
        elif request.timestamp_end:
            # 没有响应时，只计算请求时间
            timing["total"] = (request.timestamp_end - request_start) * 1000
        else:
            timing["total"] = 0

        return timing

    @staticmethod
    def headers_to_list(headers: dict[str, str]) -> list[dict[str, str]]:
        """
        将 headers 字典转换为 CDP 格式的列表

        CDP 的 headers 格式是 [{name, value}, ...]

        Args:
            headers: 请求或响应头字典

        Returns:
            CDP 格式的 headers 列表
        """
        return [{"name": k, "value": v} for k, v in headers.items()]
