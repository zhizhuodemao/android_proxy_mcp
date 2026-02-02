"""
MCP 服务入口

基于 MCP 协议的 Android 无头抓包服务。
流量数据通过 SQLite 与启动脚本共享。
"""

import asyncio
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .tools import (
    get_cert_info,
    proxy_status,
    traffic_list,
    traffic_get_detail,
    traffic_search,
    traffic_read_body,
    traffic_clear,
    android_list_devices,
    android_get_device_info,
    android_setup_proxy,
    android_clear_proxy,
)

# 创建 MCP 服务器
server = Server("android-proxy-mcp")


# ============== 工具定义 ==============

@server.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有可用工具"""
    return [
        # 代理状态工具
        Tool(
            name="proxy_status",
            description="获取代理服务器状态。注意：需要先在终端运行 'uv run android-proxy-start' 启动代理。",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_cert_info",
            description="获取 CA 证书信息和安装指南。抓取 HTTPS 流量需要在设备上安装此证书。",
            inputSchema={"type": "object", "properties": {}},
        ),
        # 流量工具
        Tool(
            name="traffic_list",
            description="列出捕获的 HTTP/HTTPS 流量。默认返回最近 10 条，支持分页和筛选。",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "返回数量限制，默认 10，最大 10",
                        "default": 10,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "跳过前 N 条记录，用于分页（如 offset=10 查看第 11-20 条）",
                        "default": 0,
                    },
                    "filter_domain": {
                        "type": "string",
                        "description": "按域名筛选，支持通配符（如 *.example.com）",
                    },
                    "filter_type": {
                        "type": "string",
                        "description": "按资源类型筛选（XHR, Document, Image, Script, Stylesheet, Font, Media, Other）",
                    },
                    "filter_status": {
                        "type": "string",
                        "description": "按状态码筛选（如 200, 4xx, 500-599）",
                    },
                    "filter_url": {
                        "type": "string",
                        "description": "按 URL 筛选，支持正则表达式",
                    },
                },
            },
        ),
        Tool(
            name="traffic_get_detail",
            description="获取单个请求的元数据（请求头、响应头、参数等）。注意：不包含请求体和响应体内容，使用 traffic_read_body 读取。",
            inputSchema={
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": "请求 ID（从 traffic_list 获取）",
                    },
                },
                "required": ["request_id"],
            },
        ),
        Tool(
            name="traffic_search",
            description="搜索流量内容。可搜索 URL、请求头、请求体、响应头、响应体。返回匹配的片段而非完整内容。",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "search_in": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "搜索范围：url, request_headers, request_body, response_headers, response_body, all（默认）",
                    },
                    "method": {
                        "type": "string",
                        "description": "限定 HTTP 方法（GET/POST）",
                    },
                    "domain": {
                        "type": "string",
                        "description": "限定域名（支持通配符 %）",
                    },
                    "context_chars": {
                        "type": "integer",
                        "description": "返回匹配内容前后字符数，默认 150",
                        "default": 150,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回几条匹配，默认 10",
                        "default": 10,
                    },
                },
                "required": ["keyword"],
            },
        ),
        Tool(
            name="traffic_read_body",
            description="分片读取请求体或响应体。用于查看大内容，支持分页读取。",
            inputSchema={
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": "请求 ID",
                    },
                    "field": {
                        "type": "string",
                        "description": "读取字段：request_body 或 response_body（默认）",
                        "default": "response_body",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "起始位置，默认 0",
                        "default": 0,
                    },
                    "length": {
                        "type": "integer",
                        "description": "读取长度，默认 4000 字符",
                        "default": 4000,
                    },
                },
                "required": ["request_id"],
            },
        ),
        Tool(
            name="traffic_clear",
            description="清空所有捕获的流量",
            inputSchema={"type": "object", "properties": {}},
        ),
        # Android 工具
        Tool(
            name="android_list_devices",
            description="列出所有连接的 Android 设备",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="android_get_device_info",
            description="获取指定 Android 设备的详细信息（型号、版本、是否 root 等）",
            inputSchema={
                "type": "object",
                "properties": {
                    "serial": {
                        "type": "string",
                        "description": "设备序列号（从 android_list_devices 获取）",
                    },
                },
                "required": ["serial"],
            },
        ),
        Tool(
            name="android_setup_proxy",
            description="在 Android 设备上设置 HTTP 代理。注意：此方式对部分应用可能无效，建议在 Wi-Fi 设置中手动配置。",
            inputSchema={
                "type": "object",
                "properties": {
                    "serial": {
                        "type": "string",
                        "description": "设备序列号",
                    },
                    "proxy_host": {
                        "type": "string",
                        "description": "代理服务器地址（通常是运行此服务的电脑 IP）",
                    },
                    "proxy_port": {
                        "type": "integer",
                        "description": "代理服务器端口，默认 8080",
                        "default": 8080,
                    },
                },
                "required": ["serial", "proxy_host"],
            },
        ),
        Tool(
            name="android_clear_proxy",
            description="清除 Android 设备上的代理设置",
            inputSchema={
                "type": "object",
                "properties": {
                    "serial": {
                        "type": "string",
                        "description": "设备序列号",
                    },
                },
                "required": ["serial"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """处理工具调用"""
    result: dict[str, Any]

    # 代理工具
    if name == "proxy_status":
        result = proxy_status()
    elif name == "get_cert_info":
        result = get_cert_info()

    # 流量工具
    elif name == "traffic_list":
        result = traffic_list(
            limit=arguments.get("limit", 10),
            offset=arguments.get("offset", 0),
            filter_domain=arguments.get("filter_domain"),
            filter_type=arguments.get("filter_type"),
            filter_status=arguments.get("filter_status"),
            filter_url=arguments.get("filter_url"),
        )
    elif name == "traffic_get_detail":
        result = traffic_get_detail(arguments["request_id"])
    elif name == "traffic_search":
        result = traffic_search(
            keyword=arguments["keyword"],
            search_in=arguments.get("search_in"),
            method=arguments.get("method"),
            domain=arguments.get("domain"),
            context_chars=arguments.get("context_chars", 150),
            limit=arguments.get("limit", 10),
        )
    elif name == "traffic_read_body":
        result = traffic_read_body(
            request_id=arguments["request_id"],
            field=arguments.get("field", "response_body"),
            offset=arguments.get("offset", 0),
            length=arguments.get("length", 4000),
        )
    elif name == "traffic_clear":
        result = traffic_clear()

    # Android 工具（异步）
    elif name == "android_list_devices":
        result = await android_list_devices()
    elif name == "android_get_device_info":
        result = await android_get_device_info(arguments["serial"])
    elif name == "android_setup_proxy":
        result = await android_setup_proxy(
            serial=arguments["serial"],
            proxy_host=arguments["proxy_host"],
            proxy_port=arguments.get("proxy_port", 8080),
        )
    elif name == "android_clear_proxy":
        result = await android_clear_proxy(arguments["serial"])

    else:
        result = {"error": f"Unknown tool: {name}"}

    # 格式化输出
    import json
    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]


async def run_server():
    """运行 MCP 服务器"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main():
    """入口函数"""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
