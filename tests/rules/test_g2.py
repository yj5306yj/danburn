"""L4-G2 자재 규칙(방수·단열·유리·마감·도장): 로드, 색인 연결, 합성 내역 행 매칭, KS 면제 ◎, 비KS 물량 빈도 계산."""
import math
import re
from pathlib import Path

import pytest

from danburn.calc import aggregate, match_rule, plan_rows
from danburn.index import coverage, load_index
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[2] / "src" / "danburn" / "data" / "rules"

# key → 별표2 시험종목 수(원문 행을 빠짐없이 옮긴 수, 조건부 포함)
G2 = {
    "liquid_waterproofing": 6,
    "coating_waterproofing": 10,
    "polymer_waterproof_sheet": 9,
    "eps_insulation": 7,
    "pe_foam_insulation": 5,
    "pur_foam_insulation": 9,
    "tempered_glass": 7,
    "insulated_glass": 6,
    "gypsum_board": 11,
    "ceramic_tile": 11,
    "water_paint": 26,
    "ready_mixed_paint": 20,
    "epoxy_floor_finish": 21,
}
KS_EXEMPT = set(G2) - {"epoxy_floor_finish"}
PER_AREA = {"eps_insulation", "pe_foam_insulation", "pur_foam_insulation"}   # 시공면적 1,000㎡마다
RAW_UNIT = {"m2": "㎡", "kg": "KG", "l": "L", "m": "M", "ea": "EA"}


@pytest.fixture(scope="module")
def rules():   # 별표2 규칙만 — LH 규칙(lh_eps·lh_pur 등)은 --owner LH 에서만 켜진다(L14-C5)
    return {k: r for k, r in load_rules(RULES).items() if not r.owner}


def _line(name, unit, qty=500.0, spec="합성규격"):
    return BoqLine("건축", "지급(건)", 7, name, spec, unit, qty, "", "지급")


@pytest.mark.parametrize("key", sorted(G2))
def test_rule_shape(rules, key):
    r = rules[key]
    assert r.material == key and r.index_keys == (key,)
    assert r.group_tests and r.group_frequency and "PDF p." in r.group_basis
    assert len(r.tests) == G2[key]
    for t in r.tests:
        assert re.search(r"\(PDF p\.\d+", t.basis), t.basis
    assert r.ks_mark == (key in KS_EXEMPT)
    by_key = {e.key: e for e in load_index()}
    e = by_key[key]
    assert (e.ks is not None) == r.ks_mark                   # KS 여부는 색인(종별 괄호)과 같다
    assert set(e.names) <= set(r.match_names)               # 색인 동의어를 빠뜨리지 않음


@pytest.mark.parametrize("key", sorted(G2))
def test_synthetic_line_row(rules, key):
    r = rules[key]
    unit = RAW_UNIT.get(r.match_units[0], r.match_units[0])
    line = _line(r.match_names[0], unit)
    assert match_rule(line, rules) is r
    mats, unread = aggregate([line], rules)
    assert not unread
    rows = [x for x in plan_rows(mats, rules) if x.material == key]
    still = [t for t in r.tests if t.ks_still_test and not t.optional] if key in KS_EXEMPT else []
    assert len(rows) == 1 + len(still)                       # 별표2 현장: 'KS라도 시험' 종목만 권고 행으로 따로(L14-D2)
    assert all("권고: KS라도 시험" in x.note for x in rows[1:])
    row = rows[0]
    assert row.item.startswith(r.label)
    if key in KS_EXEMPT:
        assert row.count_ks == "◎" and row.calc_basis == "KS자재" and row.count_external == 0
    else:
        assert row.count_ks == "" and row.count_external == 1   # 비KS: 제조사 1곳 × 1회(외부)
    cov = coverage([line], covered_keys=frozenset(k for x in rules.values() for k in x.index_keys))
    assert key not in {u["key"] for u in cov["uncovered"]}


@pytest.mark.parametrize("key", sorted(PER_AREA))
def test_non_ks_area_frequency(rules, key):
    r = rules[key]
    mats, _ = aggregate([_line(r.match_names[0], "㎡", qty=2500.0)], rules)
    row = [x for x in plan_rows(mats, rules, non_ks=True, makers={"*": 2}) if x.material == key][0]
    assert row.count_external == math.ceil(2500 / 1000) * 2
    assert all(t.frequency.per_qty == 1000 and t.frequency.unit == "m2" for t in r.tests)


@pytest.mark.parametrize("name,unit,not_key", [
    ("타일시멘트", "KG", "ceramic_tile"),
    ("비닐타일", "㎡", "ceramic_tile"),
    ("교면도막방수", "㎡", "coating_waterproofing"),
    ("폴리우레아 도막방수", "㎡", "coating_waterproofing"),
    ("개량아스팔트 시트방수", "㎡", "polymer_waterproof_sheet"),
    ("벤토나이트 시트방수", "㎡", "polymer_waterproof_sheet"),
    ("우레탄폼 충전", "M", "pur_foam_insulation"),
    ("반강화유리", "㎡", "tempered_glass"),
    ("에폭시코팅철근", "TON", "epoxy_floor_finish"),
    ("주차장 바닥에폭시", "㎡", "epoxy_floor_finish"),
    ("슬래그석고판", "㎡", "gypsum_board"),
])
def test_excluded_neighbours(rules, name, unit, not_key):
    hit = match_rule(_line(name, unit), rules)
    assert hit is None or hit.material != not_key


def test_optional_tests_not_in_default_row(rules):
    """종류·용도 한정 시험(예: 방수석고보드만, 바닥타일만)은 묶음 행 기본 종목에서 빠진다."""
    mats, _ = aggregate([_line("석고보드", "㎡"), _line("자기질타일", "㎡")], rules)
    rows: dict = {}
    for x in plan_rows(mats, rules):
        rows.setdefault(x.material, x)                       # 첫 행 = 묶음 행(뒤는 KS라도 시험 권고 행, L14-D2)
    assert "흡수시 내박리성" not in rows["gypsum_board"].test_type
    assert "휨 파괴 하중" in rows["gypsum_board"].test_type
    assert "바닥타일" not in rows["ceramic_tile"].test_type
    assert "흡수율" in rows["ceramic_tile"].test_type
