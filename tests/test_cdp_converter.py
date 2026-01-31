"""CDP 转换器测试"""

from unittest.mock import MagicMock, PropertyMock

import pytest

from android_proxy_mcp.core.cdp_converter import CDPConverter


def create_mock_flow(
    url: str = "https://api.example.com/data",
    method: str = "GET",
    status: int = 200,
    request_headers: dict | None = None,
    response_headers: dict | None = None,
    request_content: bytes = b"",
    response_content: bytes = b'{"ok": true}',
    timestamp_start: float = 1000.0,
    timestamp_end: float = 1000.1,
    response_timestamp_start: float = 1000.2,
    response_timestamp_end: float = 1000.3,
    error: str | None = None,
) -> MagicMock:
    """创建模拟的 mitmproxy HTTPFlow 对象"""
    flow = MagicMock()

    # 请求对象
    flow.request.pretty_url = url
    flow.request.method = method
    flow.request.headers = request_headers or {"User-Agent": "Test/1.0"}
    flow.request.content = request_content
    flow.request.timestamp_start = timestamp_start
    flow.request.timestamp_end = timestamp_end

    # 响应对象
    flow.response.status_code = status
    flow.response.headers = response_headers or {"Content-Type": "application/json"}
    flow.response.content = response_content
    flow.response.timestamp_start = response_timestamp_start
    flow.response.timestamp_end = response_timestamp_end

    # 错误
    flow.error = error

    return flow


def create_mock_flow_no_response(
    url: str = "https://api.example.com/timeout",
    method: str = "GET",
    request_headers: dict | None = None,
    timestamp_start: float = 1000.0,
    timestamp_end: float = 1000.1,
    error: str = "Connection timeout",
) -> MagicMock:
    """创建没有响应的模拟 Flow（如超时、连接失败）"""
    flow = MagicMock()

    flow.request.pretty_url = url
    flow.request.method = method
    flow.request.headers = request_headers or {"User-Agent": "Test/1.0"}
    flow.request.content = b""
    flow.request.timestamp_start = timestamp_start
    flow.request.timestamp_end = timestamp_end

    flow.response = None
    flow.error = error

    return flow


class TestCDPConverterBasic:
    """基础转换测试"""

    def test_basic_conversion(self):
        """测试基本的 Flow 转换"""
        flow = create_mock_flow()
        record = CDPConverter.flow_to_record(flow, "test-1")

        assert record.id == "test-1"
        assert record.method == "GET"
        assert record.url == "https://api.example.com/data"
        assert record.domain == "api.example.com"
        assert record.status == 200
        assert record.resource_type == "XHR"  # JSON 应该被识别为 XHR

    def test_post_request(self):
        """测试 POST 请求转换"""
        flow = create_mock_flow(
            method="POST",
            request_content=b'{"username": "test"}',
            request_headers={"Content-Type": "application/json"},
        )
        record = CDPConverter.flow_to_record(flow, "post-1")

        assert record.method == "POST"
        assert record.request_body == b'{"username": "test"}'
        assert record.request_body_size == len(b'{"username": "test"}')

    def test_response_body(self):
        """测试响应体提取"""
        flow = create_mock_flow(response_content=b'{"data": [1, 2, 3]}')
        record = CDPConverter.flow_to_record(flow, "resp-1")

        assert record.response_body == b'{"data": [1, 2, 3]}'
        assert record.size == len(b'{"data": [1, 2, 3]}')

    def test_headers_extraction(self):
        """测试请求头和响应头提取"""
        flow = create_mock_flow(
            request_headers={
                "User-Agent": "TestApp/1.0",
                "Authorization": "Bearer token123",
            },
            response_headers={
                "Content-Type": "application/json",
                "X-Request-Id": "abc-123",
            },
        )
        record = CDPConverter.flow_to_record(flow, "headers-1")

        assert record.request_headers["User-Agent"] == "TestApp/1.0"
        assert record.request_headers["Authorization"] == "Bearer token123"
        assert record.response_headers["Content-Type"] == "application/json"
        assert record.response_headers["X-Request-Id"] == "abc-123"

    def test_error_flow(self):
        """测试带错误的 Flow 转换"""
        flow = create_mock_flow_no_response(error="Connection refused")
        record = CDPConverter.flow_to_record(flow, "error-1")

        assert record.status == 0
        assert record.error == "Connection refused"
        assert record.response_body is None


