from pathlib import Path

import pytest

from danburn.rules import load_rules

RULES_DIR = Path(__file__).resolve().parents[1] / "src" / "danburn" / "data" / "rules"


@pytest.fixture(scope="module")
def rules():
    return load_rules(RULES_DIR)


def test_both_materials_load(rules):
    assert {"ready_mixed_concrete", "rebar"} <= set(rules)
    assert rules["ready_mixed_concrete"].label == "콘크리트"
    assert rules["rebar"].label == "철근"


def test_match_hints(rules):
    assert "레미콘" in rules["ready_mixed_concrete"].match_names
    assert rules["ready_mixed_concrete"].match_units == ("m3",)
    assert "철근" in rules["rebar"].match_names
    assert rules["rebar"].match_units == ("ton",)


def test_every_test_has_required_fields(rules):
    for rule in rules.values():
        assert rule.basis_version
        assert rule.tests
        for t in rule.tests:
            assert t.test_type, rule.material
            assert t.method, (rule.material, t.test_type)
            assert t.frequency.text, (rule.material, t.test_type)
            assert t.basis, (rule.material, t.test_type)
            assert ("PDF p." in t.basis or t.basis.startswith("실무 관행")
                    or (rule.owner and "LHCS" in (t.basis + rule.basis_version))), (rule.material, t.test_type)  # 법령 쪽수·실무 관행·발주처 기준(LHCS 절)
            if t.frequency.per_qty is not None:
                assert t.frequency.unit, (rule.material, t.test_type)
            assert t.where in ("현장", "외부", "KS")


def test_expected_test_types(rules):
    concrete = {t.test_type for t in rules["ready_mixed_concrete"].tests}
    assert {"슬럼프 또는 슬럼프플로", "공기량", "염화물 함유량", "압축강도", "단위수량"} <= concrete
    rebar = {t.test_type for t in rules["rebar"].tests}
    assert {"화학성분", "인장강도", "항복점 또는 항복강도", "굽힘성"} <= rebar


def test_missing_unit_rejected(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "material: x\nlabel: x\nbasis_version: x\ntests:\n"
        "  - {test_type: a, method: m, basis: b, frequency: {per_qty: 10, text: t}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unit"):
        load_rules(tmp_path)


def test_optional_flexural_strength_is_excluded_from_default_rows():
    from danburn.calc import plan_rows, optional_tests
    from danburn.model import MaterialQty
    rules = load_rules(RULES_DIR)
    rows = plan_rows([MaterialQty("ready_mixed_concrete", "25-24-150", "m3", 240.0, "", "건축")], rules)
    assert "휨강도" not in {r.test_type for r in rows}
    assert any("휨강도" in s for s in optional_tests(rules))


def test_compressive_strength_lot_model():
    from danburn.calc import plan_rows, parse_sets
    from danburn.model import MaterialQty
    rules = load_rules(RULES_DIR)
    m = MaterialQty("ready_mixed_concrete", "25-24-150", "m3", 1000.0, "", "건축")
    comp = {r.test_type: r for r in plan_rows([m], rules)}["압축강도"]
    assert comp.count_site == 12 and comp.calc_basis.endswith("360㎥당4조")   # 3로트 × 기본 4조(28일3+7일1)
    assert "거푸집 해체용 조 없음" in comp.detail and not comp.note
    comp = {r.test_type: r for r in plan_rows([m], rules, formwork_sets=parse_sets("25-24-150=3"))}["압축강도"]
    assert comp.count_site == 21 and comp.calc_basis.endswith("360㎥당7조")   # 수직·수평·예비 3조 추가
    comp = {r.test_type: r for r in plan_rows([m], rules, parse_sets("*=5"))}["압축강도"]
    assert comp.count_site == 15                                              # 통째 지정이 우선
    slump = {r.test_type: r for r in plan_rows([m], rules)}["슬럼프"]
    assert slump.count_site == 9                                                # ⌈1000/120⌉


