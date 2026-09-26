"""L7-R4 자재 규칙(드레인보드·일반용 PE관·철근콘크리트관·도로표지용 도료·이중벽 고밀도 PE관·망판유리·이중바닥재):
로드, 색인 연결, 합성 내역서 행 매칭, 8.11 행 산출, 노무·다른 종별 행 제외."""
from pathlib import Path

import pytest

from danburn.calc import aggregate, match_rule, plan_rows
from danburn.index import coverage, load_index
from danburn.model import BoqLine
from danburn.rules import load_rule, load_rules

RULES = Path(__file__).resolve().parents[2] / "src" / "danburn" / "data" / "rules"

R4 = ("drain_board", "general_pe_pipe", "rc_pipe", "road_marking_paint", "double_wall_hdpe_pipe", "wired_glass",
      "raised_floor")
PAGES = {"drain_board": (17,), "general_pe_pipe": (18,), "rc_pipe": (18,), "road_marking_paint": (29,),
         "double_wall_hdpe_pipe": (30,), "wired_glass": (38,), "raised_floor": (42, 43)}
TEST_COUNTS = {"drain_board": 5, "general_pe_pipe": 5, "rc_pipe": 5, "road_marking_paint": 22,
               "double_wall_hdpe_pipe": 5, "wired_glass": 2, "raised_floor": 9}


@pytest.fixture(scope="module")
def rules():
    return {k: r for k, r in load_rules(RULES).items() if not r.owner or r.owner.upper() == "LH"}   # --owner LH


def _line(name, unit, qty=100.0, spec="합성규격", disc="토목", supply="사급"):
    return BoqLine(disc, "합성", 1, name, spec, unit, qty, "", supply)


def _rows(lines, rules, **kw):
    mats, unread = aggregate(lines, rules)
    assert not unread
    return plan_rows(mats, rules, **kw)


@pytest.mark.parametrize("key", R4)
def test_rule_file_links_index(key):
    rule = load_rule(RULES / f"{key}.yaml")
    assert rule.material == key and rule.index_keys == (key,)
    entry = {e.key: e for e in load_index()}[key]
    assert rule.ks_mark == bool(entry.ks)                    # 종별 괄호 KS 가 있을 때만 ◎(※주석 p.52)
    assert len(rule.tests) == TEST_COUNTS[key]               # 별표2 종목 수(도료는 공통 8 + 종류별 14)
    for t in rule.tests:
        assert any(f"(PDF p.{p})" in t.basis for p in PAGES[key])
    assert "2026-360" in rule.basis_version and rule.work


# (자재, 합성 품명, 규격, 내역서 단위, 공급)
SAMPLES = [
    ("drain_board", "옹벽배수처리 (드레인보드)", "배수용", "M2", "사급"),
    ("general_pe_pipe", "일반용 폴리에틸렌관", "D100", "M", "사급"),
    ("centrifugal_rc_pipe", "철근콘크리트관(우수관)", "D-450MM,모래기초", "M", "사급"),   # 우수관 = 원심력 흄관(실무자 확인)
    ("road_marking_paint", "차선도색(백색, 실선)", "융착식 도료 수동식", "M2", "사급"),
    ("road_marking_paint", "주차선도색", "(상온수동식)", "M2", "사급"),
    ("double_wall_hdpe_pipe", "폴리에틸렌(PE)이중벽관", "D150mm,유공관", "M", "지급"),
    ("wired_glass", "망입유리끼우기", "T7", "M2", "사급"),
    ("raised_floor", "ACCESS FLOOR", "H:200,타일마감", "M2", "사급"),
]


@pytest.mark.parametrize("key,name,spec,unit,supply", SAMPLES)
def test_synthetic_line_matches(rules, key, name, spec, unit, supply):
    line = _line(name, unit, spec=spec, supply=supply)
    assert match_rule(line, rules).material == key
    rows = [r for r in _rows([line], rules) if r.material == key]
    assert len(rows) == 1
    if rules[key].ks_mark:                                    # KS 면제 묶음 행
        assert rows[0].count_ks == "◎" and rows[0].calc_basis == "KS자재" and rows[0].count_external == 0
    else:
        assert rows[0].count_ks == "" and rows[0].count_external >= 1
    covered = frozenset(k for r in rules.values() for k in r.index_keys)
    assert not coverage([line], covered_keys=covered)["uncovered"]


@pytest.mark.parametrize("name,unit", [
    ("PVC 이중벽관 부설 및 접합", "M"),      # PVC 는 이중벽 고밀도 PE관이 아님 + 노무
    ("PVC이중벽관", "M"),                   # PVC 이중벽관은 이 종별 아님
    ("PE관 접합 및 부설", "M"),             # 노무
    ("고강도PE관 티", "개"),                # 고강도(파형) PE관 이음관 — 일반용 PE관 아님
    ("PB관보온(발포폴리에틸렌)", "M"),       # 보온재
    ("P.E 원형거푸집", "M"),                # 거푸집
    ("흄관용 고무링", "개"),                 # 부속
    ("원심력철근콘크리트관", "M"),           # 원심력(KS F 4403)은 별도 규칙
    ("차선규제봉 설치", "개소"),             # 도료 아님
    ("ACCESS FLOOR 마구리면", "M2"),         # 끝막음 부재
])
def test_other_lines_not_matched(rules, name, unit):
    rule = match_rule(_line(name, unit), rules)
    assert rule is None or rule.material not in R4 or (name.startswith("원심력") and rule.material != "rc_pipe")


def test_centrifugal_pipe_keeps_its_rule(rules):
    assert match_rule(_line("원심력철근콘크리트관", "M"), rules).material == "centrifugal_rc_pipe"


def test_drain_board_non_ks_counts_by_area(rules):
    row = _rows([_line("드레인보드", "M2", 45000)], rules)[0]
    assert row.material == "drain_board" and row.count_external == 3          # ⌈45,000/20,000⌉ × 제조사 1곳
    assert "내약품성" not in row.test_type                                     # pH 조건부(optional)


def test_road_paint_rows_split_by_type_and_optional_type_tests(rules):
    lines = [_line("차선도색(백색, 실선)", "M2", spec="융착식 도료 수동식"),
             _line("차선도색(황색, 실선)", "M2", spec="융착식 도료 수동식"),
             _line("주차선도색", "M2", spec="(상온수동식)")]
    rows = [r for r in _rows(lines, rules) if r.material == "road_marking_paint"]
    assert sorted(r.spec for r in rows) == ["상온형", "융착형"]
    assert all("유리알" not in r.test_type and "은폐율" not in r.test_type for r in rows)   # 종류별 종목은 optional
    opt = {t.test_type for t in rules["road_marking_paint"].tests if t.optional}   # 묶음 행은 optional 을 안 싣고 목록으로 알린다
    assert len(opt) == 14 and {"유리알 함유량(4종)", "은폐율(1~3종)"} <= opt


def test_rc_pipe_groups_by_nominal_diameter(rules):
    lines = [_line("철근콘크리트관(하수관)", "M", spec="D-450MM,콘크리트기초(90도)"),
             _line("철근콘크리트관(하수관)", "M", spec="D-450MM,모래기초(60도)"),
             _line("철근콘크리트관(하수관)", "M", spec="D-600MM,콘크리트기초(90도)")]
    rows = [r for r in _rows(lines, rules) if r.material == "rc_pipe"]
    assert sorted(r.spec for r in rows) == ["D450", "D600"]
    non_ks = [r for r in _rows(lines, rules, non_ks=True) if r.material == "rc_pipe"]
    assert all("단위 확인" in r.note for r in non_ks)                          # 빈도 개수, 내역 m
