"""
netinfo.py -- figure out how to reach the dashboard on the local network and
print a friendly banner at startup.

MediGuard no longer hosts its own Wi-Fi hotspot. The Pi joins whatever network
you put it on and the dashboard is served on 0.0.0.0, so it is reachable at:

  * http://mediguard.local:<port>   (via mDNS/avahi -- see scripts/pi_setup.sh)
  * http://<pi-lan-ip>:<port>       (fallback if .local doesn't resolve)

Nothing here needs root and it is entirely best-effort: if anything fails we
still print what we can and let the app carry on.
"""

import os
import socket


def primary_ip() -> str | None:
    """Best-effort LAN IPv4 of this machine.

    Opens a UDP socket "towards" a public address -- no packets are actually
    sent, it just makes the OS pick the outbound interface so we learn its IP.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def mdns_hostname() -> str:
    """The <hostname>.local name avahi publishes for this Pi."""
    host = socket.gethostname().split(".")[0]
    return f"{host}.local"


def print_access_banner(port: int) -> None:
    """Print every URL the dashboard can be opened from."""
    ip = primary_ip()
    port_suffix = "" if port == 80 else f":{port}"
    print("Dashboard is reachable at:")
    print(f"    http://{mdns_hostname()}{port_suffix}      (mDNS / bonjour name)")
    if ip:
        print(f"    http://{ip}{port_suffix}      (LAN IP fallback)")
    print(f"    http://localhost{port_suffix}      (on the Pi itself)")
