#!/bin/sh
set -eu
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON=${LPC_PYTHON:-"${XDG_DATA_HOME:-$HOME/.local/share}/legal-privacy-cloak/venv/bin/python"}
if [ ! -x "$PYTHON" ]; then
  printf '%s\n' '本地运行环境未安装。请在独立终端运行 scripts/install.py --with-deps。' >&2
  exit 1
fi
exec "$PYTHON" "$HERE/lpc.py" "$@"
