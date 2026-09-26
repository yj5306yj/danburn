"""L4-G4 자재 규칙(창호·유리·기타 마감·토목 부자재): 로드, 색인 연결, 합성 내역 행 매칭, KS 면제 ◎, 비KS 물량 빈도 계산."""
import math
import re
from pathlib import Path

import pytest

from danburn.calc import aggregate, match_rule, plan_rows
from danburn.index import coverage, load_index
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[2] / "src" / "danburn" / "data" / "rules"

# key → 규칙의 시험종목 수(별표2 원문 종목을 빠짐없이, 조건부 포함). 섬유강화 시멘트판은 종류별 25행을 종목 8개로 합침.
G4 = {
    "tile_cement": 8,
    "pc_strand": 5,
    "alc_panel": 7,
    "nonwoven_geotextile": 9,
    "centrifugal_rc_pipe": 5,
    "asphalt_filler": 6,
    "interlocking_block": 8,
    "pvc_waterstop": 7,
    "laminated_glass": 9,
    "mineral_wool": 5,
    "wood_window_frame": 4,
    "door_set": 13,
    "window_set": 10,
    "synthetic_window_profile": 14,
    "hinge": 3,
    "fiber_cement_board": 8,
    "tile_adhesive": 8,
}
# key → (비KS 물량 빈도, 단위)
PER_QTY = {"tile_cement": (300, "ton"), "mineral_wool": (1000, "m2"), "nonwoven_geotextile": (20000, "m2")}
RAW_UNIT = {"m2": "㎡", "kg": "KG", "l": "L", "m": "M", "ea": "EA", "ton": "TON"}


@pytest.fixture(scope="module")
def rules():
    return load_rules(RULES)


def _line(name, unit, qty=500.0, spec="합성규격"):
    return BoqLine("건축", "지급(건)", 7, name, spec, unit, qty, "", "지급")


@pytest.mark.parametrize("key", sorted(G4))
def test_rule_shape(rules, key):
    r = rules[key]
    assert r.material == key and r.index_keys == (key,)
    assert r.group_tests and r.group_frequency and "PDF p." in r.group_basis
    assert len(r.tests) == G4[key]
    assert any(not t.optional for t in r.tests)
    for t in r.tests:
        assert re.search(r"\(PDF p\.\d+", t.basis), t.basis
    e = {x.key: x for x in load_index()}[key]
    assert e.ks is not None and r.ks_mark and r.ks_count == "none"   # 모두 종별 괄호에 KS
    assert e.ks in r.group_basis
    assert set(e.names) <= set(r.match_names)                      # 색인 동의어를 빠뜨리지 않음


def test_no_other_rule_claims_g4_keys(rules):
    owners = [k for r in rules.values() for k in r.index_keys if k in G4]
    assert sorted(owners) == sorted(G4)


@pytest.mark.parametrize("key", sorted(G4))
def test_synthetic_line_row(rules, key):
    r = rules[key]
    unit = RAW_UNIT.get(r.match_units[0], r.match_units[0])
    line = _line(r.match_names[0], unit)
    assert match_rule(line, rules) is r
    mats, unread = aggregate([line], rules)
    assert not unread
    rows = [x for x in plan_rows(mats, rules) if x.material == key]
    assert len(rows) == 1
    row = rows[0]
    assert row.item.startswith(r.label)
    assert row.count_ks == "◎" and row.calc_basis == "KS자재" and row.count_external == 0
    cov = coverage([line], covered_keys=frozenset(k for x in rules.values() for k in x.index_keys))
    assert key not in {u["key"] for u in cov["uncovered"]}


@pytest.mark.parametrize("key", sorted(G4))
def test_non_ks_default_count(rules, key):
    """비KS: 물량 빈도가 있으면 ⌈물량/빈도⌉×제조사 수, 없으면 제조사 수×1회."""
    r = rules[key]
    per, unit = PER_QTY.get(key, (None, r.match_units[0]))
    qty = 2500.0 if per is None else per * 2.5
    mats, _ = aggregate([_line(r.match_names[0], RAW_UNIT.get(unit, unit), qty=qty)], rules)
    row = [x for x in plan_rows(mats, rules, non_ks=True, makers={"*": 2}) if x.material == key][0]
    assert row.count_ks == ""
    assert row.count_external == (2 if per is None else math.ceil(qty / per) * 2)
    if per is not None:
        assert all(t.frequency.per_qty == per and t.frequency.unit == unit for t in r.tests if not t.optional)


