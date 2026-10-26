# Becca Offline File Redaction Skills

Chinese product name: **终极·贝卡的文件脱敏离线部署软件 skills**. Aliases: 信息隐身衣 / Becca File Redaction. Skill invocation: `$legal-privacy-cloak`.

A local-first document de-identification workflow for legal materials: deterministic rules, Chinese spaCy NER, Tesseract OCR, local human review, conservative matter grouping, document adapters, teaching-slide cleanup, AI-readable Markdown and encrypted restoration.

**Verified desktop environment: macOS and Python 3.12.** This is a Skill plus a fixed local engine and lightweight macOS launcher, not a self-contained cross-platform installer. Runtime dependencies and models must be prepared first; initial setup uses the network. Routine document processing does not call an external LLM API.

## Formats and workflow

- DOCX: text runs, tables, headers/footers, footnotes, comments, tracked and hidden content.
- XLSX: cells, hidden sheets, comments, attributes, formula checks; sensitive dependencies block rather than silently breaking calculations.
- PPTX: text and embedded images; student copies remove speaker notes, comments, hidden slides and unreachable package parts.
- PDF/scans: render, OCR, pixel masks and raster reconstruction; original searchable text is intentionally not retained.
- PNG/JPEG: solid pixel masks and metadata-clean re-encoding.
- UTF-8 TXT/Markdown: consistent placeholders.

Choose a role and purpose → import → confirm matter assignments → review text and images locally → export and verify → open the delivery folder. Unknown or unsupported content is not reported as passed.

## Setup

```bash
git clone https://github.com/lyyrebecca/becca-offline-file-redaction-skills.git
cd becca-offline-file-redaction-skills
brew install python@3.12 tesseract tesseract-lang poppler
"$(brew --prefix python@3.12)/bin/python3.12" scripts/install.py --with-deps --app
```

Open `~/Applications/信息隐身衣.app`. Optional raster PDF export from slides requires local LibreOffice. Existing installations are not overwritten automatically. See [installation](docs/INSTALL.md), [Chinese guide](开始使用.md) and [verification evidence](docs/VERIFICATION.md).

## Privacy and limits

No automatic upload, cloud OCR fallback or document analysis API. Originals and exact recovery mappings stay in the encrypted local vault. Real source text, passwords and mappings must not be copied into chats or public issues. Public screenshots use synthetic materials only.

Manual review remains required. No promise of zero misses, legal anonymization, automatic face/QR recognition, semantic case merging, multi-case splitting or pixel-perfect Office layout. Reversible pseudonymization is not legal anonymization. PDF/image recovery returns the original rather than merging external edits.

The output page has an explicit **open delivery folder** link plus copy-path fallback. Share only the required contents of `share/`, not the vault or restored files.

Maintainer: [lyyrebecca](https://github.com/lyyrebecca) · WeChat `shirebeccaha` · `1849883220@qq.com`.

Licensing follows per-component notices, not a blanket MIT grant over dependencies, reference materials and supplied artwork. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md).
