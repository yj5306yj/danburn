"""L7-R1 설비(기계) LH 규칙: LHCS 10 40 00:2020 부록 Ⅲ. 기계분야 — 바닥 배수트랩, 폴리부틸렌관, PVC 복층관·삼중관.
로드, --owner LH 일 때만 켜짐, 합성 내역 행 매칭(부속·보온·슬리브 제외), 용도·관 묶음, 공구마다 1회."""
from pathlib import Path

import pytest

from danburn.calc import aggregate, match_rule, optional_tests, plan_rows
from danburn.extra import flag_extras
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[1] / "src" / "danburn" / "data" / "rules"
MECH = ("lh_floor_drain_trap", "lh_pb_pipe", "lh_pvc_multilayer_pipe")


@pytest.fixture(scope="module")
def all_rules():
    return load_rules(RULES)


@pytest.fixture(scope="module")
def active(all_rules):
    return {k: r for k, r in all_rules.items() if not r.owner or r.owner.upper() == "LH"}


@pytest.fixture(scope="module")
def base(all_rules):
    return {k: r for k, r in all_rules.items() if not r.owner}


def _line(name, unit="개소", qty=120.0, spec="D50"):
    return BoqLine("기계", "내(기)", 9, name, spec, unit, qty, "", "사급", "아파트 > 기계설비공사 > 오배수공사")


def _mat(line, rules):
    r = match_rule(line, rules)
    return r.material if r else None


def test_mech_rules_shape(all_rules):
    for key in MECH:
        r = all_rules[key]
        assert r.owner == "LH" and not r.index_keys and r.group_tests
        assert "Ⅲ. 기계분야" in r.group_basis and r.group_frequency == "공구마다 1회"
        assert all("LHCS" in t.basis and t.method for t in r.tests)


def test_owner_off_no_match(base):
    assert _mat(_line("욕실 배수 상트랩(일반형)"), base) is None
    assert _mat(_line("PB관배관", "M"), base) is None


@pytest.mark.parametrize("name,unit,want", [
    ("욕실 배수 상트랩(일반형)", "개소", "lh_floor_drain_trap"),
    ("세탁실 배수 상트랩(일반형)", "개소", "lh_floor_drain_trap"),
    ("배수트랩 설치(일반형)", "개소", "lh_floor_drain_trap"),
    ("배수트랩 성형슬리브(일반형,욕실)", "개소", None),          # 매립 슬리브는 트랩이 아님
    ("발코니PVC 배관(통합배수트랩)", "M", "general_pvc_pipe"),    # 트랩에 잇는 VG2 배관 행(트랩 자체는 상트랩 행) — L7-R2
    ("발코니PVC 배관(통합트랩)(지급)", "M", None),               # 지급 관을 까는 행 — 관 물량 중복(L7-R2)
    ("오배수PVC 배관(지급자재)", "M", None),
    ("PVC P-트랩", "개", None),                                   # 세면기 트랩
    ("PB관배관(난방용)", "M", "lh_pb_pipe"),
    ("PB관 보온(매직)", "M", None),
    ("PB관용 써포트슬리브", "개", None),
    ("PB이중관용 원형수전박스", "개", None),
    ("오배수저소음PVC 배관(복수적용)", "M", "lh_pvc_multilayer_pipe"),
    ("PVC 삼중관", "M", "lh_pvc_multilayer_pipe"),
    ("저소음90도엘보(복수적용)", "개", None),
])
def test_match(active, name, unit, want):
    assert _mat(_line(name, unit), active) == want


def test_pb_composite_row(active):
    mats, _ = aggregate([_line("일체형(PB+CD관)이중배관(급수,급탕용)", "M", 300.0, "D16 MM(CD관 22C)")], active)
    assert [m.material for m in mats] == ["lh_pb_pipe"]


def test_trap_groups_by_use_and_counts_once(active):
    lines = [_line("욕실 배수 상트랩(일반형)", qty=90), _line("욕실 배수 상트랩(일반형)", qty=40, spec="D75"),
             _line("발코니 배수 상트랩(통합형,세탁)", qty=50, spec="D100"), _line("발코니 배수 상트랩(일반형)", qty=5)]
    mats, _ = aggregate(lines, active)
    by = {m.spec: m.qty for m in mats if m.material == "lh_floor_drain_trap"}
    assert by == {"욕실용": 130, "세탁용": 50, "발코니 등": 5}
    rows = [r for r in plan_rows(mats, active) if r.material == "lh_floor_drain_trap"]
    assert len(rows) == 3 and all(r.count_external == 1 and r.count_ks == "" for r in rows)


def test_pipes_one_row_per_tool(active):
    lines = [_line("PB관배관", "M", 500, "D20 MM"), _line("PB관배관(난방용)", "M", 800, "D16 MM"),
             _line("화장실저소음PVC 배관(복수적용)", "M", 400, "D50 MM"), _line("오배수저소음PVC 배관(복수적용)", "M", 900, "D100 MM")]
    mats, _ = aggregate(lines, active)
    rows = {r.material: r for r in plan_rows(mats, active) if r.material.startswith("lh_p")}
    assert rows["lh_pb_pipe"].qty == 1300 and rows["lh_pb_pipe"].count_external == 1
    assert rows["lh_pvc_multilayer_pipe"].qty == 1300 and rows["lh_pvc_multilayer_pipe"].count_external == 1
    assert "촉진내후성" not in rows["lh_pvc_multilayer_pipe"].test_type        # 규격1 전용 → optional(묶음 행에서 빠짐)
    assert any(o.startswith("PVC 복층관·삼중관 촉진내후성") for o in optional_tests(active))   # 요약에 안내


@pytest.mark.parametrize("name,key", [                          # L7-R2: 출처 미확보 설비 — 규칙 없이 “발주처 기준 필요”
    ("욕실수납장(설치도,내부콘센트2구형 포함)", "bath_cabinet"),
    ("슬라이딩형 수납장 설치(내부콘센트2구형)", "bath_cabinet"),
    ("일체형 고강도 PVC 지수판 슬리브 설치", "high_strength_pvc_pipe"),
    ("에어컨 냉매배관(거실용) 설치", "refrigerant_fitting"),
    ("압력시험 세트(냉매배관용,무용접)", "refrigerant_fitting"),
    ("감압밸브(세대용) 설치", "pressure_reducing_valve"),
])
def test_unsourced_mech_items_flagged(active, name, key):
    ln = _line(name)
    assert match_rule(ln, active) is None                          # 시험계획을 지어내지 않는다
    assert [h["key"] for h in flag_extras([ln])["owner_standard_needed"]] == [key]


def test_mech_items_not_claimed_by_rules(all_rules):
    keys = {"bath_cabinet", "high_strength_pvc_pipe", "refrigerant_fitting", "pressure_reducing_valve"}
    assert not keys & {k for r in all_rules.values() for k in r.extra_keys}
    got = [h["key"] for h in flag_extras([_line("고강도PE관 티"), _line("고강도연마타일붙이기")])["owner_standard_needed"]]
    assert "high_strength_pvc_pipe" not in got and got == ["hs_pe_corrugated_pipe"]   # PE관은 PE 파형관 항목(L7-R7)
