#!/usr/bin/env bash
#
# pi_setup.sh -- one-time network setup for a MediGuard Raspberry Pi.
#
# It does three things, all idempotent (safe to re-run):
#   1. Sets the hostname to "mediguard" so the Pi answers to mediguard.local.
#   2. Makes sure avahi-daemon (mDNS/Bonjour) is installed and running, so
#      mediguard.local resolves for every phone/PC on the same network.
#   3. Enables RealVNC so you can view the Pi's desktop from another PC/Android
#      with the free RealVNC Viewer app, at  mediguard.local.
#
# Run it once on the Pi:   sudo bash scripts/pi_setup.sh
#
set -euo pipefail

HOSTNAME_NEW="mediguard"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run with sudo:  sudo bash scripts/pi_setup.sh" >&2
  exit 1
fi

echo "==> 1/3  Setting hostname to '${HOSTNAME_NEW}'"
CURRENT="$(hostname)"
if [[ "${CURRENT}" != "${HOSTNAME_NEW}" ]]; then
  # raspi-config's non-interactive helper updates /etc/hostname and /etc/hosts.
  if command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_hostname "${HOSTNAME_NEW}"
  else
    hostnamectl set-hostname "${HOSTNAME_NEW}"
    sed -i "s/127.0.1.1.*/127.0.1.1\t${HOSTNAME_NEW}/" /etc/hosts || true
  fi
  echo "    hostname changed ${CURRENT} -> ${HOSTNAME_NEW} (takes effect after reboot)"
else
  echo "    already '${HOSTNAME_NEW}'"
fi

echo "==> 2/3  Ensuring avahi-daemon (mDNS) is installed and enabled"
if ! command -v avahi-daemon >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y avahi-daemon
fi
systemctl enable --now avahi-daemon
echo "    avahi-daemon active -> mediguard.local will resolve on the LAN"

echo "==> 3/3  Enabling RealVNC server (remote desktop)"
if command -v raspi-config >/dev/null 2>&1; then
  # 0 = enable. Enables the RealVNC server that ships with Raspberry Pi OS.
  raspi-config nonint do_vnc 0
  echo "    RealVNC enabled -> connect to mediguard.local with RealVNC Viewer"
else
  echo "    raspi-config not found; enable VNC manually:"
  echo "      sudo apt-get install -y realvnc-vnc-server"
  echo "      sudo systemctl enable --now vncserver-x11-serviced"
fi

echo
echo "Done. Reboot to apply the hostname:   sudo reboot"
echo
echo "After reboot:"
echo "  * Dashboard:      http://mediguard.local:7801"
echo "  * Remote desktop: open RealVNC Viewer -> connect to  mediguard.local"
echo "  * SSH terminal:   ssh pi@mediguard.local"
