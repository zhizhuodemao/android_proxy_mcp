# Android Proxy MCP

基于 MCP (Model Context Protocol) 的 Android 抓包服务，让 AI 助手能够帮你抓取和分析 HTTP/HTTPS 流量。

## 功能特点

- **抓包**: 捕获 HTTP/HTTPS 流量，支持按域名、状态码、资源类型筛选
- **智能搜索**: 搜索请求/响应内容，支持大响应分片读取
- **AI 驱动**: 通过自然语言让 Claude 帮你分析网络请求

## 架构

```
┌─────────────────┐     SQLite      ┌─────────────────┐
│  代理服务        │ ─────────────→  │  MCP 服务        │
│  (终端手动启动)   │   流量数据共享   │  (Claude 调用)   │
│  mitmdump       │                 │  查询/搜索/分析   │
└─────────────────┘                 └─────────────────┘
        ↑
        │ HTTP/HTTPS
        │
   ┌─────────┐
   │  手机    │
   └─────────┘
```

## 快速开始

### 1. 环境要求

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (Python 包管理器)

### 2. 安装

```bash
# 克隆项目
git clone https://github.com/yourname/android-proxy-mcp.git
cd android-proxy-mcp

# 安装依赖
uv sync
```

### 3. 配置 Claude Desktop

编辑 Claude Desktop 配置文件：

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "android-proxy": {
      "command": "uv",
      "args": ["--directory", "/path/to/android-proxy-mcp", "run", "android-proxy-mcp"]
    }
  }
}
```

> 将 `/path/to/android-proxy-mcp` 替换为实际项目路径

### 4. 重启 Claude Desktop

配置完成后，重启 Claude Desktop 使配置生效。

---

## 使用方法

### 第一步：启动代理

**在终端中运行：**

```bash
uv run android-proxy-start
```

你会看到如下输出：

```
╔════════════════════════════════════════════════════════════╗
║            🚀 Android Proxy MCP 启动向导                   ║
╚════════════════════════════════════════════════════════════╝

════════════════════════════════════════════════════════════
  环境检测
════════════════════════════════════════════════════════════

    ✓ 端口 8288 可用

════════════════════════════════════════════════════════════
  手机配置
════════════════════════════════════════════════════════════

    手机 Wi-Fi 代理设置:

       ┌─────────────────────────────────┐
       │  服务器:    192.168.1.100       │
       │  端  口:        8288            │
       └─────────────────────────────────┘

    证书安装: 手机浏览器访问 http://mitm.it

════════════════════════════════════════════════════════════
  启动代理 (Ctrl+C 停止)
════════════════════════════════════════════════════════════
```

> 保持这个终端窗口运行，不要关闭。

### 第二步：配置手机代理

**确保手机和电脑在同一 Wi-Fi 网络下。**

1. 手机进入 **设置 → Wi-Fi**
2. 长按当前连接的 Wi-Fi → **修改网络**
3. 展开 **高级选项**
4. 代理设置选择 **手动**
5. 填写启动脚本显示的 IP 和端口
6. 保存

### 第三步：安装 CA 证书（抓 HTTPS 必须）

1. 手机浏览器访问 `http://mitm.it`（通过代理访问）
2. 选择 Android 图标下载证书
3. 设置 → 安全 → 加密与凭据 → 安装证书 → CA 证书
4. 选择下载的证书文件安装

> ⚠️ **注意**: Android 7+ 用户证书默认不被 App 信任，只能抓取浏览器和部分应用的 HTTPS 流量。

#### 安装系统证书（Root 用户）

如果你的设备已 Root（安装了 Magisk），可以将用户证书移动为系统证书：

1. 先按照上述步骤安装用户证书
2. 安装 `resources/MoveCertificate-v1.5.5.zip` Magisk 模块：
   - 打开 Magisk → 模块 → 从本地安装
   - 选择项目中的 `resources/MoveCertificate-v1.5.5.zip`
   - 重启设备
3. 重启后，用户证书会自动移动到系统证书目录

---

### 第四步：在 Claude 中查询流量

打开 **Claude Desktop**，用自然语言查询流量：

**基础查询：**
> "显示最近的网络请求"
> "显示 api.example.com 的请求"
> "显示所有失败的请求（状态码 4xx 或 5xx）"

**搜索内容：**
> "搜索响应中包含 '张三' 的请求"
> "搜索 URL 中包含 search 的请求"
> "搜索请求头中包含 X-Token 的请求"

**查看大响应：**
> "读取 req-5 的响应体"
> "继续读取 req-5 响应体，从 4000 开始"

**智能分析：**
> "帮我找酷安 app 的搜索接口"
> "分析这个 API 的请求参数"

### 第五步：停止抓包

在运行代理的终端窗口按 `Ctrl+C` 停止代理。

记得在手机 Wi-Fi 设置中关闭代理。

---

## MCP 工具列表

| 工具 | 说明 |
|-----|------|
| `proxy_status` | 获取代理状态 |
| `traffic_list` | 列出流量（支持域名/状态码/类型筛选）|
| `traffic_search` | 搜索流量内容（URL/请求头/请求体/响应头/响应体）|
| `traffic_get_detail` | 获取请求元数据（请求头、响应头等）|
| `traffic_read_body` | 分片读取大响应体 |
| `traffic_clear` | 清空流量记录 |
| `get_cert_info` | 获取证书安装指南 |

---

## 常见问题

### Q: 手机配置代理后无法上网？

1. 确认电脑和手机在同一 Wi-Fi
2. 确认代理已启动（检查终端窗口）
3. 检查电脑防火墙是否允许 8288 端口
4. 尝试用电脑 IP（不是 localhost）

### Q: 能抓到 HTTP 但抓不到 HTTPS？

需要安装 CA 证书。手机浏览器访问 `http://mitm.it` 下载安装。

### Q: 安装了证书但某些 App 还是抓不到 HTTPS？

- Android 7+ 用户证书默认不被 App 信任 → 需要安装系统证书（参考上方）
- 部分 App 有 SSL Pinning → 需要使用 Frida/LSPosed 等工具绕过

### Q: 响应太大，MCP 无法返回？

使用 `traffic_search` 搜索关键词定位，然后用 `traffic_read_body` 分片读取。

---

## 项目结构

```
android-proxy-mcp/
├── README.md
├── pyproject.toml
├── src/
│   └── android_proxy_mcp/
│       ├── cli/              # 命令行工具
│       │   └── start.py      # 代理启动脚本
│       ├── core/             # 核心模块
│       │   └── sqlite_store.py  # SQLite 流量存储
│       ├── tools/            # MCP 工具
│       └── server.py         # MCP 服务入口
├── tests/
├── docs/                     # 文档
└── resources/                # 资源文件
    └── MoveCertificate-v1.5.5.zip  # 证书移动模块
```

## 开发

```bash
# 安装开发依赖
uv sync --extra dev

# 运行测试
uv run pytest tests/ -v

# 代码格式化
uv run ruff format .
```

## 许可证

MIT License
