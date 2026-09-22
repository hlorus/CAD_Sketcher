#!/bin/sh
# Run testing/gui_smoke.py in a private headless compositor: a real GUI (so draw
# handlers and gizmos run) that never appears on the desktop. Needs the addon
# installed as bl_ext.user_default.CAD_Sketcher into $BL_RES; see CLAUDE.md.
#
#   BL_RES=$PWD/.bltest/res sh scripts/run_gui_smoke.sh
set -e
WT=$(cd "$(dirname "$0")/.." && pwd)
BL_RES=${BL_RES:-$WT/.bltest/res}
NAME="cad-smoke-$$"

dbus-run-session -- mutter --headless --no-x11 --wayland-display="$NAME" \
    --virtual-monitor 1920x1080 >/dev/null 2>&1 &
trap "pkill -f '^mutter --headless.*$NAME'" EXIT
until [ -S "$XDG_RUNTIME_DIR/$NAME" ]; do sleep 0.2; done

LOG=$(mktemp)
env -u DISPLAY WAYLAND_DISPLAY="$NAME" timeout 180 flatpak run \
    --nosocket=x11 --socket=wayland --filesystem="$WT" \
    --env=BLENDER_USER_RESOURCES="$BL_RES" org.blender.Blender \
    --factory-startup --python "$WT/testing/gui_smoke.py" >"$LOG" 2>&1 || true
cat "$LOG"

# Blender swallows exceptions raised inside draw handlers and gizmos: it prints
# them and carries on, so the steps above can all "pass" while the viewport is
# broken. Any traceback at all is a failure.
if grep -q "Traceback (most recent call last)" "$LOG"; then
    echo "SMOKE FAILED: traceback during the run" >&2
    exit 1
fi
grep -q "^SMOKE OK" "$LOG" || { echo "SMOKE FAILED: did not complete" >&2; exit 1; }
echo "smoke: clean"
