#!/usr/bin/env bash
set -u
PX4_DIR="${1:-${PX4_DIR:-}}"
if [[ -z "$PX4_DIR" ]]; then
  echo "Set PX4_DIR to an existing PX4-Autopilot checkout (or pass it as argument)."
  exit 2
fi
PX4_DIR="$(cd "$PX4_DIR" 2>/dev/null && pwd)" || { echo "PX4_DIR is not a directory."; exit 2; }
if [[ ! -d "$PX4_DIR/.git" ]]; then echo "Warning: $PX4_DIR is not a Git working tree."; fi
printf 'PX4 checkout: %s\n' "$PX4_DIR"
printf 'Revision: '
git -C "$PX4_DIR" describe --tags --always --dirty 2>/dev/null || echo 'unknown (git metadata unavailable)'
printf 'Branch: '
git -C "$PX4_DIR" branch --show-current 2>/dev/null || echo 'unknown'
for path in boards/px4/sitl Tools/simulation/gz Tools/simulation/gazebo-classic src/modules/mavlink msg; do
  if [[ -e "$PX4_DIR/$path" ]]; then printf 'Present: %s\n' "$path"; else printf 'Absent:  %s\n' "$path"; fi
done
if [[ -d "$PX4_DIR/msg" ]]; then
  printf '\nMessage definitions (sample):\n'
  find "$PX4_DIR/msg" -type f -name '*.msg' -print 2>/dev/null | sed "s#^$PX4_DIR/##" | sort | head -30
  printf 'Total .msg files: '
  find "$PX4_DIR/msg" -type f -name '*.msg' 2>/dev/null | wc -l
fi
if command -v make >/dev/null 2>&1 && [[ -f "$PX4_DIR/Makefile" ]]; then
  printf '\nAvailable SITL/simulator targets reported by this checkout:\n'
  make -C "$PX4_DIR" px4_sitl list_vmd_make_targets 2>&1 || echo 'Target enumeration failed; see PX4 prerequisites/build output above.'
else
  echo '\nCannot enumerate make targets: GNU make or the PX4 Makefile is unavailable.'
fi
printf '\nGazebo executable: '; command -v gz || true
printf 'Gazebo Classic executable: '; command -v gazebo || true
printf '\nThis inspector reads PX4 files and build targets only; it does not modify PX4 source.\n'
