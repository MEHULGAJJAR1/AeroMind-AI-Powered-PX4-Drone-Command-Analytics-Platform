#!/usr/bin/env bash
set -euo pipefail
PX4_DIR="${PX4_DIR:-}"
if [[ -z "$PX4_DIR" ]]; then echo 'Set PX4_DIR to your PX4-Autopilot checkout.' >&2; exit 2; fi
PX4_DIR="$(cd "$PX4_DIR" && pwd)"
if [[ ! -f "$PX4_DIR/Makefile" ]]; then echo "No PX4 Makefile found at $PX4_DIR" >&2; exit 2; fi
TARGET="${PX4_SITL_TARGET:-}"
if [[ -z "$TARGET" ]]; then
  TARGETS="$(make -C "$PX4_DIR" px4_sitl list_vmd_make_targets 2>&1 || true)"
  if grep -Eq '(^|[^[:alnum:]_])gz_x500([^[:alnum:]_]|$)' <<<"$TARGETS"; then
    TARGET=gz_x500
  elif grep -Eq '(^|[^[:alnum:]_])gazebo-classic_iris([^[:alnum:]_]|$)' <<<"$TARGETS"; then
    TARGET=gazebo-classic_iris
  else
    echo 'No recognized default SITL target was reported by this checkout.' >&2
    echo 'Targets reported by PX4:' >&2
    echo "$TARGETS" >&2
    echo 'Set PX4_SITL_TARGET to one of the targets listed above and rerun.' >&2
    exit 3
  fi
fi
printf 'Launching PX4 target "%s" from %s\n' "$TARGET" "$PX4_DIR"
printf 'The application connects using PX4_SYSTEM_ADDRESS=%s (configured separately).\n' "${PX4_SYSTEM_ADDRESS:-udp://:14540}"
exec make -C "$PX4_DIR" px4_sitl "$TARGET"
