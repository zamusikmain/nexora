import socket

import pytest

from app import client_ip
from app.client_ip import client_address


@pytest.fixture(autouse=True)
def fresh_resolver_cache():
    client_ip._resolved.clear()
    yield
    client_ip._resolved.clear()


def test_untrusted_peer_ignores_forwarded_header():
    assert client_address("203.0.113.7", "198.51.100.1", "") == "203.0.113.7"
    assert client_address("203.0.113.7", "198.51.100.1", "10.0.0.0/8") == "203.0.113.7"


def test_trusted_proxy_uses_rightmost_untrusted_hop():
    trusted = "172.16.0.0/12, 10.0.0.5"
    assert client_address("172.18.0.3", "198.51.100.1", trusted) == "198.51.100.1"
    # Client-supplied left entries cannot override what the trusted proxy appended.
    assert client_address("172.18.0.3", "1.2.3.4, 198.51.100.1, 10.0.0.5", trusted) == "198.51.100.1"


def test_trusted_proxy_without_usable_client_gets_no_shared_bucket():
    trusted = "172.16.0.0/12"
    assert client_address("172.18.0.3", None, trusted) is None
    assert client_address("172.18.0.3", "", trusted) is None
    assert client_address("172.18.0.3", "172.18.0.9", trusted) is None
    assert client_address("172.18.0.3", "1.2.3.4, not-an-ip", trusted) is None
    assert client_address(None, "1.2.3.4", trusted) is None


def test_address_normalisation():
    assert client_address("::ffff:203.0.113.7", None, "") == "203.0.113.7"
    assert client_address("172.18.0.3", "203.0.113.7:51234", "172.16.0.0/12") == "203.0.113.7"
    assert client_address("172.18.0.3", "[2001:db8::1]:443", "172.16.0.0/12") == "2001:db8::/64"
    assert client_address("2001:db8:1:2:aaaa::1", None, "") == "2001:db8:1:2::/64"
    assert client_address("2001:db8:1:2:bbbb::9", None, "") == "2001:db8:1:2::/64"


def test_non_ip_peer_keeps_raw_key():
    assert client_address("testclient", "1.2.3.4", "") == "testclient"


def test_hostname_entries_resolve_and_failures_trust_nothing(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "web":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.18.0.3", 0))]
        raise socket.gaierror("unknown")

    monkeypatch.setattr(client_ip.socket, "getaddrinfo", fake_getaddrinfo)
    assert client_address("172.18.0.3", "198.51.100.1", "web") == "198.51.100.1"
    assert client_address("172.18.0.4", "198.51.100.1", "web") == "172.18.0.4"
    assert client_address("172.18.0.3", "198.51.100.1", "missing-host") == "172.18.0.3"
