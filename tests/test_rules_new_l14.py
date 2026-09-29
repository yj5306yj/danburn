"""L14-C2 새 규칙(무수축 그라우트·데크플레이트·XPS·PF)과 타일 미끄럼 저항성 — 로드·합성 품명 매칭·KS 필드."""
from pathlib import Path

import pytest

from danburn.calc import match_rule
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES_DIR = Path(__file__).resolve().parents[1] / "src" / "danburn" / "data" / "rules"
NEW = ("nonshrink_grout", "lh_deck_plate", "lh_deck_plate_removable", "lh_xps_insulation", "lh_pf_insulation")


@pytest.fixture(scope="module")
def rules():
    return load_rules(RULES_DIR)


@pytest.fixture(scope="module")
def plain(rules):                      # 별표2 현장(발주처 규칙 꺼짐)
    return {k: r for k, r in rules.items() if not r.owner}


@pytest.fixture(scope="module")
def lh(rules):                         # --owner LH
    return {k: r for k, r in rules.items() if not r.owner or r.owner == "LH"}


def _hit(name, unit, rules):
    r = match_rule(BoqLine("건축", "합성", 1, name, "", unit, 10.0, "", "사급"), rules)
    return r.material if r else None


def test_new_rules_load(rules):
    assert set(NEW) <= set(rules)
    assert rules["nonshrink_grout"].owner == ""
    for k in NEW[1:]:
        assert rules[k].owner == "LH", k
        assert "LHCS 10 40 00 V2026.04" in rules[k].basis_version


@pytest.mark.parametrize("name, unit, want_plain, want_lh", [
    ("무수축 그라우트", "포", "nonshrink_grout", "nonshrink_grout"),
    ("무수축몰탈 합성", "ton", "nonshrink_grout", "nonshrink_grout"),
    ("그라우트(팽창제)", "m3", "grout", "grout"),
    ("데크플레이트 합성형 H=75", "m2", None, "lh_deck_plate"),
    ("탈형데크플레이트 합성", "m2", None, "lh_deck_plate_removable"),
    ("데크플레이트 설치", "m2", None, None),
    ("경질발포플라스틱-건축물단열재-XPS 특호 50mm", "m2", "eps_insulation", "lh_xps_insulation"),
    ("압출법보온판 특호", "m2", "eps_insulation", "lh_xps_insulation"),
    ("경질발포플라스틱-건축물단열재-PF 40mm", "m2", None, "lh_pf_insulation"),
    ("페놀폼 단열재", "m2", None, "lh_pf_insulation"),
    ("경질발포플라스틱-건축물단열재-EPS 2종2호 50mm", "m2", "eps_insulation", "lh_eps_insulation"),   # L14-C5: LH는 ISO 4898 규칙
    ("경질발포플라스틱-건축물단열재-PUR 1종3호 100mm", "m2", "pur_foam_insulation", "lh_pur_insulation"),
    ("비드법보온판 2종1호", "m2", "eps_insulation", "lh_eps_insulation"),
    ("압출법 발포폴리스티렌 보온판", "m2", "eps_insulation", "lh_xps_insulation"),
    ("결로방지용발포폴리스티렌단열판-1호10mm", "m2", "eps_insulation", "eps_insulation"),
    ("자기질 바닥타일 합성", "m2", "ceramic_tile", "ceramic_tile"),
])
def test_synthetic_names_match(plain, lh, name, unit, want_plain, want_lh):
    assert _hit(name, unit, plain) == want_plain
    assert _hit(name, unit, lh) == want_lh


def test_nonshrink_grout_substitution(rules):
    r = rules["nonshrink_grout"]
    assert r.ks_mark and r.ks_count == "none"
    sub = {t.test_type for t in r.tests if t.ks_substitute == "certificate"}
    assert sub == {"유하시간", "플로", "응결시간", "블리딩률", "팽창 높이"}
    assert {t.test_type for t in r.tests} - sub == {"압축 강도", "염화물 함유량"}


@pytest.mark.parametrize("key, wire", [("lh_deck_plate", "철선(SWM-F) 인장강도"), ("lh_deck_plate_removable", "철선(SWM-P) 인장강도")])
def test_deck_plate_still_test_all(rules, key, wire):
    r = rules[key]
    assert r.ks_mark and r.ks_count == "makers"
    assert all(t.ks_still_test and not t.ks_substitute for t in r.tests)
    names = {t.test_type for t in r.tests}
    assert wire in names and "주철근 인장강도" in names and "아연도금강판 아연 부착량" in names


