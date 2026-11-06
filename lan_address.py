"""Find the local IPv4 address used by Windows for outbound traffic."""

import ipaddress
import socket


def detect_lan_ip():
    """Ask routing for a usable local IPv4 address without sending network data."""
    try:
        # UDP connect chooses an interface locally. No packet is sent.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("192.0.2.1", 9))
            address = connection.getsockname()[0]
        parsed = ipaddress.ip_address(address)
        if not (
            parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_unspecified
            or parsed.is_multicast
        ):
            return address
    except OSError:
        pass
    return None
