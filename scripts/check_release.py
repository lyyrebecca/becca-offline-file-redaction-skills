#!/usr/bin/env python3
"""Non-content structure, parity and cross-platform regression check.

This script never opens user case files. It runs on Windows, macOS and Linux and enforces
the invariants that broke on Windows before (``os.fchmod``, macOS-only pickers, missing
time zone data, bare ``tesseract`` on PATH, LF-only batch files).
"""
from pathlib import Path
import ast
import json
import os
import re
import sys

root = Path(__file__).resolve().parents[1]
errors: list[str] = []


def read(path: Path) -> str:
    return path.read_text("utf-8")


# 1. Every Python file must parse.
for path in (root / "scripts").rglob("*.py"):
    try:
        ast.parse(read(path))
    except SyntaxError:
        errors.append("SYNTAX:" + str(path.relative_to(root)))

# 2. Markdown links must resolve to files in the package.
for path in root.rglob("*.md"):
    for target in re.findall(r"\]\(([^)]+)\)", read(path)):
        if "://" in target or target.startswith(("#", "mailto:")):
            continue
        if not (path.parent / target.split("#")[0]).exists():
            errors.append("MISSING_LINK:" + str(path.relative_to(root)) + ":" + target)

# 3. Required payload, including the Windows launchers.
required = [
    "SKILL.md", "CHANGELOG.md", "agents/openai.yaml", "assets/brand-icon.jpg", "assets/ui-reference.png",
    "assets/ui/index.html", "assets/ui/app.js", "assets/ui/app.css", "assets/icon-256.png",
    "assets/icon.ico", "requirements.txt", "requirements-model.txt",
    "scripts/cloak/platform_support.py", "scripts/cloak/issues.py", "scripts/bootstrap.py", "scripts/install.py",
    "scripts/run.py", "scripts/run.cmd", "scripts/run.ps1", "scripts/run.sh",
    "信息隐身衣.cmd", "信息隐身衣.command",
    "tests/test_delivery_blockers.py", "tests/test_delivery_ui.js",
]
for name in required:
    if not (root / name).is_file():
        errors.append("MISSING:" + name)

# 4. POSIX executable bits only matter on POSIX; Windows checkouts cannot carry them.
if os.name != "nt":
    for name in ("scripts/run.sh", "信息隐身衣.command"):
        path = root / name
        if path.exists() and not path.stat().st_mode & 0o111:
            errors.append("NOT_EXECUTABLE:" + name)

# 5. Version and credit consistency.
brand = json.loads(read(root / "assets/brand.json"))
package = re.search(r'__version__\s*=\s*"([^"]+)"', read(root / "scripts/cloak/__init__.py"))
runtime = re.search(r'VERSION\s*=\s*"([^"]+)"', read(root / "scripts/runtime.py"))
versions = {"brand": brand.get("version"), "package": package and package.group(1),
            "runtime": runtime and runtime.group(1)}
if len({v for v in versions.values() if v}) != 1:
    errors.append("VERSION_MISMATCH:" + json.dumps(versions))
if brand.get("project_credit") != "制作者：李玥滢（lyyrebecca）":
    errors.append("PROJECT_CREDIT_MISMATCH")
if brand.get("project_credit") not in read(root / "assets/ui/index.html"):
    errors.append("PROJECT_CREDIT_MISSING")

if brand.get("author") != "李玥滢" or brand.get("github") != "lyyrebecca":
    errors.append("AUTHOR_MISMATCH")
ui_index = read(root / "assets/ui/index.html")
if f"版本 {brand.get('version')}" not in ui_index:
    errors.append("UI_VERSION_MISMATCH")
for relative in ("SKILL.md", "README.md", "README.en.md", "references/ui-design.md"):
    if "李玥滢" not in read(root / relative):
        errors.append("AUTHOR_MISSING:" + relative)

# 6. Windows launchers: CRLF line endings keep cmd.exe label handling reliable, and batch
#    files must stay ASCII because cmd parses them with the OEM code page.
for path in [root / "信息隐身衣.cmd", *(root / "scripts").glob("*.cmd")]:
    if not path.exists():
        continue
    raw = path.read_bytes()
    if b"\r\n" not in raw:
        errors.append("BATCH_WITHOUT_CRLF:" + path.name)
    if any(byte > 127 for byte in raw):
        errors.append("BATCH_NON_ASCII:" + path.name)
