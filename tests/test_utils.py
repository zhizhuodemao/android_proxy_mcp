"""工具函数测试"""

import pytest
from android_proxy_mcp.utils.mime_types import infer_resource_type
from android_proxy_mcp.utils.cert_utils import calculate_cert_hash, get_cert_filename
from android_proxy_mcp.utils.encoding import is_binary_content, encode_body


class TestMimeTypes:
    """MIME 类型推断测试"""

    def test_html_is_document(self):
        assert infer_resource_type("text/html", "/index.html", {}) == "Document"

    def test_html_with_charset_is_document(self):
        assert infer_resource_type("text/html; charset=utf-8", "/page", {}) == "Document"

    def test_json_is_xhr(self):
        assert infer_resource_type("application/json", "/api/data", {}) == "XHR"

    def test_xml_is_xhr(self):
        assert infer_resource_type("application/xml", "/api/data.xml", {}) == "XHR"
        assert infer_resource_type("text/xml", "/feed.xml", {}) == "XHR"

    def test_image_types(self):
        assert infer_resource_type("image/png", "/logo.png", {}) == "Image"
        assert infer_resource_type("image/jpeg", "/photo.jpg", {}) == "Image"
        assert infer_resource_type("image/gif", "/animation.gif", {}) == "Image"
        assert infer_resource_type("image/webp", "/modern.webp", {}) == "Image"
        assert infer_resource_type("image/svg+xml", "/icon.svg", {}) == "Image"

    def test_image_by_extension(self):
        # 即使没有 MIME 类型，通过扩展名也能识别
        assert infer_resource_type("", "/logo.png", {}) == "Image"
        assert infer_resource_type("application/octet-stream", "/photo.jpg", {}) == "Image"

    def test_script_types(self):
        assert infer_resource_type("application/javascript", "/app.js", {}) == "Script"
        assert infer_resource_type("text/javascript", "/lib.js", {}) == "Script"
        assert infer_resource_type("application/x-javascript", "/old.js", {}) == "Script"

    def test_script_by_extension(self):
        assert infer_resource_type("", "/bundle.js", {}) == "Script"
        assert infer_resource_type("", "/module.mjs", {}) == "Script"

    def test_css_is_stylesheet(self):
        assert infer_resource_type("text/css", "/style.css", {}) == "Stylesheet"
        assert infer_resource_type("", "/theme.css", {}) == "Stylesheet"

    def test_font_types(self):
        assert infer_resource_type("font/woff2", "/font.woff2", {}) == "Font"
        assert infer_resource_type("font/woff", "/font.woff", {}) == "Font"
        assert infer_resource_type("application/font-woff", "/font.woff", {}) == "Font"
        assert infer_resource_type("", "/font.ttf", {}) == "Font"

    def test_media_types(self):
        assert infer_resource_type("video/mp4", "/video.mp4", {}) == "Media"
        assert infer_resource_type("audio/mpeg", "/song.mp3", {}) == "Media"
        assert infer_resource_type("video/webm", "/clip.webm", {}) == "Media"

    def test_websocket_upgrade(self):
        headers = {"Upgrade": "websocket"}
        assert infer_resource_type("", "/ws", headers) == "WebSocket"

    def test_xhr_header(self):
        headers = {"X-Requested-With": "XMLHttpRequest"}
        assert infer_resource_type("text/plain", "/api/data", headers) == "XHR"

    def test_unknown_is_other(self):
        assert infer_resource_type("application/octet-stream", "/file.bin", {}) == "Other"
        assert infer_resource_type("", "/unknown", {}) == "Other"


