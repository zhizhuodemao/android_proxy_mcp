"""
编码处理工具

处理 HTTP 响应体的编码检测和 Base64 转换。
符合 Chrome DevTools Protocol 的 Network.getResponseBody 返回格式。
"""

import base64

# 已知的二进制 MIME 类型前缀
BINARY_MIME_PREFIXES = (
    "image/",
    "audio/",
    "video/",
    "application/octet-stream",
    "application/zip",
    "application/gzip",
    "application/x-gzip",
    "application/x-tar",
    "application/pdf",
    "application/x-protobuf",
    "application/protobuf",
    "application/grpc",
)

# 已知的文本 MIME 类型前缀
TEXT_MIME_PREFIXES = (
    "text/",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-javascript",
    "application/ecmascript",
)


def is_binary_content(data: bytes, content_type: str) -> bool:
    """
    判断内容是否为二进制

    使用以下启发式规则：
    1. 检查 Content-Type 是否为已知的二进制类型
    2. 检查内容是否包含空字节（null byte）
    3. 检查不可打印字符的比例

    Args:
        data: 原始字节数据
        content_type: Content-Type 头的值

    Returns:
        True 如果是二进制内容，False 如果是文本
    """
    if not data:
        return False

    # 清理 content_type
    content_type = (content_type or "").lower().split(";")[0].strip()

    # 检查已知的二进制类型
    if any(content_type.startswith(prefix) for prefix in BINARY_MIME_PREFIXES):
        return True

    # 检查已知的文本类型
    if any(content_type.startswith(prefix) for prefix in TEXT_MIME_PREFIXES):
        # 即使声称是文本，也检查是否真的是文本
        return _contains_binary_markers(data)

    # 未知类型，通过内容检测
    return _contains_binary_markers(data)


def _contains_binary_markers(data: bytes) -> bool:
    """检查数据是否包含二进制标记"""
    # 只检查前 8KB，避免大文件性能问题
    sample = data[:8192]

    # 检查空字节
    if b"\x00" in sample:
        return True

    # 统计不可打印字符（排除常见的空白字符）
    non_printable = 0
    for byte in sample:
        # ASCII 可打印字符范围: 32-126, 加上常见控制字符 (tab, newline, carriage return)
        if byte < 32 and byte not in (9, 10, 13):
            non_printable += 1
        elif byte > 126:
            # 高位字符可能是 UTF-8，先不算作二进制
            pass

    # 如果超过 10% 是不可打印字符，判定为二进制
    if len(sample) > 0 and non_printable / len(sample) > 0.1:
        return True

    return False


def encode_body(data: bytes, content_type: str) -> tuple[str, bool]:
    """
    编码响应体

    根据内容类型和实际内容决定是返回原始文本还是 Base64 编码。
    符合 CDP Network.getResponseBody 的返回格式。

    Args:
        data: 原始字节数据
        content_type: Content-Type 头的值

    Returns:
        tuple[str, bool]: (编码后的字符串, 是否为 Base64 编码)
    """
    if not data:
        return "", False

    if is_binary_content(data, content_type):
        # 二进制内容使用 Base64 编码
        encoded = base64.b64encode(data).decode("ascii")
        return encoded, True

    # 文本内容尝试解码
    # 尝试 UTF-8
    try:
        return data.decode("utf-8"), False
    except UnicodeDecodeError:
        pass

    # 尝试从 Content-Type 获取编码
    charset = _extract_charset(content_type)
    if charset:
        try:
            return data.decode(charset), False
        except (UnicodeDecodeError, LookupError):
            pass

    # 尝试 Latin-1（永远不会失败）
    try:
        return data.decode("latin-1"), False
    except UnicodeDecodeError:
        pass

    # 最后回退到 Base64
    encoded = base64.b64encode(data).decode("ascii")
    return encoded, True


def _extract_charset(content_type: str) -> str | None:
    """从 Content-Type 中提取 charset"""
    if not content_type:
        return None

    content_type = content_type.lower()
    if "charset=" not in content_type:
        return None

    # 解析 charset=xxx
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("charset="):
            charset = part[8:].strip().strip('"').strip("'")
            return charset

    return None
