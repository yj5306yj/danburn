"""hate(루프 4): 한 행에 여러 규칙이 맞을 때 첫 규칙이 조용히 이기지 않는다."""
from pathlib import Path

from danburn.calc import aggregate, ambiguous, match_candidates, match_rule
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[1] / "src" / "danburn" / "data" / "rules"


def L(name, unit, disc="건축", spec=""):
    return BoqLine(disc, "내역(건)", 1, name, spec, unit, 10.0, "", "사급")


def test_more_specific_name_wins():
    rules = load_rules(RULES)
    assert match_rule(L("대피공간방화문", "개소"), rules).material == "lh_refuge_fire_door"
    assert match_rule(L("복층강화유리", "M2"), rules).material == "insulated_glass"
    assert match_rule(L("떠붙임시멘트", "포"), rules).material == "tile_cement"


def test_composite_item_counts_both_materials():
    rules = load_rules(RULES)
    mats, _ = aggregate([L("보온틀(경질우레탄폼 단열재+석고보드)", "M2"), L("무관한 품명", "식"), L("가+나", "식")], rules)
    assert {"pur_foam_insulation", "gypsum_board"} <= {m.material for m in mats}


def test_every_rule_name_resolves_to_its_own_rule():
    """규칙의 match.names 를 그 규칙 단위로 넣으면 그 규칙(또는 같은 길이로 알려진 겹침)으로 간다."""
    rules = load_rules(RULES)
    stolen = []
    for key, r in rules.items():
        unit = (r.match_units or ("",))[0]
        for n in r.match_names:
            line = L(n, unit)
            got = match_rule(line, rules)
            if got is None or got.material == key:
                continue
            if key in ambiguous(line, rules):     # 같은 길이 동률은 경고로 드러난다
                continue
            best = match_candidates(line, rules)[0][0]
            if best > len(n.replace(" ", "")):    # 이름 안에 더 긴 다른 규칙 이름이 있으면 그쪽이 맞다
                continue
            stolen.append((key, n, got.material))
    assert not stolen, stolen
