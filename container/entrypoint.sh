#!/bin/sh
# BlueZ : D-Bus hôte (Pi) si org.bluez est déjà là, sinon bluetoothd local.
# Sans interface HCI (VM Mac/Lima) on n'essaie pas en boucle.
set -eu

HOST_DBUS="${HOST_DBUS_SOCKET:-/host/dbus/system_bus_socket}"
LOCAL_DBUS="/run/dbus/system_bus_socket"

needs_bluetooth() {
  [ "${1:-}" = "scan" ] && return 0
  for _a in "$@"; do
    case "$_a" in
      --preview|--print-count) return 1 ;;
    esac
  done
  return 0
}

# Même format que ipixel.log : date ISO-8601 ms + fuseau, niveau, tag.
log() {
  _lvl="$1"
  shift
  printf '%s %-7s [%s] %s\n' "$(date +%Y-%m-%dT%H:%M:%S.%3N%:z)" "$_lvl" \
    "${IPIXEL_LOG_TAG:-${YOUTUBE_CHANNEL:-${IPIXEL_ADDRESS:-ipixel}}}" "$*" >&2
}

no_ble_msg() {
  log ERROR "Bluetooth indisponible : pas d'interface HCI Linux dans ce container."
  log ERROR "nerdctl sur Mac = VM sans puce BLE. Scan et panneau : Raspberry Pi 5."
  log ERROR "  sudo systemctl enable --now bluetooth"
  log ERROR "  nerdctl compose run --rm ipixel scan"
  log ERROR "Sur Mac sans BLE : nerdctl compose run --rm ipixel --print-count"
}

bluez_ok() {
  _addr="$1"
  [ -S "$_addr" ] || return 1
  DBUS_SYSTEM_BUS_ADDRESS="unix:path=${_addr}" \
    dbus-send --system --print-reply --dest=org.bluez \
    / org.freedesktop.DBus.Peer.Ping >/dev/null 2>&1
}

setup_bluez() {
  if bluez_ok "$HOST_DBUS"; then
    export DBUS_SYSTEM_BUS_ADDRESS="unix:path=${HOST_DBUS}"
    log INFO "BlueZ de l'hôte via ${HOST_DBUS}"
    return 0
  fi
  log INFO "Pas de BlueZ hôte, démarrage d'un bluetoothd local"

  if [ ! -s /etc/machine-id ]; then
    dbus-uuidgen >/etc/machine-id
  fi
  mkdir -p /run/dbus /var/lib/bluetooth
  if [ ! -S "$LOCAL_DBUS" ]; then
    dbus-daemon --system --nofork --nopidfile --nosyslog &
    _n=0
    while [ ! -S "$LOCAL_DBUS" ]; do
      _n=$((_n + 1))
      [ "$_n" -lt 30 ] || return 1
      sleep 0.1
    done
  fi
  export DBUS_SYSTEM_BUS_ADDRESS="unix:path=${LOCAL_DBUS}"

  bluetoothd --experimental --noplugin=sap --nodetach >/tmp/bluetoothd.log 2>&1 &
  _bt=$!
  sleep 0.4
  if ! kill -0 "$_bt" 2>/dev/null; then
    return 1
  fi
  bluez_ok "$LOCAL_DBUS"
}

if ! needs_bluetooth "$@"; then
  exec python -m ipixel "$@"
fi

if ! setup_bluez; then
  no_ble_msg
  exit 1
fi

rfkill unblock bluetooth >/dev/null 2>&1 || true
bluetoothctl power on >/dev/null 2>&1 || true

if [ "${1:-}" = "scan" ]; then
  shift
  if ! bluetoothctl list 2>/dev/null | grep -q Controller; then
    no_ble_msg
    exit 1
  fi
  exec python -m pypixelcolor --scan "$@"
fi

exec python -m ipixel "$@"
