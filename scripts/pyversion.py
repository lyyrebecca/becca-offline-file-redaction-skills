"""Exit 0 only for a Python version this Skill supports (3.11 or 3.12)."""
import sys
raise SystemExit(0 if (3, 11) <= sys.version_info < (3, 13) else 1)