def test_insulation_still_test_items(rules):
    def still(k):
        return {t.test_type for t in rules[k].tests if t.ks_still_test and not t.optional}
    assert still("lh_xps_insulation") == {"초기 열전도도", "연소성"}
    assert still("lh_pf_insulation") == {"초기 열전도도", "흡수성"}
    assert still("lh_eps_insulation") == still("lh_pur_insulation") == {"초기 열전도도", "연소성"}
    for k in ("lh_xps_insulation", "lh_pf_insulation", "lh_eps_insulation", "lh_pur_insulation"):   # L14-C5: VOC 는 1.5.1(9) 친환경 대체
        voc = {t.test_type for t in rules[k].tests if t.optional and t.eco_substitute and not t.ks_still_test}
        assert voc == {"폼알데하이드", "톨루엔", "총휘발성유기화합물"}, k
        assert {t.test_type for t in rules[k].tests if t.where == "현장"} == {"선형치수", "밀도"}, k
    assert "phenolic_foam" in rules["lh_pf_insulation"].extra_keys


def test_ceramic_tile_slip_is_optional_still_test(rules):
    t = next(t for t in rules["ceramic_tile"].tests if t.test_type.startswith("미끄럼 저항성"))
    assert t.optional and t.ks_still_test and "LHCS 10 40 00 V2026.04" in t.basis


def test_ductile_fitting_ks_items_substituted(rules):
    subs = {t.test_type for t in rules["lh_ductile_iron_fitting"].tests if t.ks_substitute}
    assert subs == {"KS 규정 시험종목"}


# L14-C4: 승인본 '대응 없음' 보강 — LHCS V2026.04 부록4 종별이 있는 자재의 새 LH 규칙과 동의어
C4_NEW = ["lh_spacer", "lh_auto_door", "lh_polycarbonate_sheet", "lh_patterned_glass", "lh_drain_panel_wall", "lh_drain_panel_floor",
          "lh_digital_door_lock", "lh_filling_pu_foam", "lh_deco_gypsum_cement_board", "lh_setting_block", "lh_magnesium_board",
          "lh_terrazzo", "lh_steel_door_leaf", "lh_door_infill", "lh_steel_door_adhesive", "lh_fire_honeycomb", "lh_fire_gasket",
          "lh_foam_gasket", "lh_insulation_pin_bond", "lh_aluminum_profile"]


def test_c4_rules_are_lh_v2026(rules):
    for k in C4_NEW:
        r = rules[k]
        assert r.owner == "LH" and "V2026.04" in r.basis_version and r.tests, k
        assert all("LHCS 10 40 00 V2026.04 부록4" in t.basis for t in r.tests), k


@pytest.mark.parametrize("name, unit, want", [
    ("간격재(철근폭고정겸용)", "개", "lh_spacer"),
    ("스테인리스창호(자동문)", "개", "lh_auto_door"),
    ("폴리카보네이트시트 합성", "M2", "lh_polycarbonate_sheet"),
    ("무늬유리 합성", "M2", "lh_patterned_glass"),
    ("벽체용배수판", "M2", "lh_drain_panel_wall"),
    ("바닥용배수판 45T", "M2", "lh_drain_panel_floor"),
    ("디지털도어록", "세대", "lh_digital_door_lock"),
    ("도어록", "EA", "lh_door_lock"),
    ("충진용발포우레탄폼", "M", "lh_filling_pu_foam"),
    ("치장석고시멘트판(T6)", "M2", "lh_deco_gypsum_cement_board"),
    ("세팅블록", "M", "lh_setting_block"),
    ("마그네슘보드(결로방지용복합단열재)", "M2", "lh_magnesium_board"),
    ("테라조판", "M2", "lh_terrazzo"),
    ("강제창호가스켓", "개", "lh_fire_gasket"),
    ("난연허니컴", "개", "lh_fire_honeycomb"),
    ("문짝및문틀채움재", "개", "lh_door_infill"),
    ("덕타일추철관(KP식2종)", "M", "lh_ductile_iron_pipe"),
    ("시멘트계액체형방수제", "M2", "liquid_waterproofing"),
    ("창호용망창(방범용)", "개", "lh_insect_screen"),
    ("합성수지제창호형형재", "M", "synthetic_window_profile"),
    ("반자돌림,재료분리대,걸레받이,커튼박스중밀도섬유판(MDF)", "M", "fiberboard"),
    ("결로방지용발포플리스티렌단열판-1호10mm", "M2", "eps_insulation"),
    ("시멘트혼화용폴리머", "M2", None),                     # 시멘트 아님(portland_cement exclude)
    ("경질우레탄폼 보드", "M2", "lh_pur_insulation"),        # '충진'만 뺐다
    ("단열재고정용접착제(G-2)", "M2", "lh_insulation_pin_bond"),
    ("알루미늄창호용형재", "KG", "lh_aluminum_profile"),
    ("H형강말뚝가설(H-300)", "본", "temp_h_pile"),
])
def test_c4_synthetic_names(lh, name, unit, want):
    assert _hit(name, unit, lh) == want


def test_c4_plain_sites_unchanged(plain):
    for name, unit in (("디지털도어록", "세대"), ("테라조판", "M2"), ("간격재", "개")):
        assert _hit(name, unit, plain) is None
