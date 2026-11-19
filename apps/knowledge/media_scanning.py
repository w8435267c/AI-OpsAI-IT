"""ClamAV 私有媒体扫描适配；没有可用扫描器时一律失败关闭。"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings


@dataclass(frozen=True, slots=True)
class ScanResult:
    status: str
    message: str


def _read_clamd_reply(client: socket.socket) -> bytes:
    """Read exactly one NUL-terminated clamd response record.

    TCP has no message boundaries: a result such as ``stream: ... FOUND\0`` can
    arrive in several ``recv`` calls.  Treat a closed connection before the
    terminator, or an overlong response, as incomplete so the caller fails
    closed.
    """

    reply = bytearray()
    while len(reply) < 4096:
        chunk = client.recv(4096)
        if not chunk:
            return bytes(reply)
        reply.extend(chunk)
        terminator = reply.find(b"\0")
        if terminator >= 0:
            return bytes(reply[: terminator + 1])
    return bytes(reply)


def _classify_clamd_reply(reply: bytes) -> ScanResult:
    """Only an exact, fully framed clean result is allowed to pass."""

    if not reply.endswith(b"\0"):
        return ScanResult("failed", "扫描服务返回异常，文件暂不能使用。")

    response = reply[:-1].decode("utf-8", errors="replace")
    if response == "stream: OK":
        return ScanResult("clean", "扫描通过。")
    if response.endswith(" FOUND"):
        return ScanResult("infected", "扫描未通过，文件已被隔离。")
    return ScanResult("failed", "扫描服务返回异常，文件暂不能使用。")


def scan_private_file(path: Path) -> ScanResult:
    """使用 clamd INSTREAM 协议扫描文件，绝不把不可用视为通过。"""

    host = settings.KNOWLEDGE_MEDIA_CLAMD_HOST
    if not host:
        return ScanResult("failed", "扫描服务未配置，文件暂不能使用。")
    try:
        with socket.create_connection(
            (host, settings.KNOWLEDGE_MEDIA_CLAMD_PORT),
            timeout=settings.KNOWLEDGE_MEDIA_CLAMD_TIMEOUT_SECONDS,
        ) as client:
            client.settimeout(settings.KNOWLEDGE_MEDIA_CLAMD_TIMEOUT_SECONDS)
            client.sendall(b"zINSTREAM\0")
            with path.open("rb") as source:
                while chunk := source.read(64 * 1024):
                    client.sendall(struct.pack("!I", len(chunk)))
                    client.sendall(chunk)
            client.sendall(struct.pack("!I", 0))
            reply = _read_clamd_reply(client)
    except (OSError, ValueError):
        return ScanResult("failed", "扫描服务暂不可用，文件暂不能使用。")

    return _classify_clamd_reply(reply)
