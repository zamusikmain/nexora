import socket
import struct
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import Settings, settings
from app.scanning import ClamAVScanner, DevelopmentScanner


@pytest.mark.parametrize(
    "reply,status",
    [
        (b"stream: OK\x00", 200),
        (b"stream: Test FOUND\x00", 422),
        (b"stream: limit ERROR\x00", 503),
        (b"garbage\x00", 503),
    ],
)
def test_clamav_protocol_fails_closed(tmp_path, reply, status):
    file = tmp_path / "safe.txt"
    file.write_bytes(b"synthetic content")
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def receive():
            with server.accept()[0] as connection:
                connection.settimeout(2)
                stream = connection.makefile("rb")
                assert stream.read(10) == b"zINSTREAM\x00"
                data = b""
                while True:
                    size = struct.unpack("!I", stream.read(4))[0]
                    if not size:
                        break
                    data += stream.read(size)
                assert data == b"synthetic content"
                connection.sendall(reply)

        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(receive)
            scanner = ClamAVScanner("127.0.0.1", port, 2)
            if status == 200:
                scanner.scan(file)
            else:
                with pytest.raises(HTTPException) as error:
                    scanner.scan(file)
                assert error.value.status_code == status
            result.result(timeout=3)


def test_production_cannot_disable_scanning_or_create_demo(monkeypatch, tmp_path):
    baseline = dict(
        _env_file=None,
        seed_demo=False,
        demo_password="",
        app_env="production",
        database_url="postgresql+psycopg://service:private@db/test",
        malware_scanner="clamav",
        web_origin="https://example.test",
        operation_key_secret="x" * 40,
        legacy_operation_keys_until="2026-12-01T00:00:00Z",
    )
    assert Settings(**baseline).web_origin == "https://example.test"
    for values in [
        {"operation_key_secret": "development-only-operation-key-secret-do-not-use"},
        {"operation_key_secret": "too-short"},
        {"legacy_operation_keys_until": None},
        {"malware_scanner": "disabled-development"},
        {"seed_demo": True},
        {"demo_password": "synthetic-demo"},
        {"web_origin": "http://example.test"},
        {"web_origin": "https://user:password@example.test"},
        {"web_origin": "https://example.test?query=yes"},
        {"web_origin": "https://example.test#fragment"},
        {"database_url": "postgresql+psycopg://nexora:local-development-only@db/nexora"},
    ]:
        with pytest.raises(ValidationError):
            Settings(**(baseline | values))
    monkeypatch.setattr(settings(), "app_env", "production")
    with pytest.raises(HTTPException):
        DevelopmentScanner().scan(tmp_path / "file")
