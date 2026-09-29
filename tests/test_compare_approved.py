from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook

from scripts.compare_approved import compare, compare_subjects, parse_approved_xlsx, parse_json


def _approved(path: Path):
    wb = Workbook(); ws = wb.active; ws.title = "건축 (3차개정)"
    ws.append(["공종", "시험품목", "시험종목", "시험방법", "계획물량", "단위", "시험빈도", "근거", "현장", "의뢰", "KS", "비고"])
    ws.append(["철근콘크리트", "철근콘크리트용봉강(SD500 10㎜)", "인장", "KS", 100, "TON", "별도", "1회", 0, 2, "", ""])
    ws.append([None, None, "겉모양", "KS", None, None, "별도", "1회", 0, 2, "", ""])
    ws.append(["철근콘크리트", "굳은 콘크리트(레미콘포함)(25-18-80)", "압축", "KS", 120, "M3", "120", "1회", 1, 0, "㉿", ""])
    wb.save(path)


def test_approved_json_aggregates_alias_and_repeated_rows(tmp_path):
    xlsx = tmp_path / "approved.xlsx"; _approved(xlsx)
    data = [
        {"material": "rebar", "spec": "SD500 D10", "qty": 40, "unit": "ton", "count_site": 0, "count_external": 1},
        {"material": "rebar", "spec": "SD500 D10", "qty": 60, "unit": "ton", "count_site": 0, "count_external": 1},
        {"material": "ready_mixed_concrete", "spec": "25-18-8", "qty": 120, "unit": "m3", "count_site": 1, "count_external": 0},
    ]
    js = tmp_path / "rows.json"; js.write_text(json.dumps(data), encoding="utf-8")
    got = compare(parse_approved_xlsx(xlsx), parse_json(js))
    by = {(r["material"], r["spec"]): r for r in got}
    assert by[("철근", "SD500 D10")]["판정"] == "일치"
    assert by[("콘크리트", "25-18-80")]["판정"] == "일치"


def test_unmatched_name_is_visible():
    result = compare([{"material": "승인만자재", "spec": "A", "unit": "개", "qty": 1, "site": 1, "external": 0, "mapped": False}], [])
    assert result[0]["판정"] == "대응 없음"


def test_plan_summary_json_wrapper_and_subject_counts(tmp_path):
    wrapper = tmp_path / "summary.json"
    wrapper.write_text(json.dumps({"json": "rows.json", "warnings": []}), encoding="utf-8")
    (tmp_path / "rows.json").write_text(json.dumps([{
        "material": "ready_mixed_concrete", "spec": "25-18-8", "qty": 120, "unit": "m3",
        "test_type": "압축", "count_site": 1, "count_external": 0,
    }]), encoding="utf-8")
    rows = parse_json(wrapper)
    assert rows[0]["material_id"] == "ready_mixed_concrete"
    subjects = compare_subjects([{
        "material": "콘크리트", "material_id": "ready_mixed_concrete", "spec": "25-18-80", "unit": "m3",
        "test_type": "압축", "qty": 120, "site": 1, "external": 0, "mapped": True,
    }], rows)
    assert subjects[0]["판정"] == "일치"
