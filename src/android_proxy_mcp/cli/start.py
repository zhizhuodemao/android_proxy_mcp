"""
Android Proxy 启动脚本

交互式启动代理服务，使用 mitmproxy 原生命令。
"""

import socket
import subprocess
import sys
import time

from loguru import logger

# 配置 loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<level>{message}</level>",
    level="INFO",
    colorize=True,
)


def get_local_ip() -> str:
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def check_port_available(port: int) -> bool:
    """检查端口是否可用"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("0.0.0.0", port))
        s.close()
        return True
    except OSError:
        return False


def kill_port_process(port: int) -> bool:
    """关闭占用指定端口的进程"""
    try:
        result = subprocess.run(
            ["lsof", "-t", "-i", f":{port}"],
            capture_output=True,
            text=True
        )
        pids = [pid for pid in result.stdout.strip().split('\n') if pid]
        if not pids:
            return False
        for pid in pids:
            subprocess.run(["kill", "-9", pid], capture_output=True)
        time.sleep(1)
        return check_port_available(port)
    except Exception:
        return False


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Android Proxy MCP 启动脚本")
    parser.add_argument("--port", type=int, default=8288, help="监听端口 (默认: 8288)")
    args = parser.parse_args()

    # ========== 欢迎界面 ==========
    logger.opt(colors=True).info("<magenta>╔════════════════════════════════════════════════════════════╗</magenta>")
    logger.opt(colors=True).info("<magenta>║            🚀 Android Proxy MCP 启动向导                   ║</magenta>")
    logger.opt(colors=True).info("<magenta>╚════════════════════════════════════════════════════════════╝</magenta>")

    # ========== 环境检测 ==========
    logger.opt(colors=True).info(f"\n<cyan>{'═' * 60}</cyan>")
    logger.opt(colors=True).info("<cyan>  环境检测</cyan>")
    logger.opt(colors=True).info(f"<cyan>{'═' * 60}</cyan>\n")

    # 端口检测
    if check_port_available(args.port):
        logger.opt(colors=True).success(f"    ✓ 端口 {args.port} 可用")
    else:
        logger.opt(colors=True).warning(f"    ⚠️  端口 {args.port} 已被占用")
        try:
            answer = input("\n    是否关闭占用该端口的进程？(y/N): ").strip().lower()
            if answer == 'y':
                if kill_port_process(args.port):
                    logger.opt(colors=True).success(f"    ✓ 端口 {args.port} 已释放")
                else:
                    logger.error(f"    ✗ 无法释放端口")
                    sys.exit(1)
            else:
                sys.exit(1)
        except (EOFError, KeyboardInterrupt):
            sys.exit(1)

    local_ip = get_local_ip()

    # ========== 显示配置信息 ==========
    logger.opt(colors=True).info(f"\n<cyan>{'═' * 60}</cyan>")
    logger.opt(colors=True).info("<cyan>  手机配置</cyan>")
    logger.opt(colors=True).info(f"<cyan>{'═' * 60}</cyan>\n")

    logger.info("    手机 Wi-Fi 代理设置:")
    logger.info("")
    logger.info(f"       ┌─────────────────────────────────┐")
    logger.opt(colors=True).info(f"       │  服务器: <cyan>{local_ip:^20}</cyan> │")
    logger.opt(colors=True).info(f"       │  端  口: <cyan>{args.port:^20}</cyan> │")
    logger.info(f"       └─────────────────────────────────┘")
    logger.info("")
    logger.opt(colors=True).info("    证书安装: 手机浏览器访问 <green>http://mitm.it</green>")
    logger.info("")

    # ========== 启动 mitmproxy ==========
    logger.opt(colors=True).info(f"<cyan>{'═' * 60}</cyan>")
    logger.opt(colors=True).info("<cyan>  启动代理 (Ctrl+C 停止)</cyan>")
    logger.opt(colors=True).info(f"<cyan>{'═' * 60}</cyan>\n")

    try:
        # 直接使用 mitmdump，流量会保存到 SQLite
        from ..core.sqlite_store import SQLiteTrafficStore

        db_path = SQLiteTrafficStore.get_default_path()
        store = SQLiteTrafficStore(db_path)
        store.clear()

        # 创建 addon 脚本来保存流量到 SQLite
        addon_script = f'''
import json
import time
from pathlib import Path
import sqlite3

DB_PATH = "{db_path}"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS traffic (
            id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            method TEXT NOT NULL,
            url TEXT NOT NULL,
            domain TEXT NOT NULL,
            status INTEGER NOT NULL,
            resource_type TEXT NOT NULL,
            size INTEGER NOT NULL,
            time_ms REAL NOT NULL,
            request_headers TEXT,
            request_body BLOB,
            request_body_size INTEGER DEFAULT 0,
            response_headers TEXT,
            response_body BLOB,
            timing TEXT,
            error TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()
counter = [0]

def response(flow):
    counter[0] += 1
    record_id = f"req-{{counter[0]}}"

    conn = sqlite3.connect(DB_PATH)
    try:
        url = flow.request.pretty_url
        domain = flow.request.host

        # 判断资源类型
        content_type = flow.response.headers.get("content-type", "")
        if "json" in content_type or "xml" in content_type:
            resource_type = "XHR"
        elif "html" in content_type:
            resource_type = "Document"
        elif "image" in content_type:
            resource_type = "Image"
        elif "javascript" in content_type:
            resource_type = "Script"
        elif "css" in content_type:
            resource_type = "Stylesheet"
        else:
            resource_type = "Other"

        conn.execute("""
            INSERT OR REPLACE INTO traffic (
                id, timestamp, method, url, domain, status,
                resource_type, size, time_ms, request_headers,
                request_body, response_headers, response_body, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record_id,
            time.time(),
            flow.request.method,
            url,
            domain,
            flow.response.status_code,
            resource_type,
            len(flow.response.content) if flow.response.content else 0,
            (flow.response.timestamp_end - flow.request.timestamp_start) * 1000 if flow.response.timestamp_end else 0,
            json.dumps(dict(flow.request.headers)),
            flow.request.content,
            json.dumps(dict(flow.response.headers)),
            flow.response.content,
            None
        ))
        conn.commit()
        print(f"[{{counter[0]}}] {{flow.request.method}} {{url[:80]}}")
    except Exception as e:
        print(f"Error: {{e}}")
    finally:
        conn.close()
'''

        # 写入临时 addon 脚本
        addon_path = "/tmp/mitmproxy_addon.py"
        with open(addon_path, "w") as f:
            f.write(addon_script)

        logger.opt(colors=True).info(f"    📂 流量保存: <dim>{db_path}</dim>")
        logger.info("")

        # 启动 mitmdump
        process = subprocess.Popen(
            ["mitmdump", "-p", str(args.port), "-s", addon_path],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

        # 等待退出
        process.wait()

    except KeyboardInterrupt:
        logger.info("\n")
        logger.warning("    正在停止代理...")
        if process:
            process.terminate()
            process.wait()
        logger.opt(colors=True).success("    ✓ 代理已停止")
        logger.warning("    ⚠️  记得关闭手机代理设置!")
        logger.info("")


if __name__ == "__main__":
    main()
