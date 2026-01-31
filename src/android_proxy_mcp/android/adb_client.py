"""
ADB 客户端

封装 ADB 命令，提供设备管理基础能力。
"""

import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DeviceInfo:
    """设备信息"""

    serial: str
    state: str  # "device" | "offline" | "unauthorized" | "no permissions"
    model: str | None = None
    android_version: str | None = None
    product: str | None = None
    transport_id: str | None = None
    extra_info: dict[str, str] = field(default_factory=dict)

    @property
    def is_online(self) -> bool:
        """设备是否在线可用"""
        return self.state == "device"


class ADBError(Exception):
    """ADB 操作错误"""

    def __init__(self, message: str, returncode: int = -1, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class ADBClient:
    """
    ADB 客户端

    封装 ADB 命令执行，提供异步接口。
    """

    def __init__(self, adb_path: str | None = None):
        """
        初始化 ADB 客户端

        Args:
            adb_path: ADB 可执行文件路径，默认从 PATH 查找
        """
        self._adb_path = adb_path or shutil.which("adb")
        if not self._adb_path:
            raise ADBError("ADB not found in PATH")

    @property
    def adb_path(self) -> str:
        """获取 ADB 路径"""
        assert self._adb_path is not None
        return self._adb_path

    async def _run_command(
        self,
        *args: str,
        timeout: float = 30.0,
    ) -> tuple[int, str, str]:
        """
        执行 ADB 命令

        Args:
            *args: 命令参数
            timeout: 超时时间（秒）

        Returns:
            (returncode, stdout, stderr)
        """
        assert self._adb_path is not None
        cmd = [self._adb_path, *args]

        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )

            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace").strip(),
                stderr.decode("utf-8", errors="replace").strip(),
            )
        except asyncio.TimeoutError:
            if proc is not None:
                proc.kill()
            raise ADBError(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        except Exception as e:
            raise ADBError(f"Failed to execute ADB command: {e}")

    async def list_devices(self) -> list[DeviceInfo]:
        """
        列出所有连接的设备

        Returns:
            设备信息列表
        """
        returncode, stdout, stderr = await self._run_command("devices", "-l")

        if returncode != 0:
            raise ADBError(f"Failed to list devices: {stderr}", returncode, stderr)

        devices = []
        lines = stdout.strip().split("\n")

        for line in lines[1:]:  # 跳过 "List of devices attached" 头
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            serial = parts[0]
            state = parts[1]

            # 解析额外信息（如 model:xxx product:xxx）
            extra_info = {}
            for part in parts[2:]:
                if ":" in part:
                    key, value = part.split(":", 1)
                    extra_info[key] = value

            device = DeviceInfo(
                serial=serial,
                state=state,
                model=extra_info.get("model"),
                product=extra_info.get("product"),
                transport_id=extra_info.get("transport_id"),
                extra_info=extra_info,
            )

            # 获取 Android 版本（仅对在线设备）
            if device.is_online:
                version = await self.get_prop(serial, "ro.build.version.release")
                device.android_version = version

            devices.append(device)

        return devices

    async def shell(
        self,
        serial: str,
        command: str,
        timeout: float = 30.0,
    ) -> tuple[int, str]:
        """
        在设备上执行 shell 命令

        Args:
            serial: 设备序列号
            command: 要执行的命令
            timeout: 超时时间

        Returns:
            (exit_code, output)
        """
        returncode, stdout, stderr = await self._run_command(
            "-s", serial, "shell", command,
            timeout=timeout,
        )

        # ADB shell 命令的返回码可能在 stdout 或需要通过 echo $? 获取
        # 这里简化处理，返回 adb 命令本身的返回码和输出
        output = stdout if stdout else stderr

        return returncode, output

    async def shell_with_exit_code(
        self,
        serial: str,
        command: str,
        timeout: float = 30.0,
    ) -> tuple[int, str]:
        """
        在设备上执行 shell 命令并获取真实的 exit code

        Args:
            serial: 设备序列号
            command: 要执行的命令
            timeout: 超时时间

        Returns:
            (exit_code, output)
        """
        # 使用 ; echo $? 来获取真实的退出码
        full_command = f"{command}; echo __EXIT_CODE__$?"
        _, output = await self.shell(serial, full_command, timeout)

        # 解析退出码
        lines = output.rsplit("__EXIT_CODE__", 1)
        if len(lines) == 2:
            try:
                exit_code = int(lines[1].strip())
                return exit_code, lines[0].strip()
            except ValueError:
                pass

        return 0, output

    async def push(
        self,
        serial: str,
        local_path: str,
        remote_path: str,
        timeout: float = 60.0,
    ) -> bool:
        """
        推送文件到设备

        Args:
            serial: 设备序列号
            local_path: 本地文件路径
            remote_path: 设备上的目标路径
            timeout: 超时时间

        Returns:
            是否成功
        """
        if not Path(local_path).exists():
            raise ADBError(f"Local file not found: {local_path}")

        returncode, stdout, stderr = await self._run_command(
            "-s", serial, "push", local_path, remote_path,
            timeout=timeout,
        )

        if returncode != 0:
            raise ADBError(
                f"Failed to push file: {stderr or stdout}",
                returncode,
                stderr,
            )

        return True

    async def pull(
        self,
        serial: str,
        remote_path: str,
        local_path: str,
        timeout: float = 60.0,
    ) -> bool:
        """
        从设备拉取文件

        Args:
            serial: 设备序列号
            remote_path: 设备上的文件路径
            local_path: 本地目标路径
            timeout: 超时时间

        Returns:
            是否成功
        """
        returncode, stdout, stderr = await self._run_command(
            "-s", serial, "pull", remote_path, local_path,
            timeout=timeout,
        )

        if returncode != 0:
            raise ADBError(
                f"Failed to pull file: {stderr or stdout}",
                returncode,
                stderr,
            )

        return True

    async def get_prop(
        self,
        serial: str,
        prop: str,
    ) -> str | None:
        """
        获取设备属性

        Args:
            serial: 设备序列号
            prop: 属性名称（如 ro.build.version.release）

        Returns:
            属性值，如果不存在返回 None
        """
        _, output = await self.shell(serial, f"getprop {prop}")
        output = output.strip()
        return output if output else None

    async def is_rooted(self, serial: str) -> bool:
        """
        检查设备是否已 root

        Args:
            serial: 设备序列号

        Returns:
            是否已 root
        """
        # 方法1: 尝试执行 su -c id
        exit_code, output = await self.shell_with_exit_code(
            serial,
            "su -c id",
            timeout=5.0,
        )

        if exit_code == 0 and "uid=0" in output:
            return True

        # 方法2: 检查是否有 su 二进制文件
        _, output = await self.shell(serial, "which su")
        if output and "/su" in output:
            return True

        # 方法3: 检查常见 root 管理器
        _, output = await self.shell(serial, "pm list packages | grep -E 'supersu|magisk'")
        if output and ("supersu" in output.lower() or "magisk" in output.lower()):
            return True

        return False

    async def root_shell(
        self,
        serial: str,
        command: str,
        timeout: float = 30.0,
    ) -> tuple[int, str]:
        """
        以 root 权限执行 shell 命令

        Args:
            serial: 设备序列号
            command: 要执行的命令
            timeout: 超时时间

        Returns:
            (exit_code, output)
        """
        # 使用 su -c 执行命令
        return await self.shell_with_exit_code(
            serial,
            f"su -c '{command}'",
            timeout=timeout,
        )

    async def get_android_version(self, serial: str) -> int:
        """
        获取 Android SDK 版本号

        Args:
            serial: 设备序列号

        Returns:
            SDK 版本号（如 34 表示 Android 14）
        """
        sdk_str = await self.get_prop(serial, "ro.build.version.sdk")
        if sdk_str:
            try:
                return int(sdk_str)
            except ValueError:
                pass

        return 0

    async def forward(
        self,
        serial: str,
        local: str,
        remote: str,
    ) -> bool:
        """
        设置端口转发

        Args:
            serial: 设备序列号
            local: 本地端口（如 tcp:8080）
            remote: 远程端口（如 tcp:8080）

        Returns:
            是否成功
        """
        returncode, stdout, stderr = await self._run_command(
            "-s", serial, "forward", local, remote,
        )

        if returncode != 0:
            raise ADBError(
                f"Failed to forward port: {stderr or stdout}",
                returncode,
                stderr,
            )

        return True

    async def reverse(
        self,
        serial: str,
        remote: str,
        local: str,
    ) -> bool:
        """
        设置反向端口转发（让设备可以访问主机端口）

        Args:
            serial: 设备序列号
            remote: 设备端口（如 tcp:8080）
            local: 本地端口（如 tcp:8080）

        Returns:
            是否成功
        """
        returncode, stdout, stderr = await self._run_command(
            "-s", serial, "reverse", remote, local,
        )

        if returncode != 0:
            raise ADBError(
                f"Failed to reverse port: {stderr or stdout}",
                returncode,
                stderr,
            )

        return True

    async def reverse_remove(
        self,
        serial: str,
        remote: str,
    ) -> bool:
        """
        移除反向端口转发

        Args:
            serial: 设备序列号
            remote: 设备端口（如 tcp:8080）

        Returns:
            是否成功
        """
        returncode, _, _ = await self._run_command(
            "-s", serial, "reverse", "--remove", remote,
        )

        return returncode == 0
