#!/usr/bin/env bash
# Build baxters-hot-rod-tuner.deb per the Phase A1 packaging contract.
# Builds only. Does NOT install -- install/purge testing belongs in the VM
# harness (A2), never on the dev box (Article XIV: fans, hardware, one seat).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

HERE="$PWD"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

PKG=baxters-hot-rod-tuner
DEST="$STAGE/opt/baxters/hot-rod-tuner"

mkdir -p "$DEST"
cp -a packaging/DEBIAN "$STAGE/DEBIAN"
mkdir -p "$STAGE/usr/share/applications" "$STAGE/lib/udev/rules.d"
cp -a packaging/usr/share/applications/. "$STAGE/usr/share/applications/"
cp -a packaging/lib/udev/rules.d/. "$STAGE/lib/udev/rules.d/"

# Payload: source only. No build artifacts, no logs, no Windows launchers.
for item in src run.sh requirements.txt pyproject.toml assets hrt_floater.py; do
    cp -a "$item" "$DEST/"
done
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -name '*.pyc' -delete 2>/dev/null || true
chmod 0755 "$DEST/run.sh"

# Fail loudly if the .desktop points at an icon that is not in the payload.
ICON=$(sed -n 's|^Icon=/opt/baxters/hot-rod-tuner/||p' "$STAGE/usr/share/applications/$PKG.desktop")
if [ -n "$ICON" ] && [ ! -f "$DEST/$ICON" ]; then
    echo "FATAL: .desktop Icon= points at '$ICON' which is not in the payload" >&2
    exit 1
fi

# Debian policy requires /usr/share/doc/<pkg>/copyright.
mkdir -p "$STAGE/usr/share/doc"
cp -a packaging/usr/share/doc/. "$STAGE/usr/share/doc/"
[ -s "$STAGE/usr/share/doc/baxters-hot-rod-tuner/copyright" ] || { echo "FATAL: copyright file missing or empty" >&2; exit 1; }

OUT="$HERE/dist"
mkdir -p "$OUT"

# --- payload hygiene (added 2026-09-24 by the packaging agent) --------------
# Files inherit the BUILD USER's umask. On this box that is 0002, so payload
# arrived group-writable and dpkg installed it that way -- meaning any member
# of the installing group could edit an installed program. An audit of the
# built .deb files found this in ten of the twelve hand-written packagers; none
# of them normalised modes. `go-w` is surgical: it strips group and other write
# and leaves read and EXECUTE alone, so run.sh and binaries keep working (a
# blanket chmod 0644 would break them).
chmod -R go-w "$STAGE"
# Editor history and build-machine bytecode are not product. .bak files put a
# second, older copy of shipped code on a user's machine; __pycache__ carries
# absolute build paths and can be stale against the .py beside it.
find "$STAGE" -name '*.bak' -delete 2>/dev/null || true
find "$STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
if [ -n "$(find "$STAGE" \( -type f -o -type d \) -perm -g+w -print -quit 2>/dev/null)" ]; then
    echo "FATAL: group-writable entries remain in the payload" >&2
    exit 1
fi
dpkg-deb --root-owner-group --build "$STAGE" "$OUT/${PKG}_1.0.0_all.deb" >/dev/null
echo "built: $OUT/${PKG}_1.0.0_all.deb"
