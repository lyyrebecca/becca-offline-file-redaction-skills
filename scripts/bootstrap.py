#!/usr/bin/env python3
"""Create this Skill's versioned local runtime; never reads user documents.

Windows-first install strategy
------------------------------
1. If the machine Python already has spaCy 3.8 and the Chinese model, the runtime venv is
   created with ``--system-site-packages`` and no download is attempted at all. This is the
   usual fix when a proxy blocks the GitHub release download.
2. Otherwise packages come from PyPI, retried against Chinese mirrors.
3. The Chinese model is accepted from, in order: the venv itself, a wheel in ``vendor/``,
   the official release URL, an optional ``LPC_MODEL_URL``, then public GitHub proxies.
4. If none of that works the user can explicitly continue in rule-only mode; the workbench
   then shows a visible notice and requires an extra review confirmation.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import venv
from pathlib import Path
from runtime import read_config, runtime_home, runtime_python, write_config
from cloak import platform_support as ps

MODEL_VERSION = "zh_core_web_sm-3.8.0"
MODEL_FILE = MODEL_VERSION + "-py3-none-any.whl"
MODEL_URL = "https://github.com/explosion/spacy-models/releases/download/" + MODEL_VERSION + "/" + MODEL_FILE
# Public mirrors of GitHub release assets. Availability changes over time, so they are only
# tried after the official URL and never required for success.
MODEL_MIRRORS = [
    "https://ghproxy.net/" + MODEL_URL,
    "https://gh-proxy.com/" + MODEL_URL,
    "https://ghfast.top/" + MODEL_URL,
]
INDEX_MIRRORS = [
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://mirrors.cloud.tencent.com/pypi/simple",
]


def say(message: str) -> None:
    print(message, flush=True)


def ensure_launcher_permissions(skill_root: Path) -> None:
    """ZIP extractors and cloud drives often drop POSIX executable bits.

    Restoring them here means a freshly unzipped macOS package can still be started by
    double-clicking 信息隐身衣.command after the user runs bootstrap once.
    """
    if os.name == "nt":
        return
    for name in ("scripts/run.sh", "信息隐身衣.command"):
        path = skill_root / name
        try:
            mode = path.stat().st_mode
            if path.is_file() and not mode & 0o111:
                path.chmod(mode | 0o755)
                say(f"已恢复启动器可执行权限：{name}")
        except OSError:
            pass


def doctor(python: Path, skill_root: Path) -> dict | None:
    try:
        result = subprocess.run(
            [str(python), str(skill_root / "scripts" / "lpc.py"), "doctor"],
            capture_output=True, text=True, timeout=180, check=False,
            encoding="utf-8", errors="replace",
        )
        if result.returncode:
            return None
        value = json.loads(result.stdout)
        return value if isinstance(value, dict) else None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def venv_uses_system_site_packages(venv_dir: Path) -> bool:
    config = venv_dir / "pyvenv.cfg"
    try:
        text = config.read_text("utf-8", "replace").lower()
    except OSError:
        return False
    return "include-system-site-packages = true" in text


def remove_tree(path: Path) -> None:
    for attempt in range(3):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            # Windows keeps handles briefly after a failing child process exits.
            time.sleep(0.6 * (attempt + 1))
    shutil.rmtree(path, ignore_errors=True)


def create_venv(venv_dir: Path, reuse_system: bool) -> bool:
    if venv_dir.exists():
        remove_tree(venv_dir)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    say("正在创建独立本机 Python 环境（只安装软件依赖，不读取任何文档）。")
    say(f"  复用系统已安装的包：{'是' if reuse_system else '否'}")
    try:
        venv.EnvBuilder(with_pip=True, system_site_packages=reuse_system,
                        symlinks=(os.name != "nt")).create(venv_dir)
    except (OSError, subprocess.SubprocessError) as exc:
        say(f"无法创建虚拟环境（{type(exc).__name__}）。请检查本机 Python 安装与目录权限。")
        return False
    return True


def system_has_model() -> bool:
    """True when the interpreter running bootstrap itself has spaCy 3.8 and the model."""
    probe = "import spacy,zh_core_web_sm,sys;sys.stdout.write(spacy.__version__)"
    try:
        result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                                timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip().startswith("3.8")


def run_pip(python: Path, args: list[str], label: str) -> bool:
    command = [str(python), "-m", "pip", "install", "--disable-pip-version-check",
               "--no-input", "--retries", "2", "--timeout", "90", *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800, check=False,
                                encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        say(f"  {label}：无法启动 pip。")
        return False
    if result.returncode:
        tail = [line for line in (result.stdout + result.stderr).strip().splitlines() if line.strip()][-6:]
        say(f"  {label}：失败。")
        for line in tail:
            say("    " + line[:220])
        return False
    say(f"  {label}：完成。")
    return True


def install_requirements(python: Path, requirements: Path, index_urls: list[str]) -> bool:
    if not requirements.is_file():
        say(f"缺少依赖清单：{requirements.name}")
        return False
    tried = []
    for index in [None, *index_urls]:
        label = "PyPI 官方源" if index is None else index
        if index and index in tried:
            continue
        tried.append(index)
        args = ["-r", str(requirements)]
        if index:
            args += ["--index-url", index]
        say(f"正在安装 Python 依赖（{label}）。首次安装需要网络。")
        if run_pip(python, args, f"依赖安装 · {label}"):
            return True
    return False


MODEL_LOAD_PROBE = (
    "import spacy;nlp=spacy.load('zh_core_web_sm',"
    "disable=['parser','tagger','attribute_ruler','lemmatizer']);assert nlp"
)


def model_present(python: Path) -> bool:
    """True only when the pipeline really loads; an importable wheel is not enough.

    zh_core_web_sm needs spacy-pkuseg for its Chinese tokenizer. Checking only
    ``import zh_core_web_sm`` used to report success while every later scan failed
    with LOCAL_NER_UNAVAILABLE.
    """
    try:
        result = subprocess.run([str(python), "-c", MODEL_LOAD_PROBE],
                                capture_output=True, timeout=180, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def model_package_present(python: Path) -> bool:
    try:
        result = subprocess.run([str(python), "-c", "import zh_core_web_sm"],
                                capture_output=True, timeout=180, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def ensure_model_dependencies(python: Path) -> bool:
    """The model wheel is installed with --no-deps; install its tokenizer runtime."""
    say("正在补齐中文模型的分词依赖 spacy-pkuseg（macOS 与 Windows 均需要）。")
    return run_pip(python, ["spacy-pkuseg>=1.0.0,<2.0.0"], "中文模型分词依赖")


def install_model(python: Path, skill_root: Path, extra_urls: list[str]) -> bool:
    if model_present(python):
        say("中文模型已可加载，无需下载。")
        return True
    # A leftover wheel installed with --no-deps is importable but unusable: repair it
    # in place instead of re-downloading a large model from a blocked GitHub release.
    if model_package_present(python) and ensure_model_dependencies(python) and model_present(python):
        say("已补齐分词依赖，中文模型现在可以加载，无需重新下载。")
        return True
    vendor = skill_root / "vendor"
    wheels = sorted(vendor.glob("zh_core_web_sm-*.whl")) + sorted(vendor.glob("zh-core-web-sm-*.whl"))
    candidates: list[tuple[str, str]] = []
    for wheel in wheels:
        candidates.append((f"本机 vendor 目录：{wheel.name}", str(wheel)))
    if os.environ.get("LPC_MODEL_URL"):
        candidates.append(("环境变量 LPC_MODEL_URL", os.environ["LPC_MODEL_URL"].strip()))
    candidates += [(f"自定义源：{url}", url) for url in extra_urls]
    candidates.append(("官方发布地址", (skill_root / "requirements-model.txt").read_text("utf-8").strip().splitlines()[-1]
                       if (skill_root / "requirements-model.txt").is_file() else MODEL_URL))
    candidates += [(f"镜像：{url.split('/')[2]}", url) for url in MODEL_MIRRORS]
    for label, source in candidates:
        say(f"正在获取中文模型（{label}）。")
        if run_pip(python, ["--no-deps", source], "中文模型"):
            if not model_present(python):
                ensure_model_dependencies(python)
            if model_present(python):
                return True
    return False


def describe(state: dict) -> None:
    say(f"本机运行环境：{state.get('status')} · 平台 {state.get('platform', '未知')} · Python {state.get('python', '')}")
    say(f"中文实体识别：{state.get('ner', 'UNKNOWN')}")
    say(f"OCR/PDF 工具：{state.get('ocr_status', 'UNKNOWN')}（Tesseract {state.get('programs', {}).get('tesseract')}，pdftoppm {state.get('programs', {}).get('pdftoppm')}）")
    for warning in state.get("warnings", []):
        say("提示：" + warning)
    for name, path in (state.get("tool_paths") or {}).items():
        if path:
            say(f"  {name}: {path}")


def main() -> int:
    ps.configure_stdio()
    parser = argparse.ArgumentParser(description="为当前 Skill 创建本机依赖环境，不读取待处理文档")
    parser.add_argument("--refresh", action="store_true", help="在已有环境中重新安装 requirements.txt")
    parser.add_argument("--reuse-system", action="store_true",
                        help="用系统已装的 spaCy 与中文模型创建环境（网络受限时的推荐做法）")
    parser.add_argument("--rule-only", action="store_true",
                        help="显式接受不含中文模型的规则模式；工作台会持续提示并增加复核项")
    parser.add_argument("--wheel", type=Path, action="append", default=[],
                        help="本机中文模型 wheel 路径，可重复")
    parser.add_argument("--model-url", action="append", default=[],
                        help="自定义中文模型下载地址，可重复")
    parser.add_argument("--index-url", action="append", default=[],
                        help="自定义 PyPI 源，可重复；默认在官方源失败后尝试国内镜像")
    args = parser.parse_args()

    if sys.version_info < (3, 11) or sys.version_info >= (3, 13):
        say("需要 Python 3.11 或 3.12；当前解释器不在本版验证范围内。")
        say("Windows 请安装 python.org 的 3.12，并在安装时勾选 “Add python.exe to PATH”。")
        return 2

    skill_root = Path(__file__).resolve().parents[1]
    ensure_launcher_permissions(skill_root)
    requirements = skill_root / "requirements.txt"
    venv_dir = runtime_home() / "venv"
    python = runtime_python()
    readable = ps.path_length_warning(python)
    if readable:
        say("提示：" + readable)

    if args.wheel:
        vendor = skill_root / "vendor"
        vendor.mkdir(exist_ok=True)
        for wheel in args.wheel:
            try:
                shutil.copy2(wheel, vendor / Path(wheel).name)
                say(f"已复制模型文件到 vendor：{Path(wheel).name}")
            except OSError as exc:
                say(f"无法复制模型文件（{type(exc).__name__}）：{wheel}")
                return 1

    if python.exists() and not args.refresh:
        current = doctor(python, skill_root)
        if current and current.get("status") == "READY":
            say("本机运行环境已就绪，无需重复安装。")
            describe(current)
            return 0

    reuse = args.reuse_system or system_has_model()
    reuse = reuse or venv_uses_system_site_packages(venv_dir)
    if python.exists() and venv_uses_system_site_packages(venv_dir) != reuse:
        say("运行环境的系统包复用方式与本次安装不一致，正在重建（只影响本 Skill 的软件运行目录）。")
        remove_tree(venv_dir)
    if not python.exists():
        if not create_venv(venv_dir, reuse):
            return 1
        if reuse:
            # The system already provides spaCy and the model: verify before touching the network.
            state = doctor(python, skill_root)
            if state and state.get("status") == "READY":
                say("已复用系统 Python 中已有的依赖与中文模型，无需联网下载。")
                write_config({"allow_rule_only": bool(args.rule_only), "install_mode": "system-site"})
                describe(state)
                return 0

    if not install_requirements(python, requirements, INDEX_MIRRORS + args.index_url):
        if not python.is_file():
            return 1
        state = doctor(python, skill_root)
        if not state or state.get("status") != "READY":
            say("依赖安装失败。请检查网络、证书与代理设置；原始法律文件未被处理。")
            say("可行做法：1) 换用可访问 PyPI 的网络；2) 先在本机 python 中安装依赖后运行 bootstrap.py --reuse-system；")
            say("          3) 把 zh_core_web_sm 的 wheel 放到 vendor/ 目录后重试。")
            return 1

    have_model = install_model(python, skill_root, args.model_url)
    if not have_model and not venv_uses_system_site_packages(venv_dir) and system_has_model():
        say("中文模型仅在系统 Python 中可用，正在重建可复用系统包的环境。")
        if create_venv(venv_dir, True):
            install_requirements(python, requirements, INDEX_MIRRORS + args.index_url)
            have_model = model_present(python)

    state = doctor(python, skill_root)
    rule_only_allowed = bool(args.rule_only)
    if state and state.get("ner") == "RULES_ONLY":
        rule_only_allowed = True
    if not have_model and not (state and state.get("ner") == "READY"):
        if not rule_only_allowed:
            say("中文实体识别模型仍未就绪。可选做法：")
            say("  1) 重新运行并指定本机模型文件：python -m scripts.bootstrap --wheel zh_core_web_sm-3.8.0-py3-none-any.whl")
            say("  2) 用系统已装的 spaCy 与模型：python scripts/bootstrap.py --reuse-system")
            say("  3) 显式接受仅规则的降级模式：python scripts/bootstrap.py --rule-only（复核时需要额外确认）")
            return 1
        say("已按你的选择启用规则模式：仅使用规则、词典与表格语境，不加载中文模型。")
        write_config({"allow_rule_only": True, "install_mode": "rule-only"})
    else:
        write_config({"allow_rule_only": False, "install_mode": "model" if have_model else "system-site"})

    state = doctor(python, skill_root)
    if not state or state.get("status") != "READY":
        say("依赖或中文模型仍未就绪；请检查安装环境后再运行。")
        return 1
    say("本机运行环境已就绪。")
    describe(state)
    say(f"运行时目录：{venv_dir}")
    if os.name == "nt":
        say("下一步：双击技能目录中的「信息隐身衣.cmd」打开工作台。")
    elif sys.platform == "darwin":
        say("下一步：双击「信息隐身衣.command」，或运行 scripts/run.sh desktop 打开工作台。")
        say("若系统提示开发者无法验证，先运行：xattr -dr com.apple.quarantine <技能目录>")
    else:
        say("下一步：运行 scripts/run.sh desktop 打开工作台。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