class TestCDPConverterResourceTypes:
    """资源类型推断测试"""

    def test_json_is_xhr(self):
        """测试 JSON 响应识别为 XHR"""
        flow = create_mock_flow(
            response_headers={"Content-Type": "application/json"}
        )
        record = CDPConverter.flow_to_record(flow, "json-1")
        assert record.resource_type == "XHR"

    def test_html_is_document(self):
        """测试 HTML 响应识别为 Document"""
        flow = create_mock_flow(
            url="https://example.com/index.html",
            response_headers={"Content-Type": "text/html; charset=utf-8"},
            response_content=b"<html></html>",
        )
        record = CDPConverter.flow_to_record(flow, "html-1")
        assert record.resource_type == "Document"

    def test_image_type(self):
        """测试图片识别"""
        flow = create_mock_flow(
            url="https://cdn.example.com/logo.png",
            response_headers={"Content-Type": "image/png"},
            response_content=b"\x89PNG\r\n",
        )
        record = CDPConverter.flow_to_record(flow, "img-1")
        assert record.resource_type == "Image"

    def test_javascript_is_script(self):
        """测试 JavaScript 识别为 Script"""
        flow = create_mock_flow(
            url="https://cdn.example.com/app.js",
            response_headers={"Content-Type": "application/javascript"},
            response_content=b"console.log('hello');",
        )
        record = CDPConverter.flow_to_record(flow, "js-1")
        assert record.resource_type == "Script"

    def test_css_is_stylesheet(self):
        """测试 CSS 识别为 Stylesheet"""
        flow = create_mock_flow(
            url="https://cdn.example.com/style.css",
            response_headers={"Content-Type": "text/css"},
            response_content=b"body { color: red; }",
        )
        record = CDPConverter.flow_to_record(flow, "css-1")
        assert record.resource_type == "Stylesheet"


class TestCDPConverterTiming:
    """时序计算测试"""

    def test_timing_calculation(self):
        """测试时序计算"""
        flow = create_mock_flow(
            timestamp_start=1000.0,
            timestamp_end=1000.1,  # 发送耗时 100ms
            response_timestamp_start=1000.2,  # TTFB 100ms
            response_timestamp_end=1000.5,  # 下载耗时 300ms
        )
        record = CDPConverter.flow_to_record(flow, "timing-1")

        timing = record.timing

        assert "requestTime" in timing
        assert timing["requestTime"] == 1000.0

        # sendEnd 应该是 100ms
        assert abs(timing.get("sendEnd", 0) - 100) < 1

        # 总耗时应该是 500ms
        assert abs(timing.get("total", 0) - 500) < 1

    def test_timing_with_no_response(self):
        """测试无响应时的时序计算"""
        flow = create_mock_flow_no_response(
            timestamp_start=1000.0,
            timestamp_end=1000.1,
        )
        record = CDPConverter.flow_to_record(flow, "timeout-1")

        timing = record.timing

        # 应该只有请求相关的时序
        assert "requestTime" in timing
        assert abs(timing.get("total", 0) - 100) < 1  # 只有发送时间，允许浮点误差

    def test_time_ms_field(self):
        """测试 time_ms 字段"""
        flow = create_mock_flow(
            timestamp_start=1000.0,
            response_timestamp_end=1000.5,
        )
        record = CDPConverter.flow_to_record(flow, "time-1")

        # time_ms 应该等于 timing['total']
        assert abs(record.time_ms - 500) < 1


class TestCDPConverterDomain:
    """域名提取测试"""

    def test_extract_domain_simple(self):
        """测试简单域名提取"""
        assert CDPConverter.extract_domain("https://api.example.com/path") == "api.example.com"

    def test_extract_domain_with_port(self):
        """测试带端口的域名提取"""
        assert CDPConverter.extract_domain("http://localhost:8080/api") == "localhost"

    def test_extract_domain_subdomain(self):
        """测试子域名提取"""
        assert CDPConverter.extract_domain("https://sub.domain.co.uk/path") == "sub.domain.co.uk"

    def test_extract_domain_ip(self):
        """测试 IP 地址"""
        assert CDPConverter.extract_domain("http://192.168.1.1:8080/api") == "192.168.1.1"

    def test_extract_domain_invalid(self):
        """测试无效 URL"""
        assert CDPConverter.extract_domain("not-a-url") == ""


class TestCDPConverterHelpers:
    """辅助方法测试"""

    def test_headers_to_list(self):
        """测试 headers 转换为 CDP 列表格式"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token",
        }

        result = CDPConverter.headers_to_list(headers)

        assert len(result) == 2
        assert {"name": "Content-Type", "value": "application/json"} in result
        assert {"name": "Authorization", "value": "Bearer token"} in result

    def test_headers_to_list_empty(self):
        """测试空 headers 转换"""
        result = CDPConverter.headers_to_list({})
        assert result == []
