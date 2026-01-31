"""MCP 工具模块"""

from .proxy_tools import get_cert_info
from .traffic_tools import (
    traffic_list,
    traffic_get_detail,
    traffic_clear,
    traffic_search,
    traffic_read_body,
    proxy_status,
)
from .android_tools import (
    android_list_devices,
    android_get_device_info,
    android_setup_proxy,
    android_clear_proxy,
)

__all__ = [
    # Proxy tools
    "get_cert_info",
    "proxy_status",
    # Traffic tools
    "traffic_list",
    "traffic_get_detail",
    "traffic_search",
    "traffic_read_body",
    "traffic_clear",
    # Android tools
    "android_list_devices",
    "android_get_device_info",
    "android_setup_proxy",
    "android_clear_proxy",
]
