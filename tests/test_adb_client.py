"""ADB 客户端测试"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from android_proxy_mcp.android.adb_client import ADBClient, ADBError, DeviceInfo


class TestDeviceInfo:
    """设备信息测试"""

    def test_device_info_online(self):
        """测试在线设备"""
        device = DeviceInfo(serial="emulator-5554", state="device")
        assert device.is_online is True

    def test_device_info_offline(self):
        """测试离线设备"""
        device = DeviceInfo(serial="emulator-5554", state="offline")
        assert device.is_online is False

    def test_device_info_unauthorized(self):
        """测试未授权设备"""
        device = DeviceInfo(serial="RF8M33XXXXX", state="unauthorized")
        assert device.is_online is False

    def test_device_info_with_model(self):
        """测试带型号的设备信息"""
        device = DeviceInfo(
            serial="RF8M33XXXXX",
            state="device",
            model="SM-G970F",
            android_version="11",
        )
        assert device.model == "SM-G970F"
        assert device.android_version == "11"


class TestADBClientInit:
    """ADB 客户端初始化测试"""

    def test_init_with_path(self):
        """测试指定路径初始化"""
        with patch("shutil.which", return_value="/usr/bin/adb"):
            client = ADBClient(adb_path="/custom/adb")
            assert client.adb_path == "/custom/adb"

    def test_init_from_path(self):
        """测试从 PATH 查找 ADB"""
        with patch("shutil.which", return_value="/usr/bin/adb"):
            client = ADBClient()
            assert client.adb_path == "/usr/bin/adb"

    def test_init_adb_not_found(self):
        """测试 ADB 未找到"""
        with patch("shutil.which", return_value=None):
            with pytest.raises(ADBError, match="ADB not found"):
                ADBClient()


class TestADBClientMocked:
    """ADB 客户端模拟测试"""

    @pytest.fixture
    def mock_client(self):
        """创建模拟的 ADB 客户端"""
        with patch("shutil.which", return_value="/usr/bin/adb"):
            return ADBClient()

    @pytest.mark.asyncio
    async def test_list_devices_parsing(self, mock_client):
        """测试设备列表解析"""
        mock_output = (
            "List of devices attached\n"
            "emulator-5554\tdevice product:sdk_gphone64_arm64 model:sdk_gphone64_arm64 device:emu64a transport_id:1\n"
            "RF8M33XXXXX\tdevice product:beyond1q model:SM_G970F device:beyond1 transport_id:2\n"
        )

        async def mock_run(*args, **kwargs):
            if args[0] == "devices":
                return (0, mock_output, "")
            elif args[0] == "-s" and "getprop" in args:
                return (0, "11", "")
            return (0, "", "")

        with patch.object(mock_client, "_run_command", side_effect=mock_run):
            devices = await mock_client.list_devices()

            assert len(devices) == 2
            assert devices[0].serial == "emulator-5554"
            assert devices[0].state == "device"
            assert devices[0].model == "sdk_gphone64_arm64"
            assert devices[1].serial == "RF8M33XXXXX"
            assert devices[1].model == "SM_G970F"

    @pytest.mark.asyncio
    async def test_list_devices_empty(self, mock_client):
        """测试空设备列表"""
        mock_output = "List of devices attached\n"

        with patch.object(
            mock_client,
            "_run_command",
            return_value=(0, mock_output, ""),
        ):
            devices = await mock_client.list_devices()
            assert len(devices) == 0

    @pytest.mark.asyncio
    async def test_list_devices_with_unauthorized(self, mock_client):
        """测试包含未授权设备的列表"""
        mock_output = (
            "List of devices attached\n"
            "emulator-5554\tdevice\n"
            "RF8M33XXXXX\tunauthorized\n"
        )

        async def mock_run(*args, **kwargs):
            if args[0] == "devices":
                return (0, mock_output, "")
            elif "getprop" in args:
                return (0, "11", "")
            return (0, "", "")

        with patch.object(mock_client, "_run_command", side_effect=mock_run):
            devices = await mock_client.list_devices()

            assert len(devices) == 2
            assert devices[0].is_online is True
            assert devices[1].is_online is False
            assert devices[1].state == "unauthorized"

    @pytest.mark.asyncio
    async def test_shell_command(self, mock_client):
        """测试 shell 命令执行"""
        with patch.object(
            mock_client,
            "_run_command",
            return_value=(0, "Hello World", ""),
        ):
            code, output = await mock_client.shell("device1", "echo Hello World")

            assert code == 0
            assert output == "Hello World"

    @pytest.mark.asyncio
    async def test_shell_with_exit_code(self, mock_client):
        """测试带退出码的 shell 命令"""
        with patch.object(
            mock_client,
            "_run_command",
            return_value=(0, "some output\n__EXIT_CODE__0", ""),
        ):
            code, output = await mock_client.shell_with_exit_code(
                "device1", "some_command"
            )

            assert code == 0
            assert output == "some output"

    @pytest.mark.asyncio
    async def test_shell_with_exit_code_failure(self, mock_client):
        """测试失败的 shell 命令"""
        with patch.object(
            mock_client,
            "_run_command",
            return_value=(0, "error: file not found\n__EXIT_CODE__1", ""),
        ):
            code, output = await mock_client.shell_with_exit_code("device1", "cat /nonexistent")

            assert code == 1
            assert "file not found" in output

    @pytest.mark.asyncio
    async def test_get_prop(self, mock_client):
        """测试获取属性"""
        with patch.object(
            mock_client,
            "_run_command",
            return_value=(0, "14", ""),
        ):
            value = await mock_client.get_prop("device1", "ro.build.version.release")
            assert value == "14"

    @pytest.mark.asyncio
    async def test_get_prop_empty(self, mock_client):
        """测试获取不存在的属性"""
        with patch.object(
            mock_client,
            "_run_command",
            return_value=(0, "", ""),
        ):
            value = await mock_client.get_prop("device1", "nonexistent.prop")
            assert value is None

    @pytest.mark.asyncio
    async def test_is_rooted_true(self, mock_client):
        """测试已 root 设备"""
        call_count = [0]

        async def mock_shell(serial, cmd, timeout=30.0):
            call_count[0] += 1
            if "su -c id" in cmd:
                return (0, "uid=0(root) gid=0(root)")
            return (1, "")

        with patch.object(mock_client, "shell_with_exit_code", side_effect=mock_shell):
            with patch.object(mock_client, "shell", return_value=(1, "")):
                result = await mock_client.is_rooted("device1")
                assert result is True

    @pytest.mark.asyncio
    async def test_is_rooted_false(self, mock_client):
        """测试未 root 设备"""
        async def mock_shell_exit(*args, **kwargs):
            return (1, "su: not found")

        async def mock_shell(*args, **kwargs):
            return (1, "")

        with patch.object(mock_client, "shell_with_exit_code", side_effect=mock_shell_exit):
            with patch.object(mock_client, "shell", side_effect=mock_shell):
                result = await mock_client.is_rooted("device1")
                assert result is False

    @pytest.mark.asyncio
    async def test_get_android_version(self, mock_client):
        """测试获取 Android 版本"""
        with patch.object(mock_client, "get_prop", return_value="34"):
            version = await mock_client.get_android_version("device1")
            assert version == 34

    @pytest.mark.asyncio
    async def test_get_android_version_invalid(self, mock_client):
        """测试无效的 Android 版本"""
        with patch.object(mock_client, "get_prop", return_value="invalid"):
            version = await mock_client.get_android_version("device1")
            assert version == 0

    @pytest.mark.asyncio
    async def test_push_success(self, mock_client):
        """测试推送文件成功"""
        with patch("pathlib.Path.exists", return_value=True):
            with patch.object(
                mock_client,
                "_run_command",
                return_value=(0, "/sdcard/test.txt: 1 file pushed", ""),
            ):
                result = await mock_client.push(
                    "device1", "/local/test.txt", "/sdcard/test.txt"
                )
                assert result is True

    @pytest.mark.asyncio
    async def test_push_local_not_found(self, mock_client):
        """测试推送本地文件不存在"""
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(ADBError, match="Local file not found"):
                await mock_client.push(
                    "device1", "/nonexistent.txt", "/sdcard/test.txt"
                )

    @pytest.mark.asyncio
    async def test_pull_success(self, mock_client):
        """测试拉取文件成功"""
        with patch.object(
            mock_client,
            "_run_command",
            return_value=(0, "/sdcard/test.txt: 1 file pulled", ""),
        ):
            result = await mock_client.pull(
                "device1", "/sdcard/test.txt", "/local/test.txt"
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_pull_failure(self, mock_client):
        """测试拉取文件失败"""
        with patch.object(
            mock_client,
            "_run_command",
            return_value=(1, "", "remote object '/nonexistent' does not exist"),
        ):
            with pytest.raises(ADBError, match="does not exist"):
                await mock_client.pull(
                    "device1", "/nonexistent", "/local/test.txt"
                )

    @pytest.mark.asyncio
    async def test_forward(self, mock_client):
        """测试端口转发"""
        with patch.object(
            mock_client,
            "_run_command",
            return_value=(0, "", ""),
        ):
            result = await mock_client.forward(
                "device1", "tcp:8080", "tcp:8080"
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_reverse(self, mock_client):
        """测试反向端口转发"""
        with patch.object(
            mock_client,
            "_run_command",
            return_value=(0, "", ""),
        ):
            result = await mock_client.reverse(
                "device1", "tcp:8080", "tcp:8080"
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_reverse_remove(self, mock_client):
        """测试移除反向端口转发"""
        with patch.object(
            mock_client,
            "_run_command",
            return_value=(0, "", ""),
        ):
            result = await mock_client.reverse_remove("device1", "tcp:8080")
            assert result is True


class TestADBClientErrors:
    """ADB 客户端错误处理测试"""

    @pytest.fixture
    def mock_client(self):
        """创建模拟的 ADB 客户端"""
        with patch("shutil.which", return_value="/usr/bin/adb"):
            return ADBClient()

    @pytest.mark.asyncio
    async def test_command_timeout(self, mock_client):
        """测试命令超时"""
        async def slow_command(*args, **kwargs):
            await asyncio.sleep(10)
            return (0, "", "")

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = slow_command
            mock_proc.kill = MagicMock()
            mock_exec.return_value = mock_proc

            with pytest.raises(ADBError, match="timed out"):
                await mock_client._run_command("devices", timeout=0.1)

    @pytest.mark.asyncio
    async def test_list_devices_failure(self, mock_client):
        """测试列出设备失败"""
        with patch.object(
            mock_client,
            "_run_command",
            return_value=(1, "", "error: no devices/emulators found"),
        ):
            with pytest.raises(ADBError, match="Failed to list devices"):
                await mock_client.list_devices()


@pytest.mark.requires_device
class TestADBClientReal:
    """真实设备测试（需要连接设备）"""

    @pytest.mark.asyncio
    async def test_list_real_devices(self):
        """测试列出真实设备"""
        try:
            client = ADBClient()
        except ADBError:
            pytest.skip("ADB not installed")

        devices = await client.list_devices()
        # 至少应该能执行，即使没有设备
        assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_shell_on_real_device(self):
        """测试在真实设备上执行命令"""
        try:
            client = ADBClient()
        except ADBError:
            pytest.skip("ADB not installed")

        devices = await client.list_devices()
        if not devices:
            pytest.skip("No device connected")

        online_devices = [d for d in devices if d.is_online]
        if not online_devices:
            pytest.skip("No online device")

        code, output = await client.shell(online_devices[0].serial, "echo test123")
        assert "test" in output

    @pytest.mark.asyncio
    async def test_get_android_version_real(self):
        """测试获取真实设备的 Android 版本"""
        try:
            client = ADBClient()
        except ADBError:
            pytest.skip("ADB not installed")

        devices = await client.list_devices()
        online_devices = [d for d in devices if d.is_online]
        if not online_devices:
            pytest.skip("No online device")

        version = await client.get_android_version(online_devices[0].serial)
        assert version > 0  # 应该是一个有效的 SDK 版本号
