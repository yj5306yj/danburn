"""L7-R9 LH 수도용 덕타일 주철관·이형관(LHCS 10 40 00 부록 Ⅰ.1 마. 기타 상수도용 관). 별표2에는 주철관 종별 없음.
'닥타일'(오기) 표기, 규격 '시멘트라이닝'이 있어도 주철관으로, 부설·접합·밸브·배수용 NO-HUB 는 제외, 도자기질 타일 오탐 없음."""
from pathlib import Path

import pytest

from danburn.calc import aggregate, ambiguous, match_rule, plan_rows
from danburn.index import identify
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[2] / "src" / "danburn" / "data" / "rules"


@pytest.fixture(scope="module")
def all_rules():
    return load_rules(RULES)


@pytest.fixture(scope="module")
def active(all_rules):
    return {k: r for k, r in all_rules.items() if not r.owner or r.owner.upper() == "LH"}


def _line(name, spec="D150X6,000 (시멘트 라이닝)공장도", unit="본", qty=40.0):
    return BoqLine("토목", "내(토)3", 6, name, spec, unit, qty, "블록B", "사급", "급수간선공사")


def _mat(line, rules):
    r = match_rule(line, rules)
    return r.material if r else None


def test_shape(all_rules):
    pipe, fit = all_rules["lh_ductile_iron_pipe"], all_rules["lh_ductile_iron_fitting"]
    assert pipe.owner == fit.owner == "LH" and not pipe.index_keys and not fit.index_keys
    assert [t.test_type for t in pipe.tests] == ["치수", "KS D 4311에 규정된 시험종목", "수압시험"]
    assert [t.where for t in pipe.tests] == ["현장", "KS", "현장"] and not pipe.group_tests
    assert "수압시험" not in [t.test_type for t in fit.tests] and fit.ks_mark and fit.group_tests


@pytest.mark.parametrize("name,spec,unit,want", [
    ("수도용 닥타일 주철직관(KP식 2종)", "D150X6,000 (시멘트 라이닝)공장도", "본", "lh_ductile_iron_pipe"),
    ("수도용 덕타일 주철관", "D100", "M", "lh_ductile_iron_pipe"),
    ("닥타일이형관(각종)(시멘트라이닝)", "D250MM이하(공장도)", "KG", "lh_ductile_iron_fitting"),
    ("주철관 부설(D=150M/M)", "(자재 미포함)", "M", None),
    ("KP메커니컬 조인트접합(D=150M/M)", "", "개소", None),
    ("배수용주철관(NO-HUB)", "D150 MM(에폭시도장)", "M", None),
    ("제수밸브 (덕타일/수동식)", "D150 MM, KS B 2334", "개", None),
    ("고속도로 통행료(주철관)", "", "회", None),
])
def test_match(active, name, spec, unit, want):
    ln = _line(name, spec, unit)
    assert _mat(ln, active) == want and ambiguous(ln, active) == []


def test_not_tile_or_cement(active):
    for name in ("수도용 닥타일 주철직관(KP식 2종)", "닥타일이형관(각종)(시멘트라이닝)"):
        assert "ceramic_tile" not in [e.key for e in identify(name)]      # '닥타일' 안의 '타일' 오탐 없음(색인 exclude)
        assert _mat(_line(name, unit="본" if "직관" in name else "KG"), active) not in ("portland_cement", "ceramic_tile")


def test_owner_off(all_rules):
    base = {k: r for k, r in all_rules.items() if not r.owner}
    assert _mat(_line("수도용 닥타일 주철직관(KP식 2종)"), base) is None


def test_rows(active):
    lines = [_line("수도용 닥타일 주철직관(KP식 2종)"), _line("닥타일이형관(각종)(시멘트라이닝)", "D250MM이하(공장도)", "KG", 900)]
    rows = plan_rows(aggregate(lines, active)[0], active)
    pipe = [r for r in rows if r.material == "lh_ductile_iron_pipe"]
    assert [(r.spec, r.test_type, r.count_site, r.count_ks) for r in pipe] == [
        ("D150", "치수", 1, ""), ("D150", "KS D 4311에 규정된 시험종목", 0, "KS"), ("D150", "수압시험", 1, "")]
    fit = [r for r in rows if r.material == "lh_ductile_iron_fitting"]
    assert len(fit) == 1 and fit[0].count_ks == "◎" and fit[0].calc_basis == "KS자재"
