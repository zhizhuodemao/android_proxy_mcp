"""
证书处理工具

用于计算 Android 系统证书的 hash 值（subject_hash_old 格式）。
"""

import subprocess
import tempfile
from pathlib import Path


def calculate_cert_hash(cert_pem: bytes | str) -> str:
    """
    计算证书的 subject_hash_old（Android 系统证书命名格式）

    Android 系统证书使用 OpenSSL 的 subject_hash_old 算法命名。
    文件名格式为: <hash>.0, <hash>.1, ...

    Args:
        cert_pem: PEM 格式的证书内容（bytes 或 str）

    Returns:
        8 位十六进制字符串，如 "c8450d0d"

    Raises:
        RuntimeError: 如果 openssl 命令执行失败
    """
    if isinstance(cert_pem, str):
        cert_pem = cert_pem.encode("utf-8")

    # 使用 openssl 命令计算 subject_hash_old
    # 这是最可靠的方式，因为 Python 的 cryptography 库不直接支持这个算法
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as f:
        f.write(cert_pem)
        temp_path = f.name

    try:
        result = subprocess.run(
            ["openssl", "x509", "-inform", "PEM", "-subject_hash_old", "-noout"],
            input=cert_pem,
            capture_output=True,
            check=True,
        )
        hash_value = result.stdout.decode("utf-8").strip()

        # 验证返回的是有效的 hash（8 位十六进制）
        if len(hash_value) == 8 and all(c in "0123456789abcdef" for c in hash_value):
            return hash_value

        raise RuntimeError(f"Invalid hash format from openssl: {hash_value}")

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"openssl command failed: {e.stderr.decode('utf-8')}") from e
    except FileNotFoundError:
        raise RuntimeError(
            "openssl command not found. Please install OpenSSL."
        ) from None
    finally:
        Path(temp_path).unlink(missing_ok=True)


def get_cert_filename(cert_pem: bytes | str, index: int = 0) -> str:
    """
    获取证书在 Android 系统中的文件名

    Args:
        cert_pem: PEM 格式的证书内容
        index: 如果存在 hash 冲突，使用的索引（默认 0）

    Returns:
        文件名，如 "c8450d0d.0"
    """
    hash_value = calculate_cert_hash(cert_pem)
    return f"{hash_value}.{index}"
