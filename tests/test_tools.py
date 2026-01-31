"""MCP 工具测试"""

import time
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from android_proxy_mcp.tools import traffic_tools, android_tools, proxy_tools
from android_proxy_mcp.core.models import TrafficRecord
from android_proxy_mcp.core.sqlite_store import SQLiteTrafficStore


class TestProxyTools:
    """代理工具测试"""

    def test_get_cert_info_success(self):
        """测试获取证书信息成功"""
        with patch("android_proxy_mcp.tools.proxy_tools.CertHelper") as MockHelper:
            mock_helper = MagicMock()
            mock_cert_info = MagicMock()
            mock_cert_info.pem_path = "/path/to/cert.pem"
            mock_cert_info.hash = "c8750f0d"
            mock_cert_info.filename = "c8750f0d.0"
            mock_helper.get_cert_info.return_value = mock_cert_info
            mock_helper.get_install_instructions.return_value = "Install instructions"
            MockHelper.return_value = mock_helper

            result = proxy_tools.get_cert_info()

            assert result["success"] is True
            assert result["cert_hash"] == "c8750f0d"

    def test_get_cert_info_not_found(self):
        """测试证书未找到"""
        with patch("android_proxy_mcp.tools.proxy_tools.CertHelper") as MockHelper:
            mock_helper = MagicMock()
            mock_helper.get_cert_info.side_effect = FileNotFoundError("Not found")
            mock_helper.get_install_instructions.return_value = "Start proxy first"
            MockHelper.return_value = mock_helper

            result = proxy_tools.get_cert_info()

            assert result["success"] is False
            assert "证书" in result["message"]


