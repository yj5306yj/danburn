"""L4-G3 자재 규칙(강재·가설·배관·토공·포장): 로드, 색인 연결, 합성 내역서 행 매칭, 8.11 행 산출."""
from pathlib import Path

import pytest

from danburn.calc import aggregate, match_rule, plan_rows
from danburn.index import coverage, load_index
from danburn.model import BoqLine
from danburn.rules import load_rule, load_rules

RULES = Path(__file__).resolve().parents[2] / "src" / "danburn" / "data" / "rules"

G3 = ("rolled_steel_general", "form_plywood", "welded_wire_mesh", "temp_system_scaffold", "general_pvc_pipe",
      "water_rubber", "backfill", "excavation_bearing", "fill_soil", "road_subgrade", "frost_subbase",
      "asphalt_plant_mix", "asphalt_laying")
KS_EXEMPT = {"rolled_steel_general", "form_plywood", "general_pvc_pipe", "water_rubber"}


@pytest.fixture(scope="module")
def rules():
    return load_rules(RULES)


def _line(name, unit, qty=100.0, spec="합성규격", disc="토목"):
    return BoqLine(disc, "합성", 1, name, spec, unit, qty, "", "사급")


def _rows(line, rules, **kw):
    mats, unread = aggregate([line], rules)
    assert not unread
    return plan_rows(mats, rules, **kw)


@pytest.mark.parametrize("key", G3)
def test_rule_file_links_index(key):
    rule = load_rule(RULES / f"{key}.yaml")
    assert rule.material == key and rule.index_keys == (key,)
    entry = {e.key: e for e in load_index()}[key]
    assert rule.ks_mark == bool(entry.ks)                    # 종별 괄호 KS 가 있을 때만 ◎(※주석 p.52)
    for t in rule.tests:
        assert f"(PDF p.{entry.page})" in t.basis           # 색인 시작 쪽과 같은 쪽 근거
    assert "2026-360" in rule.basis_version


# (자재, 합성 품명, 내역서 단위)
SAMPLES = [
    ("rolled_steel_general", "H형강 SS275", "TON"),
    ("form_plywood", "코팅합판 12mm", "M2"),
    ("welded_wire_mesh", "와이어메쉬", "M2"),
    ("temp_system_scaffold", "시스템비계", "M2"),
    ("general_pvc_pipe", "경질폴리염화비닐관 VG1", "M"),
    ("water_rubber", "고무링", "EA"),
    ("backfill", "되메우기", "M3"),
    ("excavation_bearing", "터파기(토사)", "M3"),
    ("fill_soil", "흙쌓기", "M3"),
    ("road_subgrade", "노상성토", "M3"),
    ("frost_subbase", "보조기층", "M3"),
    ("asphalt_plant_mix", "아스콘 표층", "TON"),
    ("asphalt_laying", "아스콘 표층", "M2"),
]


@pytest.mark.parametrize("key,name,unit", SAMPLES)
def test_synthetic_line_matches(rules, key, name, unit):
    line = _line(name, unit)
    assert match_rule(line, rules).material == key
    rows = [r for r in _rows(line, rules) if r.material == key]
    assert rows
    if key in KS_EXEMPT:                                      # KS 면제 묶음 행
        assert len(rows) == 1 and rows[0].count_ks == "◎" and rows[0].calc_basis == "KS자재"
        assert rows[0].count_external == 0
    else:                                                     # 비KS: 시험마다 행, 횟수 있음
        assert all(r.count_ks == "" for r in rows)
        assert all(r.count_site + r.count_external >= 1 for r in rows)
    covered = frozenset(k for r in rules.values() for k in r.index_keys)   # cli 와 같은 방식
    assert not coverage([line], covered_keys=covered)["uncovered"]


@pytest.mark.parametrize("name,unit", [
    ("흙막이 H형강", "TON"),          # 가설 흙막이용은 별도 종별
    ("H형강 가공조립", "TON"),         # 노무
    ("수도용PVC관", "M"),             # 수도용 경질폴리염화비닐관은 별도 종별
    ("노체성토", "M3"),               # 노체는 별도 종별
    ("투수성아스콘", "TON"),           # 투수성 아스팔트 혼합물은 별도 종별
    ("와이어메쉬 깔기", "M2"),         # 노무
    ("시스템비계", "인"),              # 단위 불일치
])
def test_excluded_lines_not_matched(rules, name, unit):
    rule = match_rule(_line(name, unit), rules)
    assert rule is None or rule.material not in G3


def test_quantity_frequency_counts(rules):
    """물량 비례 빈도: ⌈물량/빈도⌉."""
    def count(name, unit, qty, key, test):
        rows = _rows(_line(name, unit, qty), rules)
        return next(r for r in rows if r.material == key and r.test_type == test)

    r = count("노상성토", "M3", 2500, "road_subgrade", "현장밀도")
    assert r.count_site == 3 and "1,000㎥당1회" in r.calc_basis          # ⌈2500/1000⌉
    r = count("보조기층", "M3", 1200, "frost_subbase", "함수비")
    assert r.count_site == 3                                               # ⌈1200/500⌉
    r = count("아스콘 기층", "M2", 7000, "asphalt_laying", "두께")
    assert r.count_site == 3                                               # ⌈7000/3000⌉
    r = count("노상성토", "M3", 100, "road_subgrade", "프루프롤링")
    assert r.count_site == 3                                               # 3회 이상


def test_optional_tests_excluded_by_default(rules):
    base = {r.test_type for r in _rows(_line("되메우기", "M3"), rules)}
    assert "평판재하" not in base and "현장밀도" in base
    full = {r.test_type for r in _rows(_line("되메우기", "M3"), rules, include_optional=True)}
    assert "평판재하" in full


def test_ks_group_row_lists_required_tests_only(rules):
    row = _rows(_line("PVC관 VG2", "M"), rules)[0]
    assert "인장항복강도" in row.test_type and "IDVP" not in row.test_type
    row = _rows(_line("합판거푸집", "M2"), rules)[0]
    assert "휨강성 변형량" in row.test_type and "폼알데하이드" not in row.test_type
