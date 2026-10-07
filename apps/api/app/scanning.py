"""Pluggable, bounded, fail-closed malware scanner."""

import socket
import struct
import time
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException

from app.config import settings


class MalwareScanner(Protocol):
    def scan(self, path: Path) -> None: ...


class DevelopmentScanner:
    def scan(self, path: Path) -> None:
        if settings().app_env != "development":
            raise HTTPException(503, "scanner_unavailable")


class ClamAVScanner:
    def __init__(self, host: str, port: int, timeout: float):
        self.host, self.port, self.timeout = host, port, timeout

    def scan(self, path: Path) -> None:
        deadline = time.monotonic() + self.timeout
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as connection:

                def bounded_send(data: bytes):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    connection.settimeout(remaining)
                    connection.sendall(data)

                bounded_send(b"zINSTREAM\x00")
                with path.open("rb") as file:
                    while chunk := file.read(64 * 1024):
                        bounded_send(struct.pack("!I", len(chunk)) + chunk)
                bounded_send(struct.pack("!I", 0))
                reply = b""
                while b"\x00" not in reply:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    connection.settimeout(remaining)
                    chunk = connection.recv(1024)
                    if not chunk or len(reply) + len(chunk) > 4096:
                        raise ValueError("Invalid scanner response")
                    reply += chunk
                result = reply.split(b"\x00", 1)[0]
                if result == b"stream: OK":
                    return
                if result.startswith(b"stream: ") and result.endswith(b" FOUND"):
                    raise HTTPException(422, "malware_detected")
                raise ValueError("Scanner did not confirm clean content")
        except (OSError, ValueError, TimeoutError):
            raise HTTPException(503, "scanner_unavailable") from None


def scanner() -> MalwareScanner:
    config = settings()
    if config.malware_scanner == "clamav":
        return ClamAVScanner(config.clamav_host, config.clamav_port, config.scan_timeout_seconds)
    return DevelopmentScanner()
