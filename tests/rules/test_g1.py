"""L4-G1 자재 규칙(조적·미장·석재·시멘트): 로드, 색인 동의어·단위 매칭, KS 면제 ◎, 비KS 횟수, 종별 간 오매칭 방지."""
import math
from pathlib import Path

import pytest

from danburn.calc import aggregate, match_rule, plan_rows
from danburn.index import load_index
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[2] / "data" / "rules"

# material: (도급내역서 품명, 단위, 수량, 별표2 시험종목 수, 비KS 물량 빈도(None=문구형))
# 수량은 unit_factors 환산 뒤 값이 빈도 단위와 같도록 고른다(포 40 → 1.6톤 등은 아래 환산 테스트에서 따로 본다).
G1 = {
    "concrete_brick": ("시멘트벽돌", "매", 250000, 5, 100000),
    "clay_brick": ("점토벽돌", "EA", 60000, 4, 50000),
    "hollow_concrete_block": ("콘크리트블록", "매", 25000, 4, 10000),
    "architectural_block": ("치장콘크리트블록", "매", 7000, 4, 3000),
    "aac_block": ("ALC블록", "매", 2500, 4, 1000),
    "portland_cement": ("시멘트", "TON", 700, 6, 300),
    "white_cement": ("백시멘트", "TON", 40, 6, 300),
    "dry_cement_mortar": ("건조시멘트모르타르", "포", 900, 5, None),
    "curb_block": ("콘크리트경계블록", "EA", 2500, 3, 1000),
    "stone": ("화강석 판재", "M2", 800, 2, None),
}


@pytest.fixture(scope="module")
def rules():
    return load_rules(RULES)


def _line(name, unit, qty, spec="규격A", row=1):
    return BoqLine("건축", "지급(건)", row, name, spec, unit, float(qty), "", "지급")


def test_rules_load_with_index_keys_and_basis(rules):
    keys = {e.key: e for e in load_index()}
    for material, (_, _, _, n_tests, _) in G1.items():
        rule = rules[material]
        assert rule.index_keys == (material,)
        entry = keys[material]
        assert len(rule.tests) == n_tests, material                     # 별표2 시험종목 빠짐없이
        for t in rule.tests:
            assert f"p.{entry.page}" in t.basis or f"p.{entry.page + 1}" in t.basis, (material, t.test_type)
            assert t.where == "외부"
        assert rule.ks_mark == bool(entry.ks), material                  # 종별 괄호 KS 여부와 같다
        assert rule.group_tests, material                                # 모두 규격당 한 행
        if rule.ks_mark:
            assert "PDF p.52" in rule.group_basis and rule.ks_count == "none"


@pytest.mark.parametrize("material", sorted(G1))
def test_synthetic_line_matches_and_ks_row(rules, material):
    name, unit, qty, _, _ = G1[material]
    line = _line(name, unit, qty)
    assert match_rule(line, rules).material == material
    mats, unread = aggregate([line], rules)
    assert not unread
    rows = [r for r in plan_rows(mats, rules) if r.material == material]
    rule = rules[material]
    assert len(rows) == 1
    row = rows[0]
    assert row.item == f"{rule.label}(규격A)"
    if rule.ks_mark:
        assert row.count_ks == "◎" and row.calc_basis == "KS자재" and row.count_external == 0
    else:                                                               # 석재: KS 아님 → ◎ 없이 골재원(제조사 자리) 1곳×1회
        assert row.test_type == "밀도 및 흡수율,압축강도"
        assert row.count_ks == "" and row.count_external == 1 and row.note == "제조사 수 확인"
        assert row.calc_basis.startswith("골재원마다")


@pytest.mark.parametrize("material", [m for m in sorted(G1) if G1[m][4]])
def test_non_ks_count_by_quantity(rules, material):
    name, unit, qty, _, per = G1[material]
    mats, _ = aggregate([_line(name, unit, qty)], rules)
    row = [r for r in plan_rows(mats, rules, non_ks=True, makers={"*": 2}) if r.material == material][0]
    assert row.count_ks == "" and row.count_external == math.ceil(qty / per) * 2


def test_dry_mortar_non_ks_is_per_maker(rules):
    mats, _ = aggregate([_line("드라이몰탈", "kg", 5000)], rules)
    row = plan_rows(mats, rules, non_ks=True, makers={"*": 3})[0]
    assert row.material == "dry_cement_mortar" and row.count_external == 3


