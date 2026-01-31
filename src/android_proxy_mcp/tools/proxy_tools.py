"""
代理工具

提供证书信息查询功能。
"""

from typing import Any

from ..android.cert_injector import CertHelper


def get_cert_info() -> dict[str, Any]:
    """
    获取 CA 证书信息和安装指南

    Returns:
        包含证书信息和安装指南的字典
    """
    helper = CertHelper()

    try:
        cert_info = helper.get_cert_info()
        instructions = helper.get_install_instructions(cert_info)

        return {
            "success": True,
            "cert_path": cert_info.pem_path,
            "cert_hash": cert_info.hash,
            "cert_filename": cert_info.filename,
            "install_instructions": instructions,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "message": "CA 证书未找到。请先运行: uv run android-proxy-start",
            "install_instructions": helper.get_install_instructions(),
        }
