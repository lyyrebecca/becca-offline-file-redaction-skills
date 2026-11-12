# Legal Privacy Cloak · v2.4.2

**Created by 李玥滢 (Li Yueying), [lyyrebecca](https://github.com/lyyrebecca).** An individually created AI-law course project; course submission as a group assignment does not imply joint development.

A Skill, fixed local engine and browser-based local workbench for Chinese legal-document de-identification. After installing dependencies, daily processing requires no external LLM or API key. Reversible de-identification is not legal anonymization.

[中文说明](README.md) · [Download](https://github.com/lyyrebecca/becca-offline-file-redaction-skills/releases/latest) · [Installation](docs/INSTALL.md) · [Verification scope](docs/VERIFICATION.md)

## New since the previous 2.0.1 release

- Select missed text and apply an exact-literal rule across the current batch; affected files must be reviewed again.
- Right-click to cancel one candidate with confirmation. Additional numeric/alphanumeric candidates are visible-text/OCR-only and unmasked by default.
- Optional encrypted local exact-term library, loaded by future tasks using the same passphrase; no semantic training or cross-case identity inference.
- Numbered image masks; jump to automatic candidates or remove/redraw manual rectangles.
- CSV/TSV, JSON/XML/LOG and restricted plain-text EML support, in addition to Office/PDF/images/UTF-8 text.
- One case per workbench batch by default; use separate tasks for separate cases.
- Versioned user runtimes, Windows launchers, native tool discovery, UTF-8 console handling and optional shortcuts.
- **2.4.2:** delivery blockers are explained per file, with issue codes and navigation back to review. Unknown issues fail closed; soft confirmations cannot bypass structural export gates.

## Formats and restoration

DOCX/XLSX/PPTX, PDF, PNG/JPEG, UTF-8 TXT/Markdown/CSV/TSV/JSON/XML/LOG, and single-part `text/plain` EML. Multipart/HTML/attachment emails are blocked; EML output is a non-sendable `X-LPC-*` review copy. Unsupported formats and structures are blocked rather than silently skipped.

Office displays `***`; edited-copy restoration requires intact markers in the original text units/offsets and other consistency checks. Text formats use full internal placeholders. PDF/images restore original bytes only. AES-256-GCM and scrypt protect originals/mappings in a separate vault.

## Install and run

Python **3.11 or 3.12** required; 3.12 recommended. Download and extract `legal-privacy-cloak-2.4.2.zip`, then enter its `legal-privacy-cloak` directory.

Windows 10/11:

```powershell
py -3.12 scripts\bootstrap.py
scripts\run.cmd doctor
```

Double-click `信息隐身衣.cmd`. Optional shortcut: `py -3.12 scripts\install.py --shortcut desktop`.

macOS:

```bash
python3.12 scripts/bootstrap.py
chmod +x scripts/run.sh 信息隐身衣.command
scripts/run.sh doctor
```

Double-click `信息隐身衣.command`; optionally run `python3.12 scripts/install.py --app`.

Tesseract with `chi_sim` and `eng`, plus Poppler, are needed for OCR/PDF. LibreOffice is optional for PPT-to-raster-PDF. These tools and model/runtime binaries are not bundled. Bootstrap needs network access or prepared dependencies; explicit `--rule-only` mode does not provide the Chinese model's capabilities.

## Workflow and scope

Choose purpose → import one case → review every file locally → resolve blockers and export. Only selected `share/` outputs are candidate deliverables; never share the whole task, vault, passphrase or restored originals. `CHECKED` is not a guarantee of zero misses or legal permission to disclose. Faces, signatures, QR codes and indirect identification need human review.

Windows/macOS native CI is tracked in [Actions](https://github.com/lyyrebecca/becca-offline-file-redaction-skills/actions); current verification is documented separately from old 2.0.1 screenshots. Linux code paths do not establish Linux desktop GUI acceptance; no mobile version is provided.

Credit appears only in the app/docs, not in processed legal documents. Third-party notices and layered licensing remain unchanged: [LICENSE](LICENSE), [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md). Report synthetic reproductions only, not real case data.