class TestTrafficTools:
    """流量工具测试 - 使用 SQLite"""

    def setup_method(self):
        """每个测试前创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_traffic.db"
        # 创建存储实例
        self.store = SQLiteTrafficStore(self.db_path)

    def teardown_method(self):
        """每个测试后清理"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_traffic_list_proxy_not_started(self):
        """测试代理未启动时列出流量"""
        # 使用不存在的数据库路径
        with patch.object(SQLiteTrafficStore, 'exists', return_value=False):
            result = traffic_tools.traffic_list()
            assert result["success"] is False
            assert "代理未启动" in result["message"]

    def test_traffic_list_empty(self):
        """测试空流量列表"""
        with patch.object(SQLiteTrafficStore, 'exists', return_value=True):
            with patch.object(traffic_tools, '_get_store', return_value=self.store):
                result = traffic_tools.traffic_list()

                assert result["success"] is True
                assert result["requests"] == []
                assert result["total"] == 0

    def test_traffic_list_with_records(self):
        """测试有流量时的列表"""
        record = TrafficRecord(
            id="req-1",
            timestamp=time.time(),
            method="GET",
            url="https://example.com/api",
            domain="example.com",
            status=200,
            resource_type="XHR",
            size=1024,
            time_ms=150.0,
        )

        self.store.add(record)

        with patch.object(SQLiteTrafficStore, 'exists', return_value=True):
            with patch.object(traffic_tools, '_get_store', return_value=self.store):
                result = traffic_tools.traffic_list(limit=10)

                assert result["success"] is True
                assert result["total"] == 1
                assert result["requests"][0]["id"] == "req-1"

    def test_traffic_list_with_filters(self):
        """测试带筛选的流量列表"""
        # 添加多条记录
        for i in range(5):
            record = TrafficRecord(
                id=f"req-{i}",
                timestamp=time.time(),
                method="GET",
                url=f"https://api.example.com/test{i}",
                domain="api.example.com",
                status=200,
                resource_type="XHR",
                size=1024,
                time_ms=150.0,
            )
            self.store.add(record)

        # 添加一条不同域名的记录
        other_record = TrafficRecord(
            id="req-other",
            timestamp=time.time(),
            method="GET",
            url="https://other.com/test",
            domain="other.com",
            status=404,
            resource_type="Document",
            size=512,
            time_ms=100.0,
        )
        self.store.add(other_record)

        with patch.object(SQLiteTrafficStore, 'exists', return_value=True):
            with patch.object(traffic_tools, '_get_store', return_value=self.store):
                # 按域名筛选
                result = traffic_tools.traffic_list(filter_domain="%.example.com")
                assert result["success"] is True
                assert result["total"] == 5

                # 按状态码筛选
                result = traffic_tools.traffic_list(filter_status="404")
                assert result["total"] == 1

    def test_traffic_get_detail_not_found(self):
        """测试获取不存在的请求详情"""
        with patch.object(SQLiteTrafficStore, 'exists', return_value=True):
            with patch.object(traffic_tools, '_get_store', return_value=self.store):
                result = traffic_tools.traffic_get_detail("nonexistent")

                assert result["success"] is False
                assert "not found" in result["message"].lower()

    def test_traffic_get_detail_success(self):
        """测试获取请求详情成功（只返回元数据，不含body）"""
        record = TrafficRecord(
            id="req-1",
            timestamp=time.time(),
            method="POST",
            url="https://example.com/api",
            domain="example.com",
            status=200,
            resource_type="XHR",
            size=1024,
            time_ms=150.0,
            request_headers={"Content-Type": "application/json"},
            request_body=b'{"key": "value"}',
            response_headers={"Content-Type": "application/json"},
            response_body=b'{"ok": true}',
        )

        self.store.add(record)

        with patch.object(SQLiteTrafficStore, 'exists', return_value=True):
            with patch.object(traffic_tools, '_get_store', return_value=self.store):
                result = traffic_tools.traffic_get_detail("req-1")

                assert result["success"] is True
                assert result["request"]["id"] == "req-1"
                assert result["request"]["method"] == "POST"
                assert "hint" in result  # 应该提示使用 traffic_read_body

    def test_traffic_clear(self):
        """测试清空流量"""
        # 添加一些记录
        for i in range(10):
            record = TrafficRecord(
                id=f"req-{i}",
                timestamp=time.time(),
                method="GET",
                url=f"https://example.com/test{i}",
                domain="example.com",
                status=200,
                resource_type="XHR",
                size=1024,
                time_ms=150.0,
            )
            self.store.add(record)

        assert len(self.store) == 10

        with patch.object(SQLiteTrafficStore, 'exists', return_value=True):
            with patch.object(traffic_tools, '_get_store', return_value=self.store):
                result = traffic_tools.traffic_clear()

                assert result["success"] is True
                assert result["cleared_count"] == 10
                assert len(self.store) == 0

    def test_proxy_status_not_running(self):
        """测试代理未运行时的状态"""
        with patch.object(SQLiteTrafficStore, 'exists', return_value=False):
            result = traffic_tools.proxy_status()
            assert result["running"] is False

    def test_proxy_status_running(self):
        """测试代理运行时的状态"""
        with patch.object(SQLiteTrafficStore, 'exists', return_value=True):
            with patch.object(traffic_tools, '_get_store', return_value=self.store):
                result = traffic_tools.proxy_status()
                assert result["running"] is True

    def test_traffic_search_in_response_body(self):
        """测试搜索响应体"""
        record = TrafficRecord(
            id="req-1",
            timestamp=time.time(),
            method="GET",
            url="https://api.example.com/users",
            domain="api.example.com",
            status=200,
            resource_type="XHR",
            size=1024,
            time_ms=150.0,
            response_body='{"users": [{"name": "张三", "age": 25}]}'.encode('utf-8'),
        )
        self.store.add(record)

        with patch.object(SQLiteTrafficStore, 'exists', return_value=True):
            with patch.object(traffic_tools, '_get_store', return_value=self.store):
                result = traffic_tools.traffic_search(keyword="张三", search_in=["response_body"])

                assert result["success"] is True
                assert result["total_matches"] == 1
                assert result["matches"][0]["request_id"] == "req-1"
                assert "张三" in result["matches"][0]["snippet"]

    def test_traffic_search_in_url(self):
        """测试搜索URL"""
        record = TrafficRecord(
            id="req-1",
            timestamp=time.time(),
            method="GET",
            url="https://api.example.com/search?q=phone",
            domain="api.example.com",
            status=200,
            resource_type="XHR",
            size=1024,
            time_ms=150.0,
        )
        self.store.add(record)

        with patch.object(SQLiteTrafficStore, 'exists', return_value=True):
            with patch.object(traffic_tools, '_get_store', return_value=self.store):
                result = traffic_tools.traffic_search(keyword="search", search_in=["url"])

                assert result["success"] is True
                assert result["total_matches"] == 1

    def test_traffic_read_body(self):
        """测试分片读取响应体"""
        large_body = b'{"data": "' + b'x' * 10000 + b'"}'
        record = TrafficRecord(
            id="req-1",
            timestamp=time.time(),
            method="GET",
            url="https://api.example.com/data",
            domain="api.example.com",
            status=200,
            resource_type="XHR",
            size=len(large_body),
            time_ms=150.0,
            response_body=large_body,
        )
        self.store.add(record)

        with patch.object(SQLiteTrafficStore, 'exists', return_value=True):
            with patch.object(traffic_tools, '_get_store', return_value=self.store):
                # 读取前 1000 字符
                result = traffic_tools.traffic_read_body("req-1", "response_body", offset=0, length=1000)

                assert result["success"] is True
                assert len(result["content"]) == 1000
                assert result["has_more"] is True
                assert result["total_size"] > 1000

                # 继续读取
                result2 = traffic_tools.traffic_read_body("req-1", "response_body", offset=1000, length=1000)
                assert result2["success"] is True
                assert result2["offset"] == 1000

    def test_traffic_read_body_not_found(self):
        """测试读取不存在的请求"""
        with patch.object(SQLiteTrafficStore, 'exists', return_value=True):
            with patch.object(traffic_tools, '_get_store', return_value=self.store):
                result = traffic_tools.traffic_read_body("nonexistent", "response_body")

                assert result["success"] is False
                assert "not found" in result["message"].lower()


