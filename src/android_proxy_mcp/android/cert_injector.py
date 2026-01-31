"""
证书助手

提供证书相关的辅助功能，如获取证书路径、计算 hash、推送到设备等。
证书的实际安装由用户手动完成。
"""

from dataclasses import dataclass
from pathlib import Path

from ..utils.cert_utils import calculate_cert_hash, get_cert_filename
from .adb_client import ADBClient


@dataclass
class CertInfo:
    """证书信息"""

    pem_path: str
    hash: str
    filename: str
    pem_content: bytes


class CertHelper:
    """
    证书助手

    提供证书相关的辅助功能：
    - 获取 mitmproxy CA 证书信息
    - 推送证书到设备
    - 生成安装指南
    """

    # mitmproxy 默认证书路径
    MITMPROXY_CERT_DIR = Path.home() / ".mitmproxy"
    MITMPROXY_CA_CERT = MITMPROXY_CERT_DIR / "mitmproxy-ca-cert.pem"

    # 设备上的临时路径
    REMOTE_CERT_DIR = "/sdcard/Download"

    def __init__(self, adb: ADBClient | None = None):
        """
        初始化证书助手

        Args:
            adb: ADB 客户端实例（可选，推送证书时需要）
        """
        self._adb = adb

    def get_cert_info(self, cert_path: str | Path | None = None) -> CertInfo:
        """
        获取证书信息

        Args:
            cert_path: 证书路径，默认使用 mitmproxy CA 证书

        Returns:
            CertInfo 包含证书路径、hash、文件名等信息
        """
        if cert_path is None:
            cert_path = self.MITMPROXY_CA_CERT

        cert_path = Path(cert_path)
        if not cert_path.exists():
            raise FileNotFoundError(f"Certificate not found: {cert_path}")

        pem_content = cert_path.read_bytes()
        cert_hash = calculate_cert_hash(pem_content)
        cert_filename = get_cert_filename(pem_content)

        return CertInfo(
            pem_path=str(cert_path),
            hash=cert_hash,
            filename=cert_filename,
            pem_content=pem_content,
        )

    async def push_cert_to_device(
        self,
        serial: str,
        cert_path: str | Path | None = None,
    ) -> str:
        """
        推送证书到设备的 Download 目录

        Args:
            serial: 设备序列号
            cert_path: 证书路径，默认使用 mitmproxy CA 证书

        Returns:
            设备上的证书路径
        """
        if self._adb is None:
            raise RuntimeError("ADB client not provided")

        cert_info = self.get_cert_info(cert_path)
        remote_path = f"{self.REMOTE_CERT_DIR}/{cert_info.filename}"

        await self._adb.push(serial, cert_info.pem_path, remote_path)
        return remote_path

    def get_install_instructions(self, cert_info: CertInfo | None = None) -> str:
        """
        获取证书安装指南

        Args:
            cert_info: 证书信息，默认使用 mitmproxy CA 证书

        Returns:
            安装指南文本
        """
        if cert_info is None:
            try:
                cert_info = self.get_cert_info()
            except FileNotFoundError:
                return "mitmproxy CA certificate not found. Start proxy first to generate it."

        return f"""## mitmproxy CA Certificate Installation

Certificate file: {cert_info.filename}
Certificate hash: {cert_info.hash}

### Method 1: Via mitm.it (Easiest)
1. Configure device to use proxy
2. Visit http://mitm.it in browser
3. Download and install certificate for your platform

### Method 2: Manual Install (Android)
1. Certificate pushed to: /sdcard/Download/{cert_info.filename}
2. Go to: Settings → Security → Encryption & credentials → Install certificate → CA certificate
3. Select the certificate file

### Method 3: System Certificate (Android, requires root)
For Android 7+, user certificates are not trusted by apps by default.
To install as system certificate (Android 13 and below):
```
adb shell su -c "mount -o rw,remount /system"
adb shell su -c "cp /sdcard/Download/{cert_info.filename} /system/etc/security/cacerts/"
adb shell su -c "chmod 644 /system/etc/security/cacerts/{cert_info.filename}"
adb shell su -c "mount -o ro,remount /system"
```

For Android 14+, see: Android14_证书注入方案.md

### iOS
1. Visit http://mitm.it via Safari
2. Settings → General → VPN & Device Management → Install profile
3. Settings → General → About → Certificate Trust Settings → Enable mitmproxy
"""
