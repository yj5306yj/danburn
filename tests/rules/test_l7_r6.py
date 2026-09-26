"""L7-R6 LH 경량철골 천정틀(LHCS 10 40 00 부록 Ⅱ.18, KS D 3609) + 별표2 밖 목록(섬유보강재·방수용 폴리머 모르타르).
천정틀 공사 행 매칭(석고보드·천정판·알루미늄 제외), --owner LH 일 때만, 한 행 KS ◎, 목록 경고."""
from pathlib import Path

import pytest

from danburn.calc import aggregate, ambiguous, match_rule, plan_rows
from danburn.extra import flag_extras
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[2] / "data" / "rules"


@pytest.fixture(scope="module")
def all_rules():
    return load_rules(RULES)


@pytest.fixture(scope="module")
def active(all_rules):
    return {k: r for k, r in all_rules.items() if not r.owner or r.owner.upper() == "LH"}


def _line(name, unit="M2", qty=500.0, spec="H=180MM"):
    return BoqLine("건축", "내(건)", 5, name, spec, unit, qty, "", "사급", "아파트 > 상부공사 > 목공사")


def _mat(line, rules):
    r = match_rule(line, rules)
    return r.material if r else None


def test_shape(all_rules):
    r = all_rules["lh_ceiling_frame"]
    assert r.owner == "LH" and not r.index_keys and not r.extra_keys and r.ks_mark
    assert "Ⅱ.18" in r.group_basis and r.group_frequency == "제조회사별"
    assert [t.test_type for t in r.tests] == ["아연의 부착량", "부재의 모양안정성", "재하하중에 대한 휨량"]
    assert all(t.method == "KS D 3609" for t in r.tests)


@pytest.mark.parametrize("name,want", [
    ("경량철골천정틀설치", "lh_ceiling_frame"),
    ("최상층경량철골천정틀설치", "lh_ceiling_frame"),
    ("경량철골천장틀", "lh_ceiling_frame"),
    ("경량철골천정틀 위 석고보드", "gypsum_board"),
    ("칼라알미늄천정틀설치", None),
    ("칼라알루미늄 천정판 T=4", None),
])
def test_match(active, name, want):
    ln = _line(name)
    assert _mat(ln, active) == want and ambiguous(ln, active) == []


def test_owner_off(all_rules):
    base = {k: r for k, r in all_rules.items() if not r.owner}
    assert _mat(_line("경량철골천정틀설치"), base) is None


def test_one_ks_row(active):
    lines = [_line("경량철골천정틀설치", spec="거실,H=180MM"), _line("최상층경량철골천정틀설치", qty=200, spec="침실,H=240MM")]
    rows = [r for r in plan_rows(aggregate(lines, active)[0], active) if r.material == "lh_ceiling_frame"]
    assert len(rows) == 1 and rows[0].qty == 700 and rows[0].count_ks == "◎" and rows[0].calc_basis == "KS자재"


@pytest.mark.parametrize("name,key", [
    ("섬유보강재(천연및화학섬유, 투입비포함)", "fiber_reinforcement"),
    ("콘크리트 섬유보강재(투입비포함)-복수적용", "fiber_reinforcement"),
    ("방수모르타르/폴리머모르타르-복수적용-건조모르타르", "wp_polymer_mortar"),
])
def test_catalog_flags(active, name, key):
    ln = _line(name)
    assert match_rule(ln, active) is None
    assert [h["key"] for h in flag_extras([ln])["owner_standard_needed"]] == [key]
