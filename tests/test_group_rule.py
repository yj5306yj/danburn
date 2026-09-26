"""루프 4 공통 틀: 색인 연결(index_keys) 규칙이 동의어로 매칭되고, KS 면제 묶음 행(◎)이 나오며, 색인 대조에서 covered 가 된다."""
import shutil
from pathlib import Path

from danburn.calc import aggregate, plan_rows
from danburn.index import coverage
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[1] / "data" / "rules"


def test_index_linked_group_rule(tmp_path):
    for name in ("ready_mixed_concrete.yaml", "rebar.yaml"):      # 실제 규칙이 늘어도 흔들리지 않게 핵심 규칙만
        shutil.copy(RULES / name, tmp_path)
    (tmp_path / "zz_synthetic.yaml").write_text('''material: synthetic_pvc_waterstop
label: 지수판
basis_version: "합성"
index_keys: [pvc_waterstop]
ks_mark: true
ks_count: none
group_tests: true
group: {frequency: "제조회사별, 제품규격별", basis: "합성 근거"}
tests:
  - {test_type: 겉모양, method: "KS", where: KS, frequency: {per_qty: null, unit: null, text: "제조회사별"}, basis: "실무 관행 — 합성"}
''', encoding="utf-8")
    rules = load_rules(tmp_path)
    assert rules["synthetic_pvc_waterstop"].match_names          # 색인 동의어가 채워짐
    name = rules["synthetic_pvc_waterstop"].match_names[0]
    line = BoqLine("건축", "지급(건)", 5, name, "", "M", 700.0, "", "지급")
    mats, _ = aggregate([line], rules)
    row = [r for r in plan_rows(mats, rules) if r.material == "synthetic_pvc_waterstop"][0]
    assert row.count_ks == "◎" and row.calc_basis == "KS자재" and row.count_external == 0
    cov = coverage([line], covered_keys=frozenset({"pvc_waterstop"}))
    assert not cov["uncovered"]


def test_unit_factors_convert_before_counting(tmp_path):
    (tmp_path / "b.yaml").write_text('''material: synthetic_brick
label: 벽돌
basis_version: "합성"
match: {names: [합성벽돌], units: [천매, ea]}
unit_factors: {천매: [ea, 1000]}
group_tests: true
group: {frequency: "10,000매마다", basis: "합성"}
tests:
  - {test_type: 압축강도, method: "KS", where: 외부, frequency: {per_qty: 10000, unit: ea, text: "10,000매마다"}, basis: "실무 관행 — 합성"}
''', encoding="utf-8")
    rules = load_rules(tmp_path)
    mats, _ = aggregate([BoqLine("건축", "지급(건)", 1, "합성벽돌", "", "천매", 25.0, "", "지급")], rules)
    assert mats[0].unit == "ea" and mats[0].qty == 25000
    row = plan_rows(mats, rules, non_ks=True)[0]
    assert row.count_external == 3                      # ⌈25,000/10,000⌉ × 1곳


def test_group_row_flags_unit_mismatch_and_uses_makers_label(tmp_path):
    (tmp_path / "b.yaml").write_text('''material: synthetic_stone
label: 석재
basis_version: "합성"
match: {names: [합성석재], units: [m3, m2]}
makers_label: 골재원
group_tests: true
group: {frequency: "1,000㎡마다", basis: "합성"}
tests:
  - {test_type: 압축강도, method: "KS", where: 외부, frequency: {per_qty: 1000, unit: m2, text: "1,000㎡마다"}, basis: "실무 관행 — 합성"}
''', encoding="utf-8")
    rules = load_rules(tmp_path)
    m3 = aggregate([BoqLine("건축", "x", 1, "합성석재", "", "M3", 50.0, "", "지급")], rules)[0]
    row = plan_rows(m3, rules, non_ks=True)[0]
    assert "단위 확인" in row.note and row.count_external == 1
    m2 = aggregate([BoqLine("건축", "x", 1, "합성석재", "", "M2", 2500.0, "", "지급")], rules)[0]
    row = plan_rows(m2, rules, non_ks=True, makers={"*": 2})[0]
    assert row.count_external == 6 and "골재원2곳" in row.calc_basis


def test_install_rows_accepted_only_when_no_material_rows():
    rules = load_rules(RULES)
    inst = BoqLine("토목", "내(토)", 1, "PVC지수판 설치", "W=200", "M", 120.0, "", "사급")
    mats, _ = aggregate([inst], rules)
    rows = plan_rows(mats, rules)
    wp = [r for r in rows if r.material == "pvc_waterstop"]
    assert wp and "시공 행 추정" in wp[0].note
    mat = BoqLine("토목", "지급(토)", 2, "PVC지수판", "W=200", "M", 100.0, "", "지급")
    mats, _ = aggregate([inst, mat], rules)
    assert [m.qty for m in mats if m.material == "pvc_waterstop"] == [100.0]      # 자재 행이 있으면 시공 행은 중복으로 버림


def test_l4t3_matching_regressions():
    from danburn.calc import match_rule
    rules = load_rules(RULES)
    L = lambda name, unit: BoqLine("건축", "x", 1, name, "", unit, 1.0, "", "사급")
    assert match_rule(L("10X21/FSD", "개소"), rules).material == "door_set"
    assert match_rule(L("12X10/AW", "개소"), rules).material == "window_set"
    assert match_rule(L("12X10/AWD", "개소"), rules).material == "door_set"
    assert match_rule(L("관보온/유리솜", "M"), rules).material == "mineral_wool"
    assert match_rule(L("와이어메쉬 깔기", "M2"), rules) is None


def test_supplied_dedup_is_per_spec_not_per_material():
    rules = load_rules(RULES)
    L = lambda name, spec, supply: BoqLine("토목", "x", 1, name, spec, "M3", 100.0, "", supply)
    lines = [L("레미콘", "25-21-15", "지급"), L("레미콘", "25-21-15", "사급"), L("레미콘", "25-24-15", "사급")]
    mats, _ = aggregate(lines, rules)
    got = {m.spec: m.qty for m in mats if m.material == "ready_mixed_concrete"}
    assert got == {"25-21-150": 100.0, "25-24-150": 100.0}        # 같은 규격만 중복 제거, 다른 규격 사급은 유지


def test_supplied_dedup_respects_block():
    rules = load_rules(RULES)
    a = BoqLine("기계", "지급(기)", 1, "PVC 파이프", "VG1 D50", "M", 100.0, "A동", "지급")
    b = BoqLine("기계", "내(기)", 2, "오.배수용 PVC 파이프", "VG1 D50", "M", 80.0, "B동", "사급")
    mats, _ = aggregate([a, b], rules, "B동")
    assert [m.qty for m in mats if m.material == "general_pvc_pipe"] == [80.0]   # 다른 블록의 지급은 중복이 아니다
