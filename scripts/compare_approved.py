#!/usr/bin/env python3
"""승인 시험계획서와 단번 8.11 산출물을 자재·규격·단위별로 대조한다.

실제 문서는 로컬에서만 읽고, CSV는 사용자가 지정한 경로에만 쓴다.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
from openpyxl import load_workbook
from pypdf import PdfReader

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
from danburn.calc import _spec_for, match_rule
from danburn.model import BoqLine
from danburn.paths import RULES_DIR
from danburn.rules import load_rules


ALIASES = {
    "굳은콘크리트": "콘크리트", "굳지아니한콘크리트": "콘크리트",
    "굳은콘크리트레미콘포함": "콘크리트", "굳지아니한콘크리트레미콘포함": "콘크리트",
    "굳은콘크리트레미콘포함": "콘크리트", "철근콘크리트용봉강": "철근",
    "철근콘크리트용봉강": "철근", "이형봉강": "철근",
}
UNIT_ALIASES = {"㎥": "m3", "m³": "m3", "M3": "m3", "㎡": "m2", "M2": "m2",
                "㎜": "mm", "ｍｍ": "mm", "TON": "ton", "톤": "ton", "개소": "개", "EA": "개"}
_RULES = None
_CLASSIFY_CACHE = {}


def display_material(material: str) -> str:
    return {"rebar": "철근", "ready_mixed_concrete": "콘크리트"}.get(material, material)


def _text(v) -> str:
    return re.sub(r"\s+", " ", str(v or "").replace("\xa0", " ")).strip()


def _compact(v) -> str:
    return re.sub(r"\s+", "", _text(v))


def norm_unit(v) -> str:
    return UNIT_ALIASES.get(_text(v).upper(), _text(v).lower())


def norm_spec(v) -> str:
    s = _text(v).upper().replace("㎜", "MM").replace("ＭＭ", "MM")
    s = re.sub(r"\s+", "", s).replace("－", "-").replace("–", "-")
    m = re.search(r"SD\s*(\d{3})[^0-9]*(?:D|H)?\s*(\d{1,2})(?:MM)?", s)
    if m:
        return f"SD{m.group(1)} D{int(m.group(2))}"
    m = re.search(r"(\d{2})[-](\d{2})[-](\d{1,3})", s)
    if m:
        slump = int(m.group(3)); slump = slump * 10 if slump < 30 else slump
        return f"{m.group(1)}-{m.group(2)}-{slump}"
    return s.strip("()")


def norm_material(v) -> tuple[str, bool]:
    raw = _text(v)
    key = re.sub(r"[\s·()（）]", "", raw).lower()
    if key in ("rebar", "steelbar"):
        return "철근", True
    if key in ("readymixedconcrete", "ready_mixed_concrete", "concrete"):
        return "콘크리트", True
    if key in ALIASES:
        return ALIASES[key], True
    if "철근" in key or "봉강" in key:
        return "철근", True
    if "콘크리트" in key or "레미콘" in key:
        return "콘크리트", True
    return key, False


def _rules():
    global _RULES
    if _RULES is None:
        _RULES = load_rules(RULES_DIR)
    return _RULES


def classify_material(name, spec="", unit="") -> tuple[str, str, bool]:
    """단번의 실제 matcher를 먼저 호출하고, 못 잡은 이름만 기존 별칭으로 보조한다."""
    raw = _text(name)
    cache_key = (raw, _text(spec), _text(unit))
    if cache_key in _CLASSIFY_CACHE:
        return _CLASSIFY_CACHE[cache_key]
    rules = _rules()
    if raw in rules:
        result = (raw, norm_spec(_spec_for(raw, _text(spec), raw) or spec), True)
        _CLASSIFY_CACHE[cache_key] = result
        return result
    for candidate in (raw, _compact(raw)):
        line = BoqLine("", "approved", 0, candidate, _text(spec), _text(unit), 0, "", "")
        rule = match_rule(line, rules)
        if rule:
            result = (rule.material, norm_spec(_spec_for(rule.material, _text(spec), raw) or spec), True)
            _CLASSIFY_CACHE[cache_key] = result
            return result
    mat, mapped = norm_material(raw)
    result = (mat, norm_spec(spec), mapped)
    _CLASSIFY_CACHE[cache_key] = result
    return result


def split_item(v) -> tuple[str, str, bool]:
    raw = _text(v)
    matches = list(re.finditer(r"\(([^()]*)\)", raw))
    if matches:
        spec = matches[-1].group(1)
        material = raw[:matches[-1].start()].strip()
    else:
        material, spec = raw, ""
    mat, mapped = norm_material(material)
    # 승인본 철근은 한 칸 전체가 철근콘크리트용봉강(SD500 10㎜)이다.
    if not mapped and ("SD" in raw.upper() or "봉강" in raw):
        mat, mapped = "철근", True
    return mat, norm_spec(spec), mapped


def split_item_raw(v) -> tuple[str, str]:
    raw = _text(v)
    matches = list(re.finditer(r"\(([^()]*)\)", raw))
    if not matches:
        return raw, ""
    m = matches[-1]
    return raw[:m.start()].strip(), m.group(1)


def _merged_value(ws, r: int, c: int):
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= r <= rng.max_row and rng.min_col <= c <= rng.max_col:
            return ws.cell(rng.min_row, rng.min_col).value
    return ws.cell(r, c).value


def _approved_sheets(wb):
    def has_plan_header(ws):
        vals = [_compact(ws.cell(r, c).value) for r in range(1, min(ws.max_row, 20) + 1)
                for c in range(1, min(ws.max_column, 20) + 1)]
        return any("시험품목" in v for v in vals) and any("계획물량" in v for v in vals)
    sheets = [ws for ws in wb.worksheets if "3차개정" in ws.title and has_plan_header(ws)]
    if sheets:
        return sheets
    candidates = [ws for ws in wb.worksheets if "개정" in ws.title and has_plan_header(ws)]
    return candidates[-1:] if candidates else [wb.worksheets[-1]]


def parse_approved_xlsx(path: Path) -> list[dict]:
    rows = []
    wb = load_workbook(path, data_only=True, read_only=False)
    for ws in _approved_sheets(wb):
        header = None
        for r in range(1, min(ws.max_row, 80) + 1):
            vals = {_compact(_merged_value(ws, r, c)) for c in range(1, ws.max_column + 1)}
            if any("시험품목" in v for v in vals) and any("계획물량" in v for v in vals):
                header = r; break
        if header is None:
            continue
        for r in range(header + 1, ws.max_row + 1):
            vals = [_merged_value(ws, r, c) for c in range(1, ws.max_column + 1)]
            # 열은 승인본 세 판에서 공통: A/B/E/F/I/J/K, 기계도 B가 품목이다.
            item = vals[1] if len(vals) > 1 else None
            test = vals[2] if len(vals) > 2 else None
            qty = vals[4] if len(vals) > 4 else None
            unit = vals[5] if len(vals) > 5 else None
            site = vals[8] if len(vals) > 8 else 0
            external = vals[9] if len(vals) > 9 else 0
            if not _text(item) or not _text(test) or _compact(item) in ("시험품목", "종별") or _compact(test) in ("시험종목", "시험방법"):
                continue
            raw_mat, raw_spec = split_item_raw(item)
            mat, spec, mapped = classify_material(raw_mat, raw_spec, unit)
            try: qty = float(qty) if qty not in (None, "") else None
            except (TypeError, ValueError): qty = None
            def num(x):
                try: return float(str(x).replace(",", "")) if x not in (None, "") else 0.0
                except ValueError: return 0.0
            rows.append({"material": display_material(mat), "material_id": mat, "spec": spec, "unit": norm_unit(unit), "test_type": _text(test), "qty": qty,
                         "site": num(site), "external": num(external), "mapped": mapped,
                         "source": f"{ws.title}:{r}"})
    return rows


def parse_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        rows = data
    else:
        rows = data.get("rows") or data.get("plan_rows") or data.get("result") or []
        if isinstance(rows, dict): rows = rows.get("rows", [])
        if not rows and data.get("json"):
            nested = Path(data["json"])
            if not nested.is_absolute(): nested = path.parent / nested
            if nested.exists(): return parse_json(nested)
    out = []
    for r in rows:
        mat, spec, mapped = classify_material(r.get("material") or r.get("item"), r.get("spec"), r.get("unit"))
        out.append({"material": display_material(mat), "material_id": mat, "spec": spec, "unit": norm_unit(r.get("unit")),
                    "test_type": _text(r.get("test_type") or r.get("test_item") or r.get("시험종목")),
                    "qty": float(r.get("qty") or 0), "site": float(r.get("count_site") or 0),
                    "external": float(r.get("count_external") or 0), "mapped": mapped,
                    "source": "json"})
    return out


def _table_grid(tbl) -> list[list[str]]:
    cells = []
    for tc in tbl.xpath('./*[local-name()="tr"]/*[local-name()="tc"]'):
        a = tc.xpath('./*[local-name()="cellAddr"]'); s = tc.xpath('./*[local-name()="cellSpan"]')
        if not a or not s: continue
        r, c = int(a[0].get("rowAddr")), int(a[0].get("colAddr"))
        rs, cs = int(s[0].get("rowSpan")), int(s[0].get("colSpan"))
        txt = _text("".join(tc.xpath('.//*[local-name()="t"]/text()')))
        cells.append((r, c, rs, cs, txt))
    if not cells: return []
    grid = [["" for _ in range(max(c + cs for _, c, _, cs, _ in cells))]
            for _ in range(max(r + rs for r, _, rs, _, _ in cells))]
    for r, c, rs, cs, txt in cells:
        for rr in range(r, r + rs):
            for cc in range(c, c + cs): grid[rr][cc] = txt
    return grid


def parse_hwpx(path: Path) -> list[dict]:
    rows = []
    with ZipFile(path) as z:
        for name in sorted(n for n in z.namelist() if n.startswith("Contents/section")):
            root = etree.fromstring(z.read(name))
            for tbl in root.xpath('.//*[local-name()="tbl"]'):
                g = _table_grid(tbl)
                if not g or not any("시험항목" in x for x in g[0]): continue
                header = g[0]
                # 현재 11열 출력과 12열 출력(L14-E)을 모두 지원한다.
                idx = {k: next((i for i, x in enumerate(header) if x == k), -1)
                       for k in ("시험항목", "수량", "단위", "현장", "외부", "의뢰")}
                for row in g[2:]:
                    item = row[idx["시험항목"]] if idx["시험항목"] >= 0 else ""
                    if not item: continue
                    def val(k): return row[idx[k]] if idx[k] >= 0 and idx[k] < len(row) else ""
                    raw_mat, raw_spec = split_item_raw(item)
                    mat, spec, mapped = classify_material(raw_mat, raw_spec, val("단위"))
                    try: qty = float(val("수량").replace(",", "")) if val("수량") not in ("", "-") else None
                    except ValueError: qty = None
                    def num(x):
                        try: return float(x.replace(",", "")) if x not in ("", "-") else 0.0
                        except ValueError: return 0.0
                    test_idx = next((i for i, x in enumerate(header) if x in ("시험종류", "시험종목", "시험방법")), -1)
                    rows.append({"material": display_material(mat), "material_id": mat, "spec": spec, "unit": norm_unit(val("단위")),
                                 "test_type": row[test_idx] if 0 <= test_idx < len(row) else "", "qty": qty,
                                 "site": num(val("현장")), "external": num(val("외부") or val("의뢰")),
                                 "mapped": mapped, "source": name})
    return rows


def parse_pdf(path: Path, pages: str) -> list[dict]:
    reader = PdfReader(str(path)); start, end = (int(x) for x in pages.split("-"))
    found = []
    for page_no in range(start, end + 1):
        page = reader.pages[page_no - 1]
        positioned = []
        page.extract_text(visitor_text=lambda t, cm, tm, font, size:
                           positioned.append((float(tm[4]), float(tm[5]), t)) if t.strip() else None)
        if not positioned:
            continue
        # 머리행의 좌표에서 열 위치를 얻는다. 이 문서의 계획횟수 하위 열은 현장/의뢰다.
        header_candidates = defaultdict(list)
        for x, y, t in positioned:
            header_candidates[round(y / 2.5) * 2.5].append(_compact(t))
        header_y = max((y for y, texts in header_candidates.items()
                        if sum(any(k in t for k in ("공종", "시험품목", "시험종목", "시험방법", "계획물량", "시험빈도"))
                               for t in texts) >= 3), default=0)
        anchors = {"공종": 16, "시험품목": 68, "시험종목": 186, "시험방법": 352,
                   "계획물량": 449, "시험빈도": 555, "산출근거": 646,
                   "현장": 714, "의뢰": 743, "KS": 774, "비고": 820}
        for x, y, t in positioned:
            if abs(y - header_y) > 10 and abs(y - (header_y - 7)) > 10:
                continue
            c = _compact(t)
            for label in tuple(anchors):
                if label in c:
                    anchors[label] = x
        cuts = [0, anchors["시험품목"] - 10, anchors["시험종목"] - 10, anchors["시험방법"] - 10,
                anchors["계획물량"] - 10, anchors["시험빈도"] - 10, anchors["산출근거"] - 10,
                anchors["현장"] - 10, anchors["의뢰"] - 10, anchors["KS"] - 10, anchors["비고"] - 10, 1000]
        groups = defaultdict(list)
        for x, y, t in positioned:
            if y < header_y - 12:
                groups[round(y / 2.5) * 2.5].append((x, _text(t)))
        blocks, block = [], None
        for y in sorted(groups, reverse=True):
            cells = ["" for _ in range(11)]
            for x, t in groups[y]:
                col = next((i for i in range(10) if cuts[i] <= x < cuts[i + 1]), 10)
                cells[col] += t
            if not any(cells[1:9]):
                continue
            if cells[1] and ("콘크리트" in cells[1] or "철근" in cells[1] or "봉강" in cells[1] or "골재" in cells[1]):
                block = {"parts": [], "rows": []}; blocks.append(block)
            if block is None:
                continue
            if cells[1]: block["parts"].append(cells[1])
            if cells[2] or cells[3] or cells[4] or cells[7] or cells[8]:
                block["rows"].append(cells)
        for block in blocks:
            item = "".join(block["parts"])
            raw_mat, raw_spec = split_item_raw(item)
            if not raw_mat or not raw_spec:
                for part in block["parts"]:
                    if not raw_spec and re.search(r"\d{2}-\d{2}-\d{2,3}|SD\s*\d{3}", part, re.I):
                        raw_spec = part.strip("()")
            mat, spec, mapped = classify_material(raw_mat, raw_spec, "")
            block_qty = next((re.search(r"[\d,]+(?:\.\d+)?", c[4]) for c in block["rows"] if re.search(r"\d", c[4])), None)
            block_qty_text = block_qty.group(0).replace(",", "") if block_qty else ""
            block_qty_value = float(block_qty_text) if block_qty_text.replace(".", "", 1).isdigit() else None
            block_unit = next((m.group(1) for c in block["rows"] for m in [re.search(r"(㎥|m3|M3|㎡|m2|ton|TON|개소|본|매|m)", c[4], re.I)] if m), "")
            for cells in block["rows"]:
                qmatch = re.search(r"[\d,]+(?:\.\d+)?", cells[4])
                qty_text = qmatch.group(0).replace(",", "") if qmatch else ""
                qty = float(qty_text) if qty_text.isdigit() or re.fullmatch(r"\d+\.\d+", qty_text) else block_qty_value
                unit_match = re.search(r"(㎥|m3|M3|㎡|m2|ton|TON|개소|본|매|m)", cells[4], re.I)
                site = re.search(r"-?\d+(?:\.\d+)?", cells[7]); external = re.search(r"-?\d+(?:\.\d+)?", cells[8])
                found.append({"material": display_material(mat), "material_id": mat, "spec": spec, "unit": norm_unit(unit_match.group(1) if unit_match else block_unit),
                             "test_type": cells[2], "qty": qty,
                             "site": float(site.group(0)) if site else 0.0,
                             "external": float(external.group(0)) if external else 0.0,
                             "mapped": mapped, "incomplete": not (cells[2] and qty is not None and site and external),
                             "source": f"PDF p.{page_no}"})
    return found


def aggregate(rows: list[dict], by_test: bool = False) -> dict[tuple, dict]:
    out = {}
    for r in rows:
        k = (r.get("material_id", r["material"]), r["spec"], r["unit"], _compact(r.get("test_type")) if by_test else "")
        a = out.setdefault(k, {"material": r["material"], "spec": r["spec"], "unit": r["unit"],
                               "test_type": r.get("test_type", ""), "qty": None, "qty_values": set(), "site": 0.0, "external": 0.0, "mapped": True, "incomplete": False})
        # 같은 계획물량이 시험종목마다 반복되면 한 번만, 블록·행별로 값이 다르면 합산한다.
        if r.get("qty") is not None: a["qty_values"].add(float(r["qty"]))
        a["qty"] = sum(a["qty_values"]) if a["qty_values"] else None
        a["site"] += r.get("site", 0) or 0; a["external"] += r.get("external", 0) or 0
        a["mapped"] &= r.get("mapped", False); a["incomplete"] |= r.get("incomplete", False)
    return out


def compare(expected: list[dict], actual: list[dict]) -> list[dict]:
    e, a, out = aggregate(expected), aggregate(actual), []
    for k in sorted(set(e) | set(a)):
        x, y = e.get(k), a.get(k)
        if not x: status = "대응 없음" if not y["mapped"] else "승인본에 없음"
        elif not y: status = "대응 없음" if not x["mapped"] else "단번에 없음"
        else:
            qdiff = x["qty"] is not None and y["qty"] is not None and abs(x["qty"] - y["qty"]) > max(0.01, abs(x["qty"]) * 0.001)
            cdiff = abs(x["site"] - y["site"]) > 0.001 or abs(x["external"] - y["external"]) > 0.001
            status = "수량차" if qdiff else "횟수차" if cdiff else "일치"
        out.append({"material": (x or y)["material"], "spec": k[1], "unit": k[2], "approved_qty": x["qty"] if x else "", "danburn_qty": y["qty"] if y else "",
                    "qty_diff": (y["qty"] - x["qty"]) if x and y and x["qty"] is not None and y["qty"] is not None else "",
                    "approved_site": x["site"] if x else "", "danburn_site": y["site"] if y else "",
                    "approved_external": x["external"] if x else "", "danburn_external": y["external"] if y else "",
                    "판정": "읽기 불완전" if (x and x.get("incomplete")) or (y and y.get("incomplete")) else status})
    return out


def compare_subjects(expected: list[dict], actual: list[dict]) -> list[dict]:
    e, a, out = aggregate(expected, True), aggregate(actual, True), []
    for k in sorted(set(e) | set(a)):
        x, y = e.get(k), a.get(k)
        if not x or not y:
            status = "대응 없음"
        elif abs(x["site"] - y["site"]) > 0.001 or abs(x["external"] - y["external"]) > 0.001:
            status = "횟수차"
        else:
            status = "일치"
        out.append({"material": (x or y)["material"], "spec": k[1], "unit": k[2], "test_type": (x or y)["test_type"],
                    "approved_site": x["site"] if x else "", "danburn_site": y["site"] if y else "",
                    "approved_external": x["external"] if x else "", "danburn_external": y["external"] if y else "",
                    "판정": "읽기 불완전" if (x and x.get("incomplete")) or (y and y.get("incomplete")) else status})
    return out


def _fmt(v): return "" if v == "" else f"{v:g}" if isinstance(v, float) else str(v)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--approved", required=True)
    src = ap.add_mutually_exclusive_group(required=True); src.add_argument("--json"); src.add_argument("--hwpx")
    ap.add_argument("--pages", default="341-388", help="관리본 PDF 페이지 범위(1부터, 예: 341-388)")
    ap.add_argument("--out", help="CSV 출력 경로")
    a = ap.parse_args(argv)
    approved_path = Path(a.approved)
    expected = parse_approved_xlsx(approved_path) if approved_path.suffix.lower() != ".pdf" else parse_pdf(approved_path, a.pages)
    actual_path = Path(a.json or a.hwpx)
    actual = parse_json(actual_path) if a.json else parse_hwpx(actual_path)
    result = compare(expected, actual)
    print("자재 | 규격 | 단위 | 승인 총량 | 단번 총량 | 차이 | 승인 현장/의뢰 | 단번 현장/외부 | 판정")
    for r in result:
        print(f"{r['material']} | {r['spec']} | {r['unit']} | {_fmt(r['approved_qty'])} | {_fmt(r['danburn_qty'])} | {_fmt(r['qty_diff'])} | {r['approved_site']}/{r['approved_external']} | {r['danburn_site']}/{r['danburn_external']} | {r['판정']}")
    subjects = compare_subjects(expected, actual)
    print("\n종목별(규격 × 시험종목) | 자재 | 규격 | 시험종목 | 승인 현장/의뢰 | 단번 현장/외부 | 판정")
    for r in subjects:
        print(f"종목별 | {r['material']} | {r['spec']} | {r['test_type']} | {r['approved_site']}/{r['approved_external']} | {r['danburn_site']}/{r['danburn_external']} | {r['판정']}")
    if a.out:
        fields = list(result[0]) if result else ["material", "spec", "unit", "판정"]
        with Path(a.out).open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(result)
    return 0


if __name__ == "__main__": sys.exit(main())
