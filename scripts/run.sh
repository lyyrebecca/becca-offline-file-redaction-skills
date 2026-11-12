#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# GUI-launched macOS processes may have a minimal PATH. Add conventional Homebrew locations when present.
for candidate in /opt/homebrew/bin /usr/local/bin /usr/bin /bin; do
  if [ -d "$candidate" ]; then PATH="$candidate:$PATH"; fi
done
export PATH
PYTHON=
for candidate in "${LPC_BOOTSTRAP_PYTHON:-}" python3.12 python3.11 python3; do
  [ -n "$candidate" ] || continue
  command -v "$candidate" >/dev/null 2>&1 || continue
  if "$candidate" "$HERE/pyversion.py" >/dev/null 2>&1; then
    PYTHON=$candidate
    break
  fi
done
if [ -z "$PYTHON" ]; then
  printf '%s\n' '未找到 Python 3.11/3.12。请安装后运行 scripts/bootstrap.py；macOS 可用 python.org 安装包或 brew install python@3.12。' >&2
  exit 2
fi
exec "$PYTHON" "$HERE/run.py" "$@"
