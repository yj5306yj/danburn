"""KS 제품 종목별 계산(L14-D2, 메인 결정 2026-09-29) — LH 발주는 종목별 행·총량 기준, 그 밖은 별표2 면제 + 권고."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from danburn.calc import plan_rows, rows_to_json
from danburn.model import MaterialQty
from danburn.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def rules():
    return load_rules(ROOT / "src" / "danburn" / "data" / "rules")


def _m(material, spec, unit, qty):
    return MaterialQty(material=material, spec=spec, unit=unit, qty=qty, block="", discipline="건축")


def _tests(rule):
    return [t for t in rule.tests if not t.optional]


def test_lh_ks_rebar_items(rules):
    rows = plan_rows([_m("rebar", "SD500 D10", "ton", 240.0)], rules, makers={"*": 3}, owner="LH")
    assert [r.test_type for r in rows] == [t.display or t.test_type for t in _tests(rules["rebar"])]
    chem = [r for r in rows if r.test_type == "화학성분"]
    assert len(chem) == 1 and chem[0].count_site == chem[0].count_external == 0
    assert chem[0].note == "성적서대체" and chem[0].calc_basis == "3개업체×규격별 1회"      # 0회라도 산출근거는 남긴다(승인본)
    others = [r for r in rows if r.test_type != "화학성분"]
    assert all(r.count_external == 3 and r.count_site == 0 and r.note == "" for r in others)   # ⑤ 부분 갈음의 나머지: 의뢰 계상
    assert all(r.count_ks == "◎" and r.qty == 240.0 for r in rows)


def test_lh_ks_cement_all_substituted(rules):
    rows = plan_rows([_m("portland_cement", "(규격 없음)", "ton", 900.0)], rules, owner="LH")
    assert len(rows) == len(_tests(rules["portland_cement"]))
    assert all(r.count_site == r.count_external == 0 and r.note == "성적서대체" for r in rows)


def test_lh_ks_eps_counts_still_test_and_defaults_rest_to_certificate(rules):
    rows = plan_rows([_m("eps_insulation", "규격별", "m2", 2500.0)], rules, makers={"eps_insulation": 2}, owner="LH")
    assert len(rows) == len(_tests(rules["eps_insulation"]))
    n = math.ceil(2500 / 1000) * 2
    still = [r for r in rows if "KS라도 시험" in r.note]
    assert {r.test_type for r in still} == {"연소성", "초기 열전도율"}
    assert all(r.count_site + r.count_external == n for r in still)          # ② 총량 기준 ⌈2500/1000⌉×2
    site = {t.display or t.test_type for t in rules["eps_insulation"].tests if t.where == "현장"}   # rules 워커가 현장으로 바꾸면 ③
    assert all(r.count_site == n for r in rows if r.test_type in site)
    rest = [r for r in rows if r not in still and r.test_type not in site]
    assert rest and all(r.count_site == r.count_external == 0 and r.note == "KS 성적서대체" for r in rest)   # ⑥
    assert all(r.calc_basis == "2,500㎡/1,000㎡=3회×2개업체" for r in rows)


def test_lh_ks_without_makers_marks_detail_not_note(rules):
    from danburn.calc import makers_confirmation
    rows = plan_rows([_m("eps_insulation", "규격별", "m2", 500.0), _m("rebar", "SD500 D10", "ton", 10.0)], rules, owner="LH")
    assert not any("제조사 수 확인" in r.note for r in rows)
    counted = [r for r in rows if r.count_site + r.count_external]
    assert counted and all("1곳으로 계산" in r.detail for r in counted)
    assert not any("1곳으로 계산" in r.detail for r in rows if not r.count_site + r.count_external)
    assert makers_confirmation(rows) == "제조사(골재원) 수를 1곳으로 계산한 자재 2종 — 다르면 --makers 또는 project.yaml 제조사수"
    assert makers_confirmation(plan_rows([_m("rebar", "SD500 D10", "ton", 10.0)], rules, makers={"rebar": 3})) is None


def test_lh_ks_default_certificate_for_plain_ks(rules):
    rows = plan_rows([_m("gypsum_board", "일반", "m2", 3000.0)], rules, owner="LH")   # 갈음·예외 표시 없는 KS 종별 → ⑥
    assert rows and all(r.count_site == r.count_external == 0 and r.note == "KS 성적서대체" for r in rows)
    assert all(r.calc_basis and r.count_ks == "◎" for r in rows)


def test_lh_ks_site_items_counted(rules):
    rows = plan_rows([_m("lh_xps_insulation", "규격별", "m2", 2500.0)], rules, owner="LH")
    by = {r.test_type: r for r in rows}
    assert by["선형치수"].count_site == by["밀도"].count_site == 3                    # ③ where 현장 → 현장 계상
    assert by["초기 열전도도"].count_external == by["연소성"].count_external == 3    # ②
    assert by["압축강도"].count_external == 0 and by["압축강도"].note == "KS 성적서대체"   # ⑥


def test_lh_ks_eco_item_substituted(rules):
    import dataclasses
    from types import SimpleNamespace
    from danburn.calc import ks_item_rows
    rule = rules["gypsum_board"]
    tests = [SimpleNamespace(**{**{f.name: getattr(t, f.name) for f in dataclasses.fields(t)}, "eco_substitute": i == 0})
             for i, t in enumerate(rule.tests)]
    tests[0].where = "외부"
    rows = ks_item_rows(_m("gypsum_board", "일반", "m2", 100.0), dataclasses.replace(rule, tests=tests))
    assert rows[0].note == "친환경성적서/환경표지인증서 대체" and rows[0].count_external == 0   # ④


@pytest.mark.parametrize("material", ["centrifugal_rc_pipe", "rc_pipe"])
def test_lh_small_quantity_pipe_substituted_below_threshold(rules, material):
    """LHCS 하수도용 관: 소량(10개 미만) 사용 규격은 KS면 전 종목 성적서 갈음, 그 이상이면 시험(L14-D5)."""
    below = [t for t in _tests(rules[material]) if t.ks_substitute_below]
    assert below
    names = {t.display or t.test_type for t in below}
    small = [r for r in plan_rows([_m(material, "D450", "ea", 8.0)], rules, owner="LH") if r.test_type in names]
    assert small and all(r.count_site == r.count_external == 0 and "성적서대체(소량 10개 미만)" in r.note for r in small)
    big = [r for r in plan_rows([_m(material, "D450", "ea", 40.0)], rules, owner="LH") if r.test_type in names]
    assert big and all(r.count_site + r.count_external >= 1 and "성적서대체" not in r.note for r in big)   # ⑤ 계상
    by_len = [r for r in plan_rows([_m(material, "D450", "m", 8.0)], rules, owner="LH") if r.test_type in names]
    assert all(r.count_site + r.count_external >= 1 and "10개 미만 사용 규격이면" in r.note for r in by_len)   # 개수 모름 → 계상 + 안내
    other = plan_rows([_m(material, "D450", "본", 8.0)], rules)                                  # 별표2 현장은 지금처럼 면제 묶음 행
    assert other[0].calc_basis == "KS자재"


def test_makers_lookup_by_material_key_and_star_scope(rules):
    rebar, eps = _m("rebar", "SD500 D10", "ton", 10.0), _m("eps_insulation", "규격별", "m2", 100.0)
    for table in ({"rebar": 3}, {"철근": 3}, {"rebar:SD500 D10": 3}, {"*": 3}):
        row = [r for r in plan_rows([rebar], rules, makers=table, owner="LH") if r.test_type == "인장강도"][0]
        assert row.count_external == 3, table
    star = plan_rows([eps], rules, makers={"*": 3}, owner="LH")                    # '*' 는 KS 비철근 자재에 번지지 않는다
    assert all(r.count_external in (0, 1) for r in star)
    assert all(r.count_external in (0, 3) for r in plan_rows([eps], rules, makers={"eps_insulation": 3}, owner="LH"))
    non_ks = plan_rows([eps], rules, makers={"*": 2}, non_ks=True)                 # 비KS 는 지금처럼 '*' 적용
    assert non_ks[0].count_external == 2


def test_other_owner_keeps_exemption_and_advises_still_test(rules):
    rows = plan_rows([_m("eps_insulation", "규격별", "m2", 2500.0)], rules, makers={"*": 2})
    main, *still = rows
    assert main.calc_basis == "KS자재" and main.count_ks == "◎" and main.count_external == main.count_site == 0
    assert "연소성" not in main.test_type
    assert {r.test_type for r in still} == {"연소성", "초기 열전도율"}
    assert all(r.note == "권고: KS라도 시험(LHCS 부록4)" and r.count_external == 0 for r in still)
    cement = plan_rows([_m("portland_cement", "(규격 없음)", "ton", 900.0)], rules)
    assert len(cement) == 1 and "성적서대체" not in cement[0].note                # 갈음 필드는 LH 에서만


def test_non_ks_ignores_new_fields(rules):
    for owner in ("", "LH"):
        rows = plan_rows([_m("eps_insulation", "규격별", "m2", 2500.0)], rules, makers={"*": 2}, non_ks=True,
                         owner=owner)
        assert len(rows) == 1 and rows[0].count_external == math.ceil(2500 / 1000) * 2
        assert rows[0].count_ks == "" and "KS" not in rows[0].note


def test_method_filled_on_every_row(rules):
    mats = [_m("rebar", "SD500 D10", "ton", 10.0), _m("eps_insulation", "규격별", "m2", 100.0),
            _m("ready_mixed_concrete", "25-24-150", "m3", 500.0)]
    for owner in ("", "LH"):
        rows = plan_rows(mats, rules, owner=owner)
        assert rows and all(r.method for r in rows)
    grouped = plan_rows([_m("eps_insulation", "규격별", "m2", 100.0)], rules)[0]
    methods = grouped.method.split(", ")
    assert len(methods) == len(set(methods))                                     # 묶음 행은 중복 없이
    conc = plan_rows([mats[2]], rules)
    by_test = {t.display or t.test_type: t.method for t in rules["ready_mixed_concrete"].tests}
    assert all(r.method == by_test[r.test_type] for r in conc)


def test_rows_to_json_has_method(rules):
    rows = plan_rows([_m("rebar", "SD500 D10", "ton", 10.0)], rules, owner="LH")
    js = rows_to_json(rows)
    assert all("method" in x for x in js) and js[0]["method"] == rows[0].method != ""
