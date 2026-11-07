"""Client address for login throttling behind explicitly trusted proxies only.

The direct peer is used unless it matches TRUSTED_PROXIES. Only then is X-Forwarded-For
read right-to-left, skipping trusted hops; the first untrusted address is the client.
An outer HTTPS proxy must overwrite or append X-Forwarded-For: Next.js passes a
client-supplied value through unchanged, so without such a proxy the value is spoofable.
"""

import ipaddress
import socket
import time

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_ip(value: str) -> IPAddress | None:
    value = value.strip()
    if value.startswith("[") and "]" in value:  # "[v6]:port"
        value = value[1 : value.index("]")]
    elif value.count(":") == 1:  # "v4:port"
        value = value.split(":", 1)[0]
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


_RESOLVE_TTL_SECONDS = 60
_resolved: dict[str, tuple[float, tuple[Network, ...]]] = {}


def _resolve(host: str) -> tuple[Network, ...]:
    # Short TTL: a recreated container gets a new address and must stay trusted.
    now = time.monotonic()
    cached = _resolved.get(host)
    if cached and now - cached[0] < _RESOLVE_TTL_SECONDS:
        return cached[1]
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        networks = tuple(ipaddress.ip_network(str(info[4][0])) for info in infos)
    except (OSError, ValueError):
        networks = ()
    _resolved[host] = (now, networks)
    return networks


def trusted_networks(spec: str) -> list[Network]:
    """CIDRs, addresses or hostnames (resolved, e.g. the compose service "web")."""
    networks: list[Network] = []
    for item in (part.strip() for part in spec.split(",")):
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            networks.extend(_resolve(item))
    return networks


def _trusted(address: IPAddress, networks: list[Network]) -> bool:
    return any(address.version == net.version and address in net for net in networks)


def client_address(peer: str | None, forwarded_for: str | None, trusted_spec: str) -> str | None:
    """Return a throttle key for the client, or None when it cannot be determined safely."""
    if not peer:
        return None
    peer_ip = parse_ip(peer)
    if peer_ip is None:
        return peer  # Non-IP transports (tests, unix sockets) keep their raw peer key.
    networks = trusted_networks(trusted_spec)
    candidate: IPAddress | None = peer_ip
    if _trusted(peer_ip, networks):
        candidate = None
        for hop in reversed((forwarded_for or "").split(",")):
            hop_ip = parse_ip(hop)
            if hop_ip is None:
                break  # Malformed chain: do not guess further left.
            if not _trusted(hop_ip, networks):
                candidate = hop_ip
                break
    if candidate is None:
        return None
    if isinstance(candidate, ipaddress.IPv6Address):
        # One subscriber usually controls a whole /64; rotating within it must not reset the bucket.
        return str(ipaddress.ip_network(f"{candidate}/64", strict=False))
    return str(candidate)
