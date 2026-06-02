#!/usr/bin/env bash
# Build the python-rtmidi wheel and place it in the extension's wheels/ folder so
# it can be bundled via blender_manifest.toml.
#
# Why not Blender's Python? python-rtmidi 1.5.8 builds with Meson, which needs a
# CPython 3.13 that ships dev headers. Blender's *embedded* Python has none, so we
# build with a full CPython 3.13 (e.g. Homebrew's python@3.13). The resulting
# cp313 arm64 wheel is ABI-compatible with Blender's Python 3.13.
set -euo pipefail

OUT="$(cd "$(dirname "$0")/.." && pwd)/extension/steinway_midi_piano/wheels"
mkdir -p "$OUT"

has_headers() {
  "$1" - <<'PY' 2>/dev/null
import os, sys, sysconfig
hdr = os.path.join(sysconfig.get_path("include"), "Python.h")
sys.exit(0 if sys.version_info[:2] == (3, 13) and os.path.exists(hdr) else 1)
PY
}

PYBIN="${BUILD_PYTHON:-}"
if [ -z "$PYBIN" ]; then
  for cand in \
      /opt/homebrew/opt/python@3.13/bin/python3.13 \
      /usr/local/opt/python@3.13/bin/python3.13 \
      "$(command -v python3.13 || true)"; do
    if [ -n "$cand" ] && [ -x "$cand" ] && has_headers "$cand"; then
      PYBIN="$cand"
      break
    fi
  done
fi

if [ -z "$PYBIN" ]; then
  echo "ERROR: need a CPython 3.13 with dev headers (try: brew install python@3.13)" >&2
  exit 1
fi

echo "Building python-rtmidi wheel with: $PYBIN"
"$PYBIN" -m pip wheel python-rtmidi --no-deps -w "$OUT"

echo "Wheel(s) now in $OUT:"
ls -1 "$OUT"
