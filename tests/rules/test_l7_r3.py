"""L7-R3 별표2 미작성 자재 규칙: H형강 말뚝(기초·가설), 콘크리트용 강섬유, 그라우트, 일반구조용 경량 형강,
열간 압연 연강판 및 강대, 콘크리트 구조물 보수용 폴리머시멘트모르타르. 로드·색인 연결, 합성 품명 매칭(노무·다른 종별 제외),
동률 없음, 8.11 행(KS ◎·비KS 50톤 빈도·그라우트 시험별 행)."""
from pathlib import Path

import pytest

from danburn.calc import aggregate, ambiguous, match_rule, plan_rows
from danburn.index import load_index
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[2] / "data" / "rules"
KEYS = ("h_pile", "temp_h_pile", "steel_fiber", "grout", "light_gauge_section", "hot_rolled_mild_sheet",
        "repair_polymer_mortar")
KS = {"h_pile", "temp_h_pile", "steel_fiber", "light_gauge_section", "hot_rolled_mild_sheet", "repair_polymer_mortar"}


@pytest.fixture(scope="module")
def rules():
    return {k: r for k, r in load_rules(RULES).items() if not r.owner or r.owner.upper() == "LH"}


def _line(name, unit, qty=120.0, spec="합성규격", disc="토목"):
    return BoqLine(disc, "내(토)", 3, name, spec, unit, qty, "", "사급", "부지조성 > 흙막이공사")


def _mat(line, rules):
    r = match_rule(line, rules)
    return r.material if r else None


def test_shape_and_index(rules):
    index_keys = {e.key for e in load_index()}
    for key in KEYS:
        r = rules[key]
        assert r.index_keys == (key,) and key in index_keys and not r.owner
        assert r.work and r.tests and all("별표2" in t.basis and "PDF p." in t.basis for t in r.tests)
        assert r.ks_mark == (key in KS)


@pytest.mark.parametrize("name,unit,want", [
    ("H형강말뚝(KS F 4603)", "본", "h_pile"),
    ("H형강말뚝박기(토목)", "본", "temp_h_pile"),              # 흙막이 엄지말뚝 관행 → 가설
    ("H형강말뚝뽑기(토목)", "본", None),                        # 같은 말뚝 인발
    ("엄지말뚝박기용 천공 (L=10.0~20.0m미만)", "본", None),       # 천공 노무
    ("강섬유", "KG", "steel_fiber"),
    ("콘크리트 섬유보강재(투입비포함)-복수적용", "M3", None),        # 섬유 종류 불명(규격에만 강섬유)
    ("어스앵커 그라우팅(토목)", "M3", "grout"),
    ("천공그라우팅 장비 조립,해체(토목)", "회", None),
    ("무수축그라우트", "M3", None),                              # KS F 4044 별도 종별
    ("경량형강", "TON", "light_gauge_section"),
    ("C형강", "KG", "light_gauge_section"),
    ("경량철골천장틀", "TON", None),                             # KS D 3609 천장틀 — 다른 종별
    ("열연철판", "KG", "hot_rolled_mild_sheet"),
    ("열연강판", "TON", "hot_rolled_mild_sheet"),
    ("단면보수 폴리머시멘트모르타르", "M2", "repair_polymer_mortar"),
    ("방수모르타르/폴리머모르타르-복수적용-건조모르타르", "M2", None),  # 방수용
])
def test_match(rules, name, unit, want):
    ln = _line(name, unit)
    assert _mat(ln, rules) == want
    assert ambiguous(ln, rules) == []


def test_sheet_products_not_claimed(rules):
    assert _mat(_line("집수정덮개 열연강판", "TON"), rules) != "hot_rolled_mild_sheet"   # 제품 행(기존 '강판' 동의어는 그대로)


def test_existing_steel_rules_keep_their_rows(rules):
    assert _mat(_line("H형강(H300이하)현장도착도", "TON"), rules) == "rolled_steel_general"
    assert _mat(_line("일반구조용압연강재 SS275", "TON"), rules) == "rolled_steel_general"


def test_ks_rows_are_exempt(rules):
    lines = [_line("H형강말뚝박기(토목)", "본", 40, "H=300,L=12M"), _line("H형강말뚝박기(토목)", "본", 10, "H-300X300"),
             _line("열연철판", "KG", 8000, "SPHC 6.0T")]
    rows = {r.material: r for r in plan_rows(aggregate(lines, rules)[0], rules)}
    pile = rows["temp_h_pile"]
    assert pile.spec == "H-300" and pile.qty == 50 and pile.count_ks == "◎" and pile.calc_basis == "KS자재"
    sheet = rows["hot_rolled_mild_sheet"]
    assert sheet.unit in ("ton", "톤") and sheet.qty == pytest.approx(8.0) and sheet.count_ks == "◎"


def test_non_ks_steel_counts_per_50_ton(rules):
    mats, _ = aggregate([_line("열연강판", "TON", 120, "SPHC 3.2T")], rules)
    row = plan_rows(mats, rules, non_ks=True)[0]
    assert row.count_external == 3                              # ⌈120/50⌉ × 제조사 1곳


def test_h_pile_non_ks_per_200(rules):
    mats, _ = aggregate([_line("H형강말뚝(KS F 4603)", "본", 450, "H-400X400")], rules)
    row = plan_rows(mats, rules, non_ks=True)[0]
    assert row.count_external == 3                              # ⌈450/200⌉


def test_grout_rows_per_test(rules):
    mats, _ = aggregate([_line("어스앵커 그라우팅(토목)", "M3", 30, "")], rules)
    rows = [r for r in plan_rows(mats, rules) if r.material == "grout"]
    assert [r.test_type for r in rows] == ["컨시스턴시", "압축강도", "블리딩률 및 팽창률"]   # 염화물(PSC)은 optional
    assert rows[0].count_site == 1 and rows[1].count_external == 1 and not rows[0].count_ks
    opt = [r for r in plan_rows(mats, rules, include_optional=True) if r.material == "grout"]
    assert opt[-1].test_type == "염화물함유량"