class TestAndroidTools:
    """Android 工具测试"""

    def setup_method(self):
        """每个测试前重置全局状态"""
        android_tools._adb_client = None

    @pytest.mark.asyncio
    async def test_android_list_devices_success(self):
        """测试列出设备成功"""
        mock_device = MagicMock()
        mock_device.serial = "emulator-5554"
        mock_device.state = "device"
        mock_device.model = "sdk_phone"
        mock_device.android_version = "14"
        mock_device.is_online = True

        with patch.object(android_tools, "_get_adb") as mock_get_adb:
            mock_adb = AsyncMock()
            mock_adb.list_devices.return_value = [mock_device]
            mock_get_adb.return_value = mock_adb

            result = await android_tools.android_list_devices()

            assert result["success"] is True
            assert result["count"] == 1
            assert result["devices"][0]["serial"] == "emulator-5554"

    @pytest.mark.asyncio
    async def test_android_list_devices_adb_error(self):
        """测试 ADB 错误"""
        from android_proxy_mcp.android.adb_client import ADBError

        with patch.object(android_tools, "_get_adb") as mock_get_adb:
            mock_adb = AsyncMock()
            mock_adb.list_devices.side_effect = ADBError("ADB not found")
            mock_get_adb.return_value = mock_adb

            result = await android_tools.android_list_devices()

            assert result["success"] is False
            assert "ADB" in result["message"]

    @pytest.mark.asyncio
    async def test_android_get_device_info_not_found(self):
        """测试设备未找到"""
        with patch.object(android_tools, "_get_adb") as mock_get_adb:
            mock_adb = AsyncMock()
            mock_adb.list_devices.return_value = []
            mock_get_adb.return_value = mock_adb

            result = await android_tools.android_get_device_info("nonexistent")

            assert result["success"] is False
            assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_android_get_device_info_success(self):
        """测试获取设备信息成功"""
        mock_device = MagicMock()
        mock_device.serial = "emulator-5554"
        mock_device.state = "device"
        mock_device.model = "sdk_phone"
        mock_device.android_version = "14"
        mock_device.is_online = True

        with patch.object(android_tools, "_get_adb") as mock_get_adb:
            mock_adb = AsyncMock()
            mock_adb.list_devices.return_value = [mock_device]
            mock_adb.get_android_version.return_value = 34
            mock_adb.is_rooted.return_value = False
            mock_adb.get_prop.side_effect = lambda s, p: {
                "ro.product.brand": "Google",
                "ro.product.device": "sdk_phone",
                "ro.build.id": "ABC123",
            }.get(p)
            mock_get_adb.return_value = mock_adb

            result = await android_tools.android_get_device_info("emulator-5554")

            assert result["success"] is True
            assert result["device"]["serial"] == "emulator-5554"
            assert result["device"]["sdk_version"] == 34
            assert result["device"]["is_rooted"] is False

    @pytest.mark.asyncio
    async def test_android_setup_proxy(self):
        """测试设置代理"""
        with patch.object(android_tools, "_get_adb") as mock_get_adb:
            mock_adb = AsyncMock()
            mock_adb.shell.return_value = (0, "")
            mock_get_adb.return_value = mock_adb

            result = await android_tools.android_setup_proxy(
                "device1", "192.168.1.100", 8080
            )

            assert result["success"] is True
            mock_adb.shell.assert_called_once()

    @pytest.mark.asyncio
    async def test_android_clear_proxy(self):
        """测试清除代理"""
        with patch.object(android_tools, "_get_adb") as mock_get_adb:
            mock_adb = AsyncMock()
            mock_adb.shell.return_value = (0, "")
            mock_get_adb.return_value = mock_adb

            result = await android_tools.android_clear_proxy("device1")

            assert result["success"] is True
