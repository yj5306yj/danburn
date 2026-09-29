"""종목 단위 KS 필드(ks_substitute·ks_still_test)와 PlanRow.method 로더·기본값 (L14-C)."""
from pathlib import Path

import pytest

from danburn.model import PlanRow
from danburn.rules import load_rule, load_rules

RULES_DIR = Path(__file__).resolve().parents[1] / "src" / "danburn" / "data" / "rules"

HEAD = """material: ks_demo
label: 합성 자재
basis_version: 합성 기준
tests:
"""


def _rule(tmp_path, tests: str):
    p = tmp_path / "ks_demo.yaml"
    p.write_text(HEAD + tests, encoding="utf-8")
    return load_rule(p)


def _test(extra: str = "") -> str:
    return ("  - test_type: 시험가\n    method: KS X 0000\n"
            "    frequency: {per_qty: null, unit: null, text: 제조회사별}\n    basis: 합성 근거\n" + extra)


def test_defaults_keep_current_behavior(tmp_path):
    t = _rule(tmp_path, _test()).tests[0]
    assert t.ks_substitute == "" and t.ks_still_test is False


@pytest.mark.parametrize("value, expected", [("certificate", "certificate"), ("true", "certificate"), ("false", "")])
def test_ks_substitute_values(tmp_path, value, expected):
    t = _rule(tmp_path, _test(f"    ks_substitute: {value}\n")).tests[0]
    assert t.ks_substitute == expected


def test_ks_still_test_reads(tmp_path):
    assert _rule(tmp_path, _test("    ks_still_test: true\n")).tests[0].ks_still_test is True


def test_flow_style_reads(tmp_path):
    line = "  - {test_type: 시험나, ks_substitute: certificate, method: KS X 0001, frequency: {per_qty: null, unit: null, text: 규격별}, basis: 합성}\n"
    assert _rule(tmp_path, line).tests[0].ks_substitute == "certificate"


@pytest.mark.parametrize("extra, msg", [
    ("    ks_substitute: paper\n", "ks_substitute"),
    ("    ks_still_test: 예\n", "ks_still_test"),
    ("    ks_substitute: certificate\n    ks_still_test: true\n", "함께"),
])
def test_bad_values_rejected(tmp_path, extra, msg):
    with pytest.raises(ValueError, match=msg):
        _rule(tmp_path, _test(extra))


def test_planrow_method_default():
    row = PlanRow(discipline="건축", work="", item="합성", test_type="시험가", qty=1, unit="ea", frequency="", calc_basis="")
    assert row.method == ""
    assert PlanRow(discipline="건축", work="", item="합성", test_type="시험가", qty=1, unit="ea", frequency="",
                   calc_basis="", method="KS X 0000").method == "KS X 0000"


@pytest.fixture(scope="module")
def rules():
    return load_rules(RULES_DIR)


def test_rebar_only_chemistry_substituted(rules):
    subs = {t.test_type for t in rules["rebar"].tests if t.ks_substitute}
    assert subs == {"화학성분"}
    assert not any(t.ks_still_test for t in rules["rebar"].tests)


def test_still_test_items(rules):
    def still(key):
        return {t.test_type for t in rules[key].tests if t.ks_still_test}
    assert still("ceramic_tile") == {"꺽임 강도", "미끄럼 저항성(바닥타일)"}   # 미끄럼은 optional(L14-C2)
    assert still("eps_insulation") == {"연소성", "초기 열전도율"}
    assert still("pur_foam_insulation") == {"연소성", "열전도율"}


def test_whole_substitution_example(rules):
    assert all(t.ks_substitute == "certificate" for t in rules["portland_cement"].tests)


def test_ks_fields_only_on_ks_rules(rules):
    """종목 KS 필드는 KS 종별(ks_mark) 규칙에만 쓴다 — 비KS 규칙에 붙으면 뜻이 없다."""
    for r in rules.values():
        if any(t.ks_substitute or t.ks_still_test for t in r.tests):
            assert r.ks_mark, r.material


def test_eco_and_below_fields(tmp_path):
    t = _rule(tmp_path, _test("    eco_substitute: true\n")).tests[0]
    assert t.eco_substitute is True and t.ks_substitute_below is None
    assert _rule(tmp_path, _test("    ks_substitute_below: 10\n")).tests[0].ks_substitute_below == 10
    for bad, msg in (("    eco_substitute: 예\n", "eco_substitute"), ("    ks_substitute_below: 0\n", "ks_substitute_below"),
                     ("    ks_substitute_below: 10\n    ks_still_test: true\n", "함께")):
        with pytest.raises(ValueError, match=msg):
            _rule(tmp_path, _test(bad))


def test_eco_substitute_targets(rules):
    """LHCS 부록4 Ⅴ 친환경 대상 자재의 VOC 종목만 eco_substitute — 거푸집용 합판·보통합판은 대상 아님(Ⅴ 목록 밖)."""
    eco = {k for k, r in rules.items() if any(t.eco_substitute for t in r.tests)}
    assert {"gypsum_board", "tile_adhesive", "veneer_floor", "lh_wallpaper", "lh_kitchen_furniture", "lh_xps_insulation"} <= eco
    assert not {"form_plywood", "ordinary_plywood"} & eco


def test_sewer_pipe_small_lot_substitution(rules):
    for k in ("centrifugal_rc_pipe", "rc_pipe"):
        below = {t.test_type for t in rules[k].tests if t.ks_substitute_below == 10}
        assert below and not any(t.ks_still_test for t in rules[k].tests), k
    assert "방균성능(방균관)" not in {t.test_type for t in rules["centrifugal_rc_pipe"].tests if t.ks_substitute_below}
