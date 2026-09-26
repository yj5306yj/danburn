"""match.names_generic + match.spec_names (L7-E6): 품명은 일반 이름('거푸집')뿐이고 규격에 자재('합판')가 있는 행."""
from __future__ import annotations

from pathlib import Path

import pytest

from danburn.calc import aggregate, ambiguous, match_rule, plan_rows
from danburn.index import coverage
from danburn.model import BoqLine
from danburn.rules import load_rule, load_rules

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "data" / "rules"


@pytest.fixture(scope="module")
def rules():
    return load_rules(RULES)


def _line(name, spec, unit="M2", qty=100.0):
    return BoqLine("토목", "합성", 1, name, spec, unit, qty, "", "사급")


def test_loader_reads_fields():
    r = load_rule(RULES / "form_plywood.yaml")
    assert r.match_names_generic == ("거푸집",) and r.match_spec_names == ("합판",)


def test_loader_requires_both(tmp_path):
    src = (RULES / "form_plywood.yaml").read_text(encoding="utf-8")
    bad = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("spec_names"))
    (tmp_path / "x.yaml").write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError, match="함께"):
        load_rule(tmp_path / "x.yaml")


@pytest.mark.parametrize("name,spec", [
    ("거푸집 (합성공종)", "합판6회, 간단"),
    ("문양거푸집 (합성공종)", "합판4회/보통+문양거푸집(판넬)1회"),
    ("거푸집", "코팅 합판"),
])
def test_generic_name_with_spec_matches(rules, name, spec):
    line = _line(name, spec)
    assert match_rule(line, rules).material == "form_plywood"
    assert not ambiguous(line, rules)


@pytest.mark.parametrize("name,spec", [
    ("거푸집 (합성공종)", "유로폼"),            # 다른 재질 — 규격에 합판 없음
    ("거푸집먹매김", "주택"),
    ("매립형철망거푸집", "(기초·지중보)"),
    ("P.E 원형거푸집", "(집수정)"),
    ("알루미늄 거푸집", "합판 대체"),           # 규격에 합판이 있어도 품명 제외어
    ("유로폼 거푸집", "합판 혼용"),
    ("거푸집 해체", "합판"),
    ("합판깔기", "작업대"),                     # 품명에 일반 이름(거푸집)이 없음
])
def test_other_forms_not_matched(rules, name, spec):
    m = match_rule(_line(name, spec), rules)
    assert m is None or m.material != "form_plywood"


def test_specific_name_still_wins_and_units_apply(rules):
    assert match_rule(_line("합판거푸집", "3회"), rules).material == "form_plywood"
    assert match_rule(_line("거푸집 (합성공종)", "합판6회", unit="M3"), rules) is None      # 단위 제한은 그대로


def test_rows_and_coverage(rules):
    lines = [_line("거푸집 (합성공종)", "합판6회, 간단", qty=50)]
    mats, _ = aggregate(lines, rules)
    rows = [r for r in plan_rows(mats, rules) if r.material == "form_plywood"]
    assert len(rows) == 1 and rows[0].count_ks == "◎" and rows[0].qty == 50
    cov = coverage(lines, matched=lambda ln: match_rule(ln, rules) is not None)
    assert cov["unmatched_in_covered"] == [] and cov["uncovered"] == []       # 조용한 누락·규칙 밖 행 없음


def test_rule_without_fields_ignores_spec(rules):
    # 규격 매칭은 names_generic/spec_names 를 적은 규칙에만 — 다른 규칙은 규격 칸을 보지 않는다
    assert match_rule(_line("인테리어시트 벽붙이기", "T9 MDF"), rules) is None
