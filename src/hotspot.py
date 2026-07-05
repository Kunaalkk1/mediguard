"""
hotspot.py -- optionally bring up a Wi-Fi access point on the Raspberry Pi so a
phone can join and open the dashboard, without any manual nmcli steps.

Controlled by environment (see .env):
  MEDIGUARD_HOTSPOT           1/true to start an AP at launch (default off)
  MEDIGUARD_HOTSPOT_SSID      network name       (default "MediGuard")
  MEDIGUARD_HOTSPOT_PASSWORD  WPA password       (default "mediguard123")
  MEDIGUARD_HOTSPOT_IFACE     wireless interface (default "wlan0")

This is entirely best-effort and non-fatal: it only runs on Linux with nmcli
(NetworkManager) present, and any failure just logs a warning and lets the rest
of the system carry on. Starting the AP needs root, so run main.py with sudo on
the Pi if you enable it.
"""

import os
import shutil
import subprocess
import sys


def _enabled() -> bool:
    return os.getenv("MEDIGUARD_HOTSPOT", "0").strip().lower() in {"1", "true", "yes", "on"}


def _hotspot_ip(iface: str):
    """Best-effort lookup of the AP's IPv4 address (usually 10.42.0.1)."""
    try:
        out = subprocess.run(
            ["nmcli", "-g", "IP4.ADDRESS", "device", "show", iface],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if out:
            return out.splitlines()[0].split("/")[0]
    except Exception:
        pass
    return None


def start_hotspot():
    """Start the Wi-Fi AP if enabled. Never raises."""
    if not _enabled():
        return
    if sys.platform != "linux":
        print("[hotspot] skipped: only supported on the Raspberry Pi (Linux)")
        return
    if shutil.which("nmcli") is None:
        print("[hotspot] skipped: nmcli (NetworkManager) not found")
        return

    ssid = os.getenv("MEDIGUARD_HOTSPOT_SSID", "MediGuard")
    password = os.getenv("MEDIGUARD_HOTSPOT_PASSWORD", "mediguard123")
    iface = os.getenv("MEDIGUARD_HOTSPOT_IFACE", "wlan0")

    print(f"[hotspot] starting access point '{ssid}' on {iface} ...")
    try:
        result = subprocess.run(
            ["nmcli", "device", "wifi", "hotspot",
             "ifname", iface, "ssid", ssid, "password", password],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        print("[hotspot] nmcli timed out; continuing without an AP")
        return
    except Exception as exc:
        print(f"[hotspot] unexpected error, continuing without an AP: {exc}")
        return

    if result.returncode == 0:
        ip = _hotspot_ip(iface)
        port = os.getenv("MEDIGUARD_PORT", "7801")
        where = f" -> open http://{ip}:{port}" if ip else ""
        print(f"[hotspot] access point '{ssid}' is up (password: {password}){where}")
    else:
        message = (result.stderr or result.stdout or "").strip()
        print(f"[hotspot] failed to start (run main.py with sudo?): {message}")
