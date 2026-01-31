"""
MIME 类型到 CDP ResourceType 的映射

基于 Chromium 源码中的 ResourceType 定义进行逆向映射。
"""

from urllib.parse import urlparse


def infer_resource_type(mime_type: str, url: str, headers: dict) -> str:
    """
    根据 MIME 类型、URL 和请求头推断 CDP ResourceType

    Args:
        mime_type: Content-Type 头的值（可能包含 charset）
        url: 请求的完整 URL
        headers: 请求或响应头字典

    Returns:
        CDP ResourceType: "Document" | "Stylesheet" | "Image" | "Script" |
                          "XHR" | "Font" | "Media" | "WebSocket" | "Other"
    """
    # 清理 MIME 类型（去除 charset 等参数）
    mime_type = _clean_mime_type(mime_type)
    mime_lower = mime_type.lower()

    # 获取 URL 路径的扩展名
    ext = _get_extension(url)

    # 检查 WebSocket 升级
    upgrade_header = headers.get("Upgrade", headers.get("upgrade", ""))
    if upgrade_header.lower() == "websocket":
        return "WebSocket"

    # 检查 XHR 标记
    xhr_header = headers.get("X-Requested-With", headers.get("x-requested-with", ""))
    if xhr_header.lower() == "xmlhttprequest":
        return "XHR"

    # Document: HTML 文档
    if "text/html" in mime_lower or ext in (".html", ".htm", ".asp", ".php", ".jsp"):
        return "Document"

    # Stylesheet: CSS
    if "text/css" in mime_lower or ext == ".css":
        return "Stylesheet"

    # Image: 图片
    if mime_lower.startswith("image/") or ext in (
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp"
    ):
        return "Image"

    # Media: 音视频
    if mime_lower.startswith("audio/") or mime_lower.startswith("video/") or ext in (
        ".mp4", ".mp3", ".webm", ".ogg", ".wav", ".m4a", ".avi", ".mov"
    ):
        return "Media"

    # Font: 字体
    if "font" in mime_lower or ext in (".woff", ".woff2", ".ttf", ".otf", ".eot"):
        return "Font"

    # Script: JavaScript
    if (
        "javascript" in mime_lower
        or "ecmascript" in mime_lower
        or ext in (".js", ".mjs", ".jsx", ".ts", ".tsx")
    ):
        return "Script"

    # XHR: JSON/XML API 响应
    if mime_lower in (
        "application/json",
        "application/xml",
        "text/xml",
        "text/json",
    ) or ext in (".json", ".xml"):
        return "XHR"

    # 其他 application 类型也可能是 API 调用
    if mime_lower.startswith("application/") and "octet-stream" not in mime_lower:
        return "XHR"

    return "Other"


def _clean_mime_type(mime_type: str) -> str:
    """清理 MIME 类型，去除 charset 等参数"""
    if not mime_type:
        return ""
    # 取分号前的部分
    return mime_type.split(";")[0].strip()


def _get_extension(url: str) -> str:
    """从 URL 中提取文件扩展名"""
    try:
        parsed = urlparse(url)
        path = parsed.path
        # 去除查询参数后获取扩展名
        if "." in path:
            ext = "." + path.rsplit(".", 1)[-1].lower()
            # 过滤掉太长的扩展名（可能不是真正的扩展名）
            if len(ext) <= 6:
                return ext
    except Exception:
        pass
    return ""