@pytest.mark.parametrize("name,unit,key", [
    ("타일시멘트", "KG", "tile_cement"),            # 포틀랜드 시멘트(시멘트)·도자기질 타일(타일)이 먼저 잡지 않음
    ("압착시멘트", "포", "tile_cement"),
    ("타일접착제", "KG", "tile_adhesive"),
    ("ALC패널", "㎡", "alc_panel"),                 # 경량기포콘크리트블록과 구분
    ("슬래그석고판", "㎡", "fiber_cement_board"),     # 석고보드와 구분
    ("규산칼슘판", "㎡", "fiber_cement_board"),
    ("목재문틀", "EA", "wood_window_frame"),          # 문세트(목재문)와 구분
    ("PVC창호형재", "M", "synthetic_window_profile"),  # 창세트(PVC창호)와 구분
    ("알루미늄창호", "개소", "window_set"),
    ("갑종방화문", "EA", "door_set"),
    ("원심력철근콘크리트관", "M", "centrifugal_rc_pipe"),
    ("인터로킹블록", "㎡", "interlocking_block"),      # 속빈콘크리트블록과 구분
    ("PC강연선", "TON", "pc_strand"),                # 철근과 구분
    ("석분", "TON", "asphalt_filler"),
    ("글라스울", "㎡", "mineral_wool"),
    ("접합유리", "㎡", "laminated_glass"),
])
def test_neighbour_names_route_to_g4(rules, name, unit, key):
    hit = match_rule(_line(name, unit), rules)
    assert hit is not None and hit.material == key


@pytest.mark.parametrize("name,unit,not_key", [
    ("플로어힌지", "EA", "hinge"),
    ("암면흡음판", "㎡", "mineral_wool"),
    ("수팽창지수재", "M", "pvc_waterstop"),
    ("창호 설치", "개소", "window_set"),
    ("보도블록 포설", "㎡", "interlocking_block"),
])
def test_excluded_neighbours(rules, name, unit, not_key):
    hit = match_rule(_line(name, unit), rules)
    assert hit is None or hit.material != not_key


def test_install_row_is_accepted_but_marked(rules):
    """L4-T3 이후: 시공 행('부직포 깔기')은 부직포로 받되 시공 행으로 표시한다(자재 행이 있으면 중복 제거)."""
    from danburn.calc import match_rule_kind
    rule, install = match_rule_kind(_line("부직포 깔기", "㎡"), rules)
    assert rule.material == "nonwoven_geotextile" and install


def test_optional_tests_not_in_default_row(rules):
    """종류·용도 한정 종목(곡면접합, 투수성블록, 목제 창, 방균관, 미네랄울 등)은 기본 행에서 빠진다."""
    lines = [_line("접합유리", "㎡"), _line("인터로킹블록", "㎡"), _line("알루미늄창호", "EA"),
             _line("흄관", "M"), _line("글라스울", "㎡"), _line("시멘트보드", "㎡"), _line("타일접착제", "KG")]
    mats, _ = aggregate(lines, rules)
    rows = {x.material: x.test_type for x in plan_rows(mats, rules)}
    assert "(곡면)" not in rows["laminated_glass"] and "낙구 충격시험" in rows["laminated_glass"]
    assert "(투수성블록)" not in rows["interlocking_block"] and "표면층 두께" in rows["interlocking_block"]
    assert "함수율" not in rows["window_set"] and "기밀성" in rows["window_set"]
    assert "방균" not in rows["centrifugal_rc_pipe"] and "외압강도" in rows["centrifugal_rc_pipe"]
    assert "미네랄울" not in rows["mineral_wool"] and "열전도율" in rows["mineral_wool"]
    assert rows["fiber_cement_board"] == "겉모양 및 치수,휨강도,흡수에 의한 길이 변화율"
    assert "실내공기" not in rows["tile_adhesive"]