def test_specimen_making_row_matches_compressive_strength():
    from danburn.calc import plan_rows, parse_sets
    from danburn.model import MaterialQty
    rows = {r.test_type: r for r in plan_rows([MaterialQty("ready_mixed_concrete", "25-24-150", "m3", 1000.0, "", "건축")],
                                               load_rules(RULES_DIR), parse_sets("*=7"))}
    assert rows["공시체제작"].count_site == rows["압축강도"].count_site == 21


def test_formwork_parts_by_member_type():
    from danburn.calc import parse_sets
    assert parse_sets("25-24-150=수직+수평+예비,25-24-80=수직+예비,*=0") == {"25-24-150": 3, "25-24-80": 2, "*": 0}
    with pytest.raises(ValueError):
        parse_sets("25-24-150=기둥")


def test_practice_omitted_rows_and_discipline_keys():
    from danburn.calc import plan_rows, parse_sets
    from danburn.model import MaterialQty
    rules = load_rules(RULES_DIR)
    a = MaterialQty("ready_mixed_concrete", "25-24-150", "m3", 720.0, "", "건축")
    c = MaterialQty("ready_mixed_concrete", "25-24-150", "m3", 720.0, "", "토목")
    rows = plan_rows([a, c], rules, formwork_sets=parse_sets("건축:25-24-150=수직+수평+예비"))
    kinds = {r.test_type for r in rows}
    assert not kinds & {"온도", "배합설계", "현장배합수정", "휨강도"}
    comp = {(r.discipline, r.test_type): r.count_site for r in rows}
    assert comp[("건축", "압축강도")] == 14 and comp[("토목", "압축강도")] == 8     # 2로트 × 7조 / 4조
    assert "온도" in {r.test_type for r in plan_rows([a], rules, include_optional=True)}


def test_rebar_group_row_ks_and_non_ks():
    from danburn.calc import rebar_group_row
    from danburn.model import MaterialQty
    rule = load_rules(RULES_DIR)["rebar"]
    assert rule.group_tests
    m = MaterialQty("rebar", "SD400 D13", "ton", 120.0, "", "건축")

    row = rebar_group_row(m, rule)                       # 기본: KS, 제조회사 1곳(확인 필요)
    assert row.test_type.split(",")[0] == "겉모양" and "화학성분" in row.test_type and "탄소당량(용접용)" in row.test_type
    assert row.count_external == 1 and row.count_site == 0
    assert row.calc_basis == "KS자재 - 제조회사 및 제품규격별 1회"
    assert row.note == "" and "1곳으로 계산" in row.detail          # 행 비고 대신 detail → 요약 한 줄(L14-D4)
    assert "KS제품" in row.frequency and "비KS제품" in row.frequency and "50톤" in row.frequency
    assert "p.52" in row.basis and "제91조제1항" in row.basis
    assert row.item == "철근(SD400 D13)"

    assert rebar_group_row(m, rule, ks=True, makers=3).count_external == 3
    non_ks = rebar_group_row(m, rule, ks=False, makers=2)
    assert non_ks.count_external == 6                    # ⌈120/50⌉=3 × 2곳
    assert non_ks.note == "" and "제조회사2곳" in non_ks.calc_basis


def test_rebar_ks_footnote_cited_in_every_test(rules):
    for t in rules["rebar"].tests:
        assert "p.52" in t.basis and "p.52" in t.conditions


def test_small_concrete_quantity_is_flagged():
    from danburn.calc import plan_rows
    from danburn.model import MaterialQty
    rows = plan_rows([MaterialQty("ready_mixed_concrete", "25-21-120", "m3", 10.0, "", "건축")], load_rules(RULES_DIR))
    comp = {r.test_type: r for r in rows}["압축강도"]
    assert comp.note == "생략 가능" and "3.12.5.1(5)" in comp.detail


def test_rebar_labor_rows_are_not_material():
    from danburn.calc import match_rule
    from danburn.model import BoqLine
    rules = load_rules(RULES_DIR)
    labor = BoqLine("건축", "내역(건)", 1, "철근 공장가공 및 조립", "보통", "TON", 5.0, "", "사급")
    mat = BoqLine("건축", "내역(건)", 2, "이형봉강(SD500, 현장도착도)", "H-13", "TON", 5.0, "", "사급")
    assert match_rule(labor, rules) is None and match_rule(mat, rules).material == "rebar"
