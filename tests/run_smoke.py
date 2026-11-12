"""One-command self check for a real Windows (or macOS/Linux) machine.

Usage
-----
    py -3.12 tests\run_smoke.py

It uses **synthetic** documents only, never reads user material, never touches the
network, and writes everything into a temporary folder that it deletes afterwards.
Pass ``--keep`` to keep the folder for inspection.

What is verified
----------------
* Windows launchers exist, use CRLF and stay ASCII (cmd.exe constraints).
* ``os.fchmod``-free atomic vault writes work in a path containing spaces and Chinese.
* Single-instance locking, time zone fallback, tool discovery.
* Full pipeline: scan -> review -> redact -> verify -> restore (byte identical).
* Optional OCR/PDF stage only when Tesseract with chi_sim+eng is present.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]

from cloak import platform_support as ps  # noqa: E402
from cloak.vault import open_vault, seal  # noqa: E402

PW = "SYNTHETIC-windows-smoke-2026"
results: list[dict] = []


def step(name: str):
    def wrap(function):
        try:
            detail = function() or ""
            results.append({"step": name, "status": "PASS", "detail": str(detail)[:300]})
            print(f"[PASS] {name}" + (f" · {detail}" if detail else ""), flush=True)
        except Exception as exc:  # noqa: BLE001 - report, never hide
            results.append({"step": name, "status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"[:300]})
            print(f"[FAIL] {name} · {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
        return function
    return wrap


def main() -> int:
    ps.configure_stdio()
    keep = "--keep" in sys.argv
    print("信息隐身衣 · 本机自检（仅使用合成样本）")
    print(f"平台：{ps.PLATFORM_LABEL} · Python {sys.version.split()[0]} · 文件系统编码 {sys.getfilesystemencoding()}")
    print(f"标准输出编码：{getattr(sys.stdout, 'encoding', 'unknown')}")
    home = Path(tempfile.mkdtemp(prefix="lpc-smoke-"))

    @step("启动器文件（CRLF / ASCII）")
    def launchers():
        checked = []
        for name in ("信息隐身衣.cmd", "scripts/run.cmd", "scripts/run.ps1"):
            raw = (ROOT / name).read_bytes()
            assert b"\r\n" in raw, name + " 缺少 CRLF"
            if name.endswith(".cmd"):
                assert all(byte < 128 for byte in raw), name + " 含非 ASCII 字符"
            checked.append(name)
        return ", ".join(checked)

    @step("加密保险库写入（无 fchmod、含空格与中文路径）")
    def vault():
        target = home / "任务 空格" / "private" / "task.lpcv"
        seal(target, {"task": "smoke", "files": []}, PW)
        assert open_vault(target, PW)["task"] == "smoke"
        return str(target)

    @step("原子覆盖写入")
    def atomic():
        target = home / "报告.json"
        ps.atomic_write(target, b'{"a":1}')
        ps.atomic_write(target, b'{"a":2}')
        assert json.loads(target.read_text())["a"] == 2

    @step("单实例锁")
    def locking():
        first, second = ps.FileLock(home / "app.lock"), ps.FileLock(home / "app.lock")
        assert first.acquire()
        try:
            assert not second.acquire(), "同一锁被两个实例取得"
        finally:
            first.release()
        assert second.acquire()
        second.release()

    @step("时区（Windows 无 IANA 数据时的回退）")
    def timezone_check():
        from datetime import datetime, timedelta
        assert datetime.now(ps.shanghai_tz()).utcoffset() == timedelta(hours=8)

    @step("外部工具探测")
    def tools():
        status = ps.tool_status()
        languages = ps.tesseract_languages()
        return f"tesseract={status['tesseract']} chi_sim={'chi_sim' in languages} pdftoppm={status['pdftoppm']} soffice={status['soffice']}"

    @step("依赖与识别模式")
    def doctor():
        import importlib
        report = importlib.import_module("lpc").doctor()
        assert report["status"] == "READY", report.get("warnings")
        assert report["platform"] == ps.PLATFORM_LABEL
        return f"ner={report['ner']} ocr={report['ocr_status']}"

    # ------------------------------------------------------------------ pipeline
    from cloak.workflow import scan, review_update, redact, verify, restore, SOFT_ISSUES

    def pipeline(label: str, paths: list[Path]):
        workspace = home / ("任务-" + label)
        scan(paths, workspace, PW)
        job = open_vault(workspace / "private" / "task.lpcv", PW)
        review_update(job, confirmations=sorted(SOFT_ISSUES))
        seal(workspace / "private" / "task.lpcv", job, PW)
        exported = redact(workspace, PW)
        checked = verify(workspace, PW)
        assert exported["status"] == "CHECKED", exported.get("verification")
        assert checked["status"] == "CHECKED", checked
        for index, source in enumerate(paths):
            restored = home / f"restored-{label}-{index}{source.suffix}"
            restore(workspace, PW, restored, index=index)
            assert restored.read_bytes() == source.read_bytes(), source.name + " 原件恢复不一致"
        share = workspace / "share"
        outputs = sorted(p.name for p in share.iterdir() if p.is_file())
        assert outputs, "没有生成交付候选"
        return f"{len(paths)} 份材料 · 输出 {len(outputs)} 个文件"

    @step("文本类流程：TXT / MD / CSV")
    def text_pipeline():
        files = home / "text"
        files.mkdir(parents=True, exist_ok=True)
        samples = {
            "sample.txt": "原告：赵测试，电话：13812345678，邮箱：fixture@example.test",
            "sample.md": "# 合成材料\n\n被告：合成示例科技有限公司，账户：6222021234567890123",
            "sample.csv": "姓名,联系电话,身份证号\n赵测试,13812345678,110101199001010010\n",
        }
        paths = []
        for name, body in samples.items():
            target = files / name
            target.write_text(body, "utf-8-sig" if name.endswith(".csv") else "utf-8")
            paths.append(target)
        return pipeline("text", paths)

    @step("Office 流程：DOCX / XLSX / PPTX")
    def office_pipeline():
        try:
            from fixtures import docx, xlsx, pptx
        except ImportError as exc:
            raise RuntimeError("缺少测试依赖（pip install -r requirements-test.txt）") from exc
        files = home / "office"
        files.mkdir(parents=True, exist_ok=True)
        docx(files / "sample.docx")
        xlsx(files / "sample.xlsx")
        pptx(files / "sample.pptx")
        return pipeline("office", [files / "sample.docx", files / "sample.xlsx", files / "sample.pptx"])

    @step("图像/PDF 流程：PNG / PDF（需要 Tesseract）")
    def media_pipeline():
        languages = ps.tesseract_languages()
        if not (ps.resolve_tool("tesseract") and ps.resolve_tool("pdftoppm") and {"chi_sim", "eng"}.issubset(languages)):
            raise RuntimeError("跳过：未安装 Tesseract（chi_sim/eng）或 Poppler，属于本机可选依赖")
        try:
            from fixtures import image
        except ImportError as exc:
            raise RuntimeError("缺少测试依赖（pip install -r requirements-test.txt）") from exc
        files = home / "media"
        files.mkdir(parents=True, exist_ok=True)
        png = files / "sample.png"
        png.write_bytes(image())
        from PIL import Image
        with Image.open(png) as handle:
            handle.convert("RGB").save(files / "scan.pdf", "PDF", resolution=150)
        return pipeline("media", [png, files / "scan.pdf"])

    failures = [row for row in results if row["status"] == "FAIL"]
    summary = {"platform": ps.PLATFORM_LABEL, "python": sys.version.split()[0],
               "passed": len(results) - len(failures), "failed": len(failures), "steps": results}
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    if keep:
        print(f"自检目录已保留：{home}")
    else:
        shutil.rmtree(home, ignore_errors=True)
    print("\n结论：" + ("通过" if not failures else f"有 {len(failures)} 项未通过，请把上面的输出发给维护者"))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
