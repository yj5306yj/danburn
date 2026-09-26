"""조용한 누락(L7-E4): 규칙이 있는 종별이라도 그 행이 규칙에 걸리지 않으면 드러나야 한다."""
from __future__ import annotations

import json

import openpyxl
import pytest

from danburn.calc import match_rule
from danburn.cli import main
from danburn.index import IndexEntry, coverage
from danburn.model import BoqLine
from danburn.rules import load_rules


def _entry(key, names, rule=None, order=0):
    return IndexEntry(key=key, label=f"합성 {key}", part="", section="", subsection="", ks=None, page=1,
                      names=tuple(names), rule=rule, order=order)


INDEX = [_entry("alpha", ["알파자재"], order=0), _entry("beta", ["베타자재"], order=1)]


def _line(name, unit="m2", spec=""):
    return BoqLine("건축", "합성", 1, name, spec, unit, 10.0, "", "사급")


def test_rule_key_rows_not_matched_are_reported():
    lines = [_line("알파자재 A형"), _line("알파자재 특수형"), _line("베타자재")]
    matched = lambda ln: "특수" not in ln.name and "알파" in ln.name   # noqa: E731 — 규칙이 특수형을 exclude 로 뺀 상황
    cov = coverage(lines, index=INDEX, covered_keys=frozenset({"alpha"}), matched=matched)
    miss = {u["key"]: u for u in cov["unmatched_in_covered"]}
    assert set(miss) == {"alpha"} and miss["alpha"]["lines"] == 1 and miss["alpha"]["examples"] == ["알파자재 특수형"]
    assert [u["key"] for u in cov["uncovered"]] == ["beta"]
    assert [u["key"] for u in cov["covered"]] == ["alpha"]


def test_rows_matched_by_other_rule_are_not_uncovered():
    # 색인은 beta 로 보지만 어떤 규칙이 그 행을 잡았다 → 산출됨, 경고 아님
    cov = coverage([_line("베타자재")], index=INDEX, matched=lambda ln: True)
    assert cov["uncovered"] == [] and cov["unmatched_in_covered"] == []


def test_without_matched_keeps_old_behaviour():
    cov = coverage([_line("알파자재 특수형"), _line("베타자재")], index=INDEX, covered_keys=frozenset({"alpha"}))
    assert [u["key"] for u in cov["uncovered"]] == ["beta"]
    assert cov["unmatched_in_covered"] == []


def test_labor_only_still_uses_all_rows():
    lines = [_line("알파자재 설치"), _line("알파자재")]
    cov = coverage(lines, index=INDEX, covered_keys=frozenset({"alpha"}), matched=lambda ln: ln.name == "알파자재")
    assert cov["labor_only"] == [] and cov["unmatched_in_covered"] == []


@pytest.fixture(scope="module")
def rules():
    from pathlib import Path
    return load_rules(Path(__file__).resolve().parents[1] / "src" / "danburn" / "data" / "rules")


def test_real_index_exclusions(rules):
    """색인 exclude 보강(L7-E4): 천장틀·뚜껑·방수 모르타르, 락카 사물함·피트니스·합판 작업대는 그 종별로 보지 않는다."""
    from danburn.index import identify
    keys = lambda n, s="": {e.key for e in identify(n, s)}   # noqa: E731
    assert "light_gauge_section" not in keys("경량철골 천장틀")
    assert "light_gauge_section" not in keys("경량철골 천정판")
    assert "light_gauge_section" in keys("경량형강 C-100")
    assert "hot_rolled_mild_sheet" not in keys("열연강판 뚜껑")
    assert "hot_rolled_mild_sheet" in keys("열연강판 SPHC")
    assert "repair_polymer_mortar" not in keys("폴리머시멘트모르타르 방수")
    assert "repair_polymer_mortar" in keys("단면보수 폴리머모르타르")
    assert "lacquer" not in keys("탈의실 락카")
    assert "varnish" not in keys("피트니스센터 세면대")
    assert "varnish" in keys("바니시")


def _xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "내역(건)"
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_cli_reports_rule_key_row_that_rule_excludes(tmp_path, capsys, rules):
    """재현: 규칙(PVC계 바닥재)은 있지만 그 행은 규칙에 안 걸린다(단위 '롤'이 규칙 단위 밖) → 예전에는 어디에도 안 나왔다."""
    name = "비닐바닥재 T2"
    line = _line(name, unit="롤")
    assert match_rule(line, rules) is None
    from danburn.index import identify
    assert "pvc_floor" in {e.key for e in identify(name)}
    src = tmp_path / "b.xlsx"
    _xlsx(src, [["품명", "규격", "단위", "수량"], ["레미콘", "25-24-15", "M3", 500], [name, "T2", "롤", 30]])
    assert main(["build", "--boq", str(src), "--out", str(tmp_path / "o.hwpx"), "--offline"]) == 0
    summary = json.loads(capsys.readouterr().out)
    miss = {u["key"]: u for u in summary["unmatched_in_covered"]}
    assert "pvc_floor" in miss and name in miss["pvc_floor"]["examples"]
    assert any("규칙 밖 행" in w and "PVC계 바닥재" in w for w in summary["warnings"])


def test_cli_rule_miss_hidden_when_rule_produced_rows(tmp_path, capsys):
    """이미 8.11 행이 있는 종별의 나머지 행은 요약에만(produced=True), 경고·표에는 안 싣는다."""
    src = tmp_path / "p.xlsx"
    _xlsx(src, [["품명", "규격", "단위", "수량"], ["레미콘", "25-24-15", "M3", 500],
                ["비닐바닥재", "T2", "M2", 300], ["비닐바닥재 T2", "T2", "롤", 30]])
    assert main(["build", "--boq", str(src), "--out", str(tmp_path / "o.hwpx"), "--offline"]) == 0
    summary = json.loads(capsys.readouterr().out)
    miss = {u["key"]: u for u in summary["unmatched_in_covered"]}
    assert miss["pvc_floor"]["produced"] is True
    assert not any(w.startswith("규칙 밖 행") and "PVC계 바닥재" in w for w in summary["warnings"])
    assert "fresh_concrete" not in {k for k, u in miss.items() if not u["produced"]}   # 색인 rule 로 이어진 레미콘은 산출됨


def test_unlisted_table_has_rule_miss_kind():
    from danburn.hwpx_out import _unlisted_texts, unlisted_items
    items = unlisted_items([{"label": "가", "page": 1, "lines": 2}], rule_miss=[{"label": "나", "page": 3, "lines": 4}])
    assert [i["kind"] for i in items] == ["uncovered", "rule_miss"]
    texts = _unlisted_texts(items[1])
    assert texts[0] == "규칙 밖 행" and texts[1] == "나" and texts[2] == "별표2 p.3" and "규칙" in texts[4]
