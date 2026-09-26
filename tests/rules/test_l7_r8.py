"""L7-R8 LH 하수용 PVC관(KS M 3600)·PP관 — LHCS 10 40 00:2020 부록 Ⅰ.1 공통 마. 기타.
부설 및 접합 행 받기, 지름 묶음(D-200 = 고무링접합, D200), 6m=1개 환산, 300개 빈도, 지급 우선 중복 제거, 목록 경고 대체."""
from pathlib import Path

import pytest

from danburn.calc import aggregate, ambiguous, match_rule, plan_rows
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[2] / "data" / "rules"


@pytest.fixture(scope="module")
def all_rules():
    return load_rules(RULES)


@pytest.fixture(scope="module")
def active(all_rules):
    return {k: r for k, r in all_rules.items() if not r.owner or r.owner.upper() == "LH"}


def _line(name, spec="고무링접합, D200", unit="M", qty=600.0, sheet="내(토)3", block="블록B", supply="사급"):
    return BoqLine("토목", sheet, 8, name, spec, unit, qty, block, supply, "오수공사 > 오수공사")


def _mat(line, rules):
    r = match_rule(line, rules)
    return r.material if r else None


def test_shape(all_rules):
    pvc, pp = all_rules["lh_sewer_pvc_pipe"], all_rules["lh_sewer_pp_pipe"]
    assert pvc.owner == pp.owner == "LH" and not pvc.index_keys and not pp.index_keys
    assert pvc.extra_keys == ("pvc_double_wall_pipe",)
    assert [t.test_type for t in pvc.tests] == ["원강성", "원연성", "관의 색"] and {t.method for t in pvc.tests} == {"KS M 3600"}
    assert [t.test_type for t in pp.tests] == ["원강성", "원연성"]
    for r in (pvc, pp):
        assert "Ⅰ.1 공통 마. 기타" in r.group_basis and not r.ks_mark
        assert all(t.frequency.per_qty == 300 and t.frequency.unit == "ea" for t in r.tests)


@pytest.mark.parametrize("name,unit,want", [
    ("PVC 이중벽관 부설 및 접합", "M", "lh_sewer_pvc_pipe"),
    ("PVC이중벽관", "M", "lh_sewer_pvc_pipe"),
    ("하수용 PVC관", "본", "lh_sewer_pvc_pipe"),
    ("오수관 보호콘크리트 설치", "M", None),
    ("PP 이중벽관", "M", "lh_sewer_pp_pipe"),
    ("배수용 PPF배관", "M", None),                              # 설비 배수관
    ("폴리에틸렌(PE)이중벽관", "M", "double_wall_hdpe_pipe"),   # 별표2 우선 — LH PE관 규칙은 만들지 않음
])
def test_match(active, name, unit, want):
    ln = _line(name, unit=unit)
    assert _mat(ln, active) == want and ambiguous(ln, active) == []


def test_owner_off(all_rules):
    base = {k: r for k, r in all_rules.items() if not r.owner}
    assert _mat(_line("PVC 이중벽관 부설 및 접합"), base) is None


def test_diameter_group_and_6m_units(active):
    lines = [_line("PVC 이중벽관 부설 및 접합", "고무링접합, D200", qty=1200), _line("PVC 이중벽관 부설 및 접합", "고무링접합, D300", qty=2400)]
    mats, _ = aggregate(lines, active)
    got = {m.spec: (m.qty, m.unit) for m in mats}
    assert got == {"D200": (pytest.approx(200), "ea"), "D300": (pytest.approx(400), "ea")}
    rows = {r.spec: r for r in plan_rows(mats, active)}
    assert rows["D200"].count_external == 1 and rows["D300"].count_external == 2   # ⌈개/300⌉ × 제조사 1곳


def test_supplied_row_wins_over_laying_row(active):
    """같은 블록에 지급 자재 행(D-200)과 사급 부설 행(고무링접합, D200)이 있으면 지급만 센다."""
    sup = _line("PVC이중벽관", "D-200", qty=600, sheet="지급(토)", block="블록A", supply="지급")
    lay = _line("PVC 이중벽관 부설 및 접합", "고무링접합, D200", qty=580, sheet="내(토)2", block="블록A")
    mats, _ = aggregate([sup, lay], active)
    assert len(mats) == 1 and mats[0].spec == "D200" and mats[0].qty == pytest.approx(100)
    assert [s[0] for s in mats[0].sources] == ["지급(토)"]
