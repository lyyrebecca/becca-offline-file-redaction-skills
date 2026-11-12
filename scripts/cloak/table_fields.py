"""Conservative header-aware discovery for CSV/TSV and XLSX cells.

Headers only provide local field context; they are not a substitute for human review.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from .core import Hit, id_checksum
from .formats import S

_EMPTY = {"", "无", "未提供", "不详", "未知", "空", "-", "--", "—", "n/a", "null"}
_HEADER_PATTERNS = [
    ("WECHAT", r"(?:微信(?:账号|号码|号|id)|qq号|社交账号|社交平台账号)"),
    ("PHONE", r"(?:联系)?(?:电话(?:号码)?|手机(?:号码|号)?|移动电话)"),
    ("EMAIL", r"(?:电子)?邮箱|邮件地址"),
    ("PASSPORT", r"(?:护照|港澳通行证|台湾居民来往大陆通行证)(?:号码|编号|号)?"),
    ("CREDENTIAL", r"(?:律师)?执业证(?:号码|编号|号)|律师证号"),
    ("ID", r"(?:公民)?身份证(?:号码|号)|身份证件号|证件(?:号码|号)"),
    ("ACCOUNT", r"(?:(?:对方|收款|付款|银行|个人|对公))*账号(?:/卡号)?|银行卡号|卡号|(?:收款|银行|对方|对公)账户"),
    ("CREDIT_CODE", r"(?:统一社会信用代码|统一信用代码|信用代码)"),
    ("PERSON", r"(?:当事人|自然人|联系人|收款人|付款人|对方|证人|原告|被告|申请人|被申请人|法定代表人|代理人|律师|法官)?姓名|户名|承办律师|接收律师"),
    ("ORG", r"(?:公司|单位|机构|企业|开户行)(?:名称|全称)?"),
    ("ADDRESS", r"(?:通信|通讯|联系|家庭|常住|登记)?(?:住址|地址|住所地)"),
    ("CASE", r"(?:案件)?案号|案件编号"),
    ("CONTRACT", r"(?:合同|协议)编号"),
    ("VEHICLE", r"(?:车牌|车辆牌照|号牌)(?:号码|号)?"),
    ("PROPERTY", r"(?:不动产权证|产权证|房产证)(?:号码|编号|号)?"),
    ("DATE", r"(?:交易|登记|接收|付款|签署|出生)?日期|(?:交易|登记|接收|签署)时间|生日"),
    ("AMOUNT", r"(?:交易|合同|支付|收款)?金额|账户余额|价款|总价|工资|薪资|单价|本金|利息|成本|报价|保额"),
]
_HEADER_RE = [(kind, re.compile(pattern, re.I)) for kind, pattern in _HEADER_PATTERNS]


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().lower()
    return re.sub(r"[\s:：()（）\[\]【】_\-]+", "", value)


def header_kind(value: str):
    label = _norm(value)
    return next((kind for kind, pattern in _HEADER_RE if pattern.fullmatch(label)), None)


def _value_kind(value: str, kind: str, detector):
    value = unicodedata.normalize("NFKC", value).strip()
    if value.lower() in _EMPTY or len(value) > 120:
        return None
    compact = re.sub(r"[\s-]", "", value)
    if kind == "ID":
        if re.fullmatch(r"\d{17}[\dXx]", compact) or re.fullmatch(r"\d{15}", compact):
            return "ID"
        return None
    if kind == "PHONE":
        return kind if re.fullmatch(r"(?:\+?86)?1[3-9]\d{9}|0\d{9,11}", compact) else None
    if kind == "EMAIL":
        return kind if re.fullmatch(r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value) else None
    if kind == "WECHAT":
        return kind if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{4,29}", value) else None
    if kind == "PASSPORT":
        return kind if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{7,11}", compact) else None
    if kind == "CREDENTIAL":
        return kind if re.fullmatch(r"[A-Za-z0-9-]{8,24}", compact) else None
    if kind == "ACCOUNT":
        return kind if re.fullmatch(r"\d{8,30}", compact) else None
    if kind == "CREDIT_CODE":
        return kind if re.fullmatch(r"[0-9A-HJ-NPQRTUWXY]{18}", compact, re.I) else None
    if kind == "VEHICLE":
        return kind if re.fullmatch(r"[\u4eac津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-HJ-NP-Z0-9]{5,6}", compact, re.I) else None
    if kind == "PROPERTY":
        return kind if re.search(r"\d", value) and len(value) >= 5 else None
    if kind == "CASE":
        return kind if len(value) >= 5 and re.search(r"\d", value) and "号" in value else None
    if kind == "CONTRACT":
        return kind if len(value) >= 3 and re.search(r"[A-Za-z0-9\d]", value) else None
    if kind == "ADDRESS":
        return kind if len(value) >= 4 and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", value) else None
    if kind in ("PERSON", "ORG"):
        return kind if 2 <= len(value) <= 60 and re.search(r"[\u4e00-\u9fffA-Za-z]", value) else None
    if kind == "DATE":
        return kind if not detector.preserve_dates and re.fullmatch(r"\d{1,4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?", value) else None
    if kind == "AMOUNT":
        return kind if not detector.preserve_amounts and re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?)(?:元|万元|亿元)?", value) else None
    return None


def _csv_spans(text: str, delimiter: str):
    """Parse fields and source spans without losing quoted/escaped field offsets."""
    rows, row, i, n = [], [], 0, len(text)
    while i < n:
        if text[i] == '"':
            i += 1
            start = i
            out = []
            while i < n:
                if text[i] == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        out.append('"'); i += 2; continue
                    end = i; i += 1; break
                out.append(text[i]); i += 1
            else:
                raise ValueError("CSV_INVALID")
            value = "".join(out)
            while i < n and text[i] not in (delimiter, "\r", "\n"):
                if text[i].strip(): raise ValueError("CSV_INVALID")
                i += 1
        else:
            start = i
            while i < n and text[i] not in (delimiter, "\r", "\n"):
                if text[i] == '"': raise ValueError("CSV_INVALID")
                i += 1
            end = i
            value = text[start:end]
        row.append((value, start, end))
        if i < n and text[i] == delimiter:
            i += 1
            if i == n: row.append(("", i, i)); rows.append(row)
            continue
        if i < n and text[i] == "\r": i += 1
        if i < n and text[i] == "\n": i += 1
        rows.append(row); row = []
    if row: rows.append(row)
    return rows


def _csv_hits(doc, detector):
    text = doc.units[0].text
    delimiter = "\t" if doc.suffix == ".tsv" else ","
    rows = _csv_spans(text, delimiter)
    if len(rows) < 2: return {}
    headers = [header_kind(v) for v, _, _ in rows[0]]
    if not any(headers): return {}
    hits = []
    for row in rows[1:]:
        for col, (value, start, end) in enumerate(row):
            if col >= len(headers) or not headers[col] or start == end: continue
            kind = _value_kind(value, headers[col], detector)
            if kind: hits.append(Hit(start, end, kind, "table_header_context"))
    return {doc.units[0].key: hits} if hits else {}


def _xlsx_hits(doc, detector):
    ns = f"{{{S}}}"
    workbook = doc.roots.get("xl/workbook.xml")
    rels = doc.roots.get("xl/_rels/workbook.xml.rels")
    if workbook is None or rels is None: return {}
    relmap = {e.get("Id"): e.get("Target", "") for e in rels if e.tag.endswith("Relationship")}
    relns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    sheets = []
    import posixpath
    for sheet_index, sheet in enumerate(workbook.iter(ns + "sheet"), 1):
        target = relmap.get(sheet.get("{" + relns + "}id"), "")
        if target:
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
            if path in doc.roots: sheets.append((sheet_index, path))
    shared_root = doc.roots.get("xl/sharedStrings.xml")
    shared = list(shared_root) if shared_root is not None else []
    location_units = {}
    for unit in doc.units:
        if unit.kind not in ("text", "formula"): continue
        for loc in unit.preview_cells:
            key = (loc.get("sheet"), loc.get("cell"))
            prior = location_units.get(key)
            if prior is None or unit.kind == "formula": location_units[key] = unit
    output = {}
    for sheet_number, path in sheets:
        root = doc.roots[path]
        rows = []
        for row in root.iter(ns + "row"):
            cells = {}
            for cell in row.findall(ns + "c"):
                ref = cell.get("r", "")
                col = re.match(r"[A-Z]+", ref)
                if not col: continue
                value = cell.findtext(ns + "v") or ""
                if cell.get("t") == "s" and value.isdecimal() and int(value) < len(shared):
                    value = "".join(x.text or "" for x in shared[int(value)].iter(ns + "t"))
                elif cell.get("t") == "inlineStr":
                    value = "".join(x.text or "" for x in cell.iter(ns + "t"))
                cells[col.group()] = (value, ref, cell.find(ns + "f") is not None)
            if cells: rows.append(cells)
        if not rows: continue
        header_index = max(range(min(5, len(rows))), key=lambda i: sum(header_kind(v) is not None for v, _, _ in rows[i].values()))
        headers = {col: header_kind(value) for col, (value, _, _) in rows[header_index].items()}
        if not any(headers.values()): continue
        for row in rows[header_index + 1:]:
            for col, (value, ref, formula) in row.items():
                kind = headers.get(col)
                if not kind: continue
                entity_kind = _value_kind(value, kind, detector)
                if not entity_kind: continue
                unit = location_units.get((sheet_number, ref))
                if unit is None: continue
                hit = Hit(0, len(unit.text), entity_kind, "table_header_context")
                output.setdefault(unit.key, []).append(hit)
    return output


def contextual_hits(doc, detector):
    if doc.suffix in (".csv", ".tsv"): return _csv_hits(doc, detector)
    if doc.suffix == ".xlsx": return _xlsx_hits(doc, detector)
    return {}