for path in (root / "scripts").glob("*.ps1"):
    if b"\r\n" not in path.read_bytes():
        errors.append("PS1_WITHOUT_CRLF:" + path.name)

# 7. Windows regressions that must not come back.
for path in (root / "scripts").rglob("*.py"):
    if path.name == "check_release.py":
        continue  # this file names the patterns it forbids
    text = read(path)
    relative = str(path.relative_to(root))
    if "os.fchmod" in text and not relative.endswith("platform_support.py"):
        errors.append("RAW_FCHMOD:" + relative)
    if "osascript" in text:
        errors.append("MACOS_ONLY_PICKER:" + relative)
    if "ZoneInfo(" in text and not relative.endswith("platform_support.py"):
        errors.append("DIRECT_ZONEINFO:" + relative)
    for module in ("fcntl", "termios", "pwd", "grp"):
        if re.search(r"^\s*(?:import|from)\s+" + module + r"\b", text, re.M) and \
                not relative.endswith("platform_support.py"):
            errors.append("POSIX_ONLY_IMPORT:" + relative + ":" + module)
    if "os.startfile" in text and not relative.endswith("platform_support.py"):
        errors.append("RAW_STARTFILE:" + relative)

formats = read(root / "scripts/cloak/formats.py")
for token in ("resolve_tool('tesseract')", "resolve_tool('pdftoppm')"):
    if token not in formats:
        errors.append("TOOL_RESOLUTION_MISSING:" + token)

# 8. Delivery feedback must consume the authoritative backend issue catalog, while the
#    export gate remains in the workflow and blocker labels never come from file HTML.
issues = read(root / "scripts/cloak/issues.py")
workflow = read(root / "scripts/cloak/workflow.py")
desktop = read(root / "scripts/cloak/desktop.py")
ui = read(root / "assets/ui/app.js")
for code in (
    "UNSUPPORTED_EMBEDDED_OR_DYNAMIC_PART", "UNSUPPORTED_BINARY_PART", "UNSUPPORTED_XML_TAIL",
    "SENSITIVE_FORMULA_BLOCKED", "SENSITIVE_REFERENCE_BLOCKED", "SENSITIVE_NUMERIC_WITH_FORMULAS",
    "XML_DTD_FORBIDDEN", "MULTIFRAME_IMAGE",
):
    if "'" + code + "'" not in issues:
        errors.append("ISSUE_CATALOG_MISSING:" + code)
if "blockers=set(i for f in job['files'] for i in f['issues'])-SOFT_ISSUES" not in workflow or \
        "if blockers:raise ValueError('UNRESOLVED_STRUCTURAL_BLOCKERS')" not in workflow:
    errors.append("STRUCTURAL_EXPORT_GATE_MISSING")
if "w.structural_blockers(j['files'])" not in desktop or \
        "w.required_soft_confirmations(j['files'])" not in desktop:
    errors.append("STRUCTURED_ISSUES_NOT_FROM_BACKEND")
for token in ("state.blockers", "data-blocker-file", "returnFirstBlocker", "esc(label)", "esc(b.message", "esc(b.code"):
    if token not in ui:
        errors.append("DELIVERY_UI_CONTRACT_MISSING:" + token)
if "confirmations:state.soft_confirmations||[]" not in ui or \
        "confirmations:['ENTITY_AMBIGUITY_REVIEW'" in ui:
    errors.append("FRONTEND_SOFT_ISSUE_COPY_OR_MISSING_BACKEND_FIELD")

# 9. The Chinese model must not be a hard requirement of the base install, so a blocked
#    GitHub download cannot abort the whole bootstrap.
base = read(root / "requirements.txt")
if "github.com" in base:
    errors.append("MODEL_URL_IN_BASE_REQUIREMENTS")
if "tzdata" not in base:
    errors.append("TZDATA_MISSING_FOR_WINDOWS")

print(json.dumps({
    "status": "PASS" if not errors else "FAIL",
    "version": brand.get("version"),
    "platform": sys.platform,
    "python_files": len(list((root / "scripts").rglob("*.py"))),
    "errors": errors,
}, ensure_ascii=False, indent=2))
raise SystemExit(bool(errors))
