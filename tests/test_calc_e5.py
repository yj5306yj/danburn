"""L7-E5: 자재 포함 시공 행('…(건조모르타르 포함)'), 수량 환산 없는 행(곱 0), 노무 말 보강 — 합성 자료."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from danburn.calc import aggregate, ambiguous, match_rule, match_rule_kind, plan_rows
from danburn.index import is_labor
from danburn.model import BoqLine, Frequency
from danburn.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def rules():
    return load_rules(ROOT / "src" / "danburn" / "data" / "rules")


def _line(name, unit="M2", qty=100.0, spec="합성", row=1):
    return BoqLine("건축", "합성", row, name, spec, unit, qty, "", "사급")


def _rows(lines, rules, **kw):
    mats, _ = aggregate(lines, rules)
    return plan_rows(mats, rules, **kw)


@pytest.mark.parametrize("name,unit", [
    ("합성벽돌쌓기(3.6M 이하, 건조모르타르 포함)", "M2"),     # 괄호 밖 '쌓기'는 규칙 제외어지만 공종 말이라 보지 않음
    ("배관주위모르타르충진(건조모르타르 포함)", "M"),
    ("석재벽붙이기(석재별도, 건조모르타르포함)", "M2"),
])
def test_included_mortar_is_install_row(rules, name, unit):
    rule, inst = match_rule_kind(_line(name, unit), rules)
    assert rule.material == "dry_cement_mortar" and inst
    assert not ambiguous(_line(name, unit), rules)


def test_included_mortar_makes_ks_row_without_quantity(rules):
    rows = _rows([_line("합성벽돌쌓기(건조모르타르 포함)", "M2", 500, spec="3.6M 이하", row=1),
                  _line("합성충진(건조모르타르 포함)", "M", 70, spec="배관", row=2)], rules)
    mortar = [r for r in rows if r.material == "dry_cement_mortar"]
    assert len(mortar) == 1                                   # 규격·단위가 달라도 한 행(곱 0 → 톤 키, 규격 '자재 포함 시공 행')
    r = mortar[0]
    assert r.item == "건조시멘트모르타르(자재 포함 시공 행)"
    assert r.qty == 0 and r.count_ks == "◎" and r.calc_basis == "KS자재"
    assert r.note == "시공 행 추정(수량 환산 없음)"


def test_material_row_beats_install_rows(rules):
    rows = _rows([_line("건조시멘트모르타르", "포", 200, spec="미장용", row=1),
                  _line("합성벽돌쌓기(건조모르타르 포함)", "M2", 500, row=2)], rules)
    r = [x for x in rows if x.material == "dry_cement_mortar"]
    assert len(r) == 1 and r[0].qty == pytest.approx(8.0) and "시공 행" not in r[0].note   # 200포×0.04톤, 시공 행은 중복이라 버림


def test_main_material_outside_parentheses_wins(rules):
    assert match_rule(_line("자기질타일 붙이기(건조모르타르 포함)"), rules).material == "ceramic_tile"


def test_outside_parentheses_mortar_work_rows_still_excluded(rules):
    assert match_rule(_line("시멘트모르타르 바르기"), rules) is None       # 현장 배합과 구분 불가 — 그대로 막음
    assert match_rule(_line("건조모르타르 쌓기"), rules) is None


def test_other_install_rules_unchanged(rules):
    rule, inst = match_rule_kind(_line("비닐장판깔기"), rules)
    assert rule.material == "pvc_floor" and inst


def _no_ks_per_qty(rule):
    t = rule.tests[0]
    return replace(rule, ks_mark=False, tests=(replace(t, frequency=Frequency(per_qty=50, unit="ton", text="50톤마다")),))


def test_non_ks_quantity_frequency_is_not_invented(rules):
    rules = dict(rules)
    rules["dry_cement_mortar"] = _no_ks_per_qty(rules["dry_cement_mortar"])
    rows = _rows([_line("합성벽돌쌓기(건조모르타르 포함)")], rules)
    r = [x for x in rows if x.material == "dry_cement_mortar"][0]
    assert r.count_external == 0 and "수량 확인 필요" in r.note and "수량 확인 필요" in r.calc_basis


def test_per_test_rows_with_no_quantity(rules):
    rules = dict(rules)
    rules["dry_cement_mortar"] = replace(_no_ks_per_qty(rules["dry_cement_mortar"]), group_tests=False)
    rows = [x for x in _rows([_line("합성벽돌쌓기(건조모르타르 포함)")], rules) if x.material == "dry_cement_mortar"]
    assert rows and all(x.count_site == 0 and x.count_external == 0 and x.note == "수량 확인 필요" for x in rows)


@pytest.mark.parametrize("name,labor", [
    ("H형강말뚝뽑기(토목)", True), ("H형강말뚝박기(토목)", True), ("엄지말뚝박기용 천공", True),
    ("PE관 접합 및 부설", True), ("우레탄도막방수(접합부위)", False), ("접합유리", False),
    ("자기질타일 붙이기(건조모르타르 포함)", False),    # 붙이기는 자재 포함 시공 행 — 노무로 보지 않음
])
def test_labor_words(name, labor):
    assert is_labor(name, "M2") is labor