@pytest.mark.parametrize("name,unit,expected", [
    ("시멘트벽돌 190x90x57", "매", "concrete_brick"),
    ("벽돌", "천매", "concrete_brick"),
    ("치장벽돌", "매", "clay_brick"),
    ("시멘트블록 390x190x190", "EA", "hollow_concrete_block"),
    ("치장콘크리트블록", "EA", "architectural_block"),
    ("경량기포콘크리트블록", "m3", "aac_block"),
    ("보통시멘트", "포", "portland_cement"),
    ("백색시멘트", "kg", "white_cement"),
    ("드라이몰탈", "포", "dry_cement_mortar"),
    ("화강석 경계석", "M", "stone"),                 # 화강석 경계석은 콘크리트 경계블록이 아니다
    ("보차도경계블록 180x210x1000", "M", "curb_block"),
    ("대리석", "M2", "stone"),
])
def test_cross_material_routing(rules, name, unit, expected):
    assert match_rule(_line(name, unit, 1), rules).material == expected


@pytest.mark.parametrize("name,unit", [
    ("시멘트벽돌 쌓기 1.0B", "M2"),                 # 노무(㎡)
    ("시멘트벽돌 쌓기", "천매"),                     # 노무 단어
    ("벽돌 소운반", "매"),
    ("시멘트모르타르 바름", "M2"),
    ("시멘트모르타르", "M3"),                       # 현장 비빔(단위 밖)
    ("폴리머시멘트모르타르", "포"),                  # 다른 종별(보수용)
    ("시멘트벽돌", "TON"),
    ("타일압착시멘트", "포"),                        # 도자기질 타일시멘트(다른 종별)
    ("시멘트액체방수", "M2"),
    ("경계블록 설치", "M"),
    ("화강석 붙이기", "M2"),
    ("속빈유리블록", "EA"),
])
def test_labor_and_other_kinds_not_matched(rules, name, unit):
    rule = match_rule(_line(name, unit, 1), rules)
    assert rule is None or rule.material not in G1, (name, rule and rule.material)


def test_optional_hydration_heat_left_out_of_group(rules):
    mats, _ = aggregate([_line("시멘트", "TON", 10)], rules)
    row = plan_rows(mats, rules)[0]
    assert "수화열" not in row.test_type and "압축강도" in row.test_type


# --- L4-G1b: 단위 환산(unit_factors) ---

def _one(rules, lines, material, **kw):
    mats, _ = aggregate(lines, rules)
    return [r for r in plan_rows(mats, rules, **kw) if r.material == material]


@pytest.mark.parametrize("material,name,unit,qty,conv_qty,conv_unit,per", [
    ("concrete_brick", "시멘트벽돌", "천매", 250, 250000, "개", 100000),     # 천매=1,000매
    ("clay_brick", "점토벽돌", "천매", 120, 120000, "개", 50000),
    ("hollow_concrete_block", "시멘트블록", "개", 25000, 25000, "개", 10000),
    ("architectural_block", "치장블록", "천매", 7, 7000, "개", 3000),
    ("aac_block", "ALC블록", "천매", 2.5, 2500, "개", 1000),
    ("portland_cement", "시멘트", "포", 10000, 400, "ton", 300),              # 포=40kg 가정
    ("portland_cement", "시멘트", "kg", 700000, 700, "ton", 300),             # kg=0.001톤
    ("white_cement", "백시멘트", "포", 40, 1.6, "ton", 300),
    ("curb_block", "경계블록", "M", 2500, 2500, "개", 1000),                   # 블록 길이 1m 가정
])
def test_unit_factors_convert_to_frequency_unit(rules, material, name, unit, qty, conv_qty, conv_unit, per):
    row = _one(rules, [_line(name, unit, qty)], material, non_ks=True, makers={"*": 2})[0]
    assert row.qty == pytest.approx(conv_qty) and row.unit == conv_unit
    assert row.count_external == math.ceil(conv_qty / per) * 2


def test_mixed_units_merge_into_one_row(rules):
    rows = _one(rules, [_line("시멘트벽돌", "천매", 60, row=1), _line("시멘트벽돌", "매", 50000, row=2)],
                "concrete_brick", non_ks=True)
    assert len(rows) == 1 and rows[0].qty == 110000 and rows[0].count_external == 2
    rows = _one(rules, [_line("드라이몰탈", "포", 500, row=1), _line("건조모르타르", "kg", 4000, row=2)],
                "dry_cement_mortar")
    assert len(rows) == 1 and rows[0].qty == pytest.approx(24) and rows[0].unit == "ton" and rows[0].count_ks == "◎"


def test_aac_m3_is_not_converted(rules):
    """㎥당 매수는 블록 치수마다 달라 환산하지 않는다 — 매 행과 따로 남는다."""
    rows = _one(rules, [_line("ALC블록", "m3", 30, row=1), _line("ALC블록", "매", 500, row=2)], "aac_block")
    assert sorted(r.unit for r in rows) == ["㎥", "개"]


def test_stone_sources_via_makers(rules):
    row = _one(rules, [_line("화강석 판재", "M2", 800)], "stone", makers={"*": 3})[0]
    assert row.count_external == 3 and row.note == "" and row.count_ks == ""
