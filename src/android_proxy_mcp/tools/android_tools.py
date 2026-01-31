"""
Android 工具

提供 Android 设备管理功能。
"""

from typing import Any

from ..android.adb_client import ADBClient, ADBError

# 全局 ADB 客户端实例
_adb_client: ADBClient | None = None


def _get_adb() -> ADBClient:
    """获取或创建 ADB 客户端实例"""
    global _adb_client
    if _adb_client is None:
        _adb_client = ADBClient()
    return _adb_client


async def android_list_devices() -> dict[str, Any]:
    """
    列出所有连接的 Android 设备

    Returns:
        包含设备列表的字典
    """
    try:
        adb = _get_adb()
        devices = await adb.list_devices()

        device_list = []
        for device in devices:
            device_list.append({
                "serial": device.serial,
                "state": device.state,
                "model": device.model,
                "android_version": device.android_version,
                "is_online": device.is_online,
            })

        return {
            "success": True,
            "devices": device_list,
            "count": len(device_list),
        }

    except ADBError as e:
        return {
            "success": False,
            "message": f"ADB error: {e}",
            "devices": [],
            "count": 0,
        }


async def android_get_device_info(serial: str) -> dict[str, Any]:
    """
    获取指定设备的详细信息

    Args:
        serial: 设备序列号

    Returns:
        包含设备详细信息的字典
    """
    try:
        adb = _get_adb()

        # 检查设备是否存在
        devices = await adb.list_devices()
        device = next((d for d in devices if d.serial == serial), None)

        if device is None:
            return {
                "success": False,
                "message": f"Device not found: {serial}",
            }

        if not device.is_online:
            return {
                "success": False,
                "message": f"Device is not online: {serial} (state: {device.state})",
            }

        # 获取更多信息
        sdk_version = await adb.get_android_version(serial)
        is_rooted = await adb.is_rooted(serial)

        # 获取一些常用属性
        brand = await adb.get_prop(serial, "ro.product.brand")
        device_name = await adb.get_prop(serial, "ro.product.device")
        build_id = await adb.get_prop(serial, "ro.build.id")

        return {
            "success": True,
            "device": {
                "serial": device.serial,
                "state": device.state,
                "model": device.model,
                "android_version": device.android_version,
                "sdk_version": sdk_version,
                "is_rooted": is_rooted,
                "brand": brand,
                "device_name": device_name,
                "build_id": build_id,
            },
        }

    except ADBError as e:
        return {
            "success": False,
            "message": f"ADB error: {e}",
        }


async def android_setup_proxy(
    serial: str,
    proxy_host: str,
    proxy_port: int,
) -> dict[str, Any]:
    """
    在设备上设置代理（通过 adb shell settings）

    注意：这种方式设置的代理只对部分应用有效

    Args:
        serial: 设备序列号
        proxy_host: 代理服务器地址
        proxy_port: 代理服务器端口

    Returns:
        包含设置状态的字典
    """
    try:
        adb = _get_adb()

        # 设置全局代理
        cmd = f"settings put global http_proxy {proxy_host}:{proxy_port}"
        exit_code, output = await adb.shell(serial, cmd)

        if exit_code != 0:
            return {
                "success": False,
                "message": f"Failed to set proxy: {output}",
            }

        return {
            "success": True,
            "message": f"Proxy set to {proxy_host}:{proxy_port}",
            "note": "This proxy setting may not work for all apps. "
                    "For better results, configure proxy in Wi-Fi settings manually.",
        }

    except ADBError as e:
        return {
            "success": False,
            "message": f"ADB error: {e}",
        }


async def android_clear_proxy(serial: str) -> dict[str, Any]:
    """
    清除设备上的代理设置

    Args:
        serial: 设备序列号

    Returns:
        包含清除状态的字典
    """
    try:
        adb = _get_adb()

        # 清除全局代理
        cmd = "settings put global http_proxy :0"
        exit_code, output = await adb.shell(serial, cmd)

        if exit_code != 0:
            return {
                "success": False,
                "message": f"Failed to clear proxy: {output}",
            }

        return {
            "success": True,
            "message": "Proxy cleared",
        }

    except ADBError as e:
        return {
            "success": False,
            "message": f"ADB error: {e}",
        }