class TestCertUtils:
    """证书工具测试"""

    @pytest.fixture
    def mitmproxy_cert(self):
        """获取或生成 mitmproxy CA 证书"""
        from pathlib import Path

        # mitmproxy 默认证书位置
        default_path = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"

        if default_path.exists():
            return default_path.read_bytes()

        # 如果不存在，使用 mitmproxy 的 certs 模块生成
        from mitmproxy import certs

        # 创建临时目录存放证书
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        certs.CertStore.from_store(str(temp_dir), "mitmproxy", 2048)

        cert_path = temp_dir / "mitmproxy-ca-cert.pem"
        return cert_path.read_bytes()

    def test_cert_hash_format(self, mitmproxy_cert):
        """测试证书 hash 格式"""
        hash_value = calculate_cert_hash(mitmproxy_cert)
        # 应该是 8 位十六进制
        assert len(hash_value) == 8
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_cert_hash_consistency(self, mitmproxy_cert):
        """测试同一证书的 hash 应该一致"""
        hash1 = calculate_cert_hash(mitmproxy_cert)
        hash2 = calculate_cert_hash(mitmproxy_cert)
        assert hash1 == hash2

    def test_cert_hash_accepts_string(self, mitmproxy_cert):
        """测试接受字符串输入"""
        hash_value = calculate_cert_hash(mitmproxy_cert.decode("utf-8"))
        assert len(hash_value) == 8

    def test_get_cert_filename(self, mitmproxy_cert):
        """测试获取证书文件名"""
        filename = get_cert_filename(mitmproxy_cert)
        assert filename.endswith(".0")
        assert len(filename) == 10  # 8位hash + ".0"

    def test_get_cert_filename_with_index(self, mitmproxy_cert):
        """测试带索引的证书文件名"""
        filename = get_cert_filename(mitmproxy_cert, index=1)
        assert filename.endswith(".1")


class TestEncoding:
    """编码处理测试"""

    def test_text_not_binary(self):
        """纯文本不应被判定为二进制"""
        assert not is_binary_content(b"Hello World", "text/plain")
        assert not is_binary_content(b"<html></html>", "text/html")

    def test_json_not_binary(self):
        """JSON 不应被判定为二进制"""
        assert not is_binary_content(b'{"key": "value"}', "application/json")

    def test_null_bytes_is_binary(self):
        """包含空字节的内容应被判定为二进制"""
        assert is_binary_content(b"Hello\x00World", "text/plain")

    def test_image_is_binary(self):
        """图片应被判定为二进制"""
        # PNG 文件头
        assert is_binary_content(b"\x89PNG\r\n\x1a\n", "image/png")

    def test_binary_mime_is_binary(self):
        """二进制 MIME 类型应被判定为二进制"""
        assert is_binary_content(b"any content", "application/octet-stream")
        assert is_binary_content(b"any content", "application/zip")
        assert is_binary_content(b"any content", "image/jpeg")

    def test_encode_text(self):
        """文本应直接返回，不编码"""
        body, is_base64 = encode_body(b"Hello World", "text/plain")
        assert body == "Hello World"
        assert is_base64 is False

    def test_encode_json(self):
        """JSON 应直接返回"""
        body, is_base64 = encode_body(b'{"ok": true}', "application/json")
        assert body == '{"ok": true}'
        assert is_base64 is False

    def test_encode_binary(self):
        """二进制内容应使用 Base64 编码"""
        data = b"\x89PNG\r\n\x1a\n"
        body, is_base64 = encode_body(data, "image/png")
        assert is_base64 is True
        # 验证可以解码回原始数据
        import base64
        assert base64.b64decode(body) == data

    def test_encode_empty(self):
        """空内容应返回空字符串"""
        body, is_base64 = encode_body(b"", "text/plain")
        assert body == ""
        assert is_base64 is False

    def test_encode_utf8(self):
        """UTF-8 文本应正确解码"""
        body, is_base64 = encode_body("你好世界".encode("utf-8"), "text/plain; charset=utf-8")
        assert body == "你好世界"
        assert is_base64 is False

    def test_encode_with_charset(self):
        """应尊重 Content-Type 中指定的编码"""
        # GBK 编码的中文
        data = "你好".encode("gbk")
        body, is_base64 = encode_body(data, "text/plain; charset=gbk")
        assert body == "你好"
        assert is_base64 is False

    def test_encode_fallback_latin1(self):
        """无法解码时应回退到 Latin-1"""
        # Latin-1 字符
        data = b"\xe0\xe1\xe2"  # à á â
        body, is_base64 = encode_body(data, "text/plain")
        assert is_base64 is False
        assert body == "àáâ"
