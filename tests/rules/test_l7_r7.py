"""L7-R7 PVC 이중벽관·고강도 PE 파형관: 별표2 이중벽 고밀도 폴리에틸렌관(KS M 3500)으로 식별·계산하지 않고
별표2 밖 목록으로 “발주처 기준 필요” 경고. PE 이중벽관은 그대로 규칙에 걸린다."""
import pytest

from danburn.calc import match_rule
from danburn.extra import flag_extras
from danburn.index import identify
from danburn.model import BoqLine
from danburn.rules import load_rules


@pytest.fixture(scope="module")
def rules():
    from pathlib import Path
    return {k: r for k, r in load_rules(Path(__file__).resolve().parents[2] / "data" / "rules").items()
            if not r.owner or r.owner.upper() == "LH"}


def _line(name, unit="M", spec="D200"):
    return BoqLine("토목", "내(토)", 4, name, spec, unit, 100.0, "", "사급", "오수공사")


@pytest.mark.parametrize("name", ["PVC 이중벽관 부설 및 접합", "PVC이중벽관", "폴리염화비닐 이중벽관"])
def test_pvc_double_wall_not_hdpe(rules, name):
    assert "double_wall_hdpe_pipe" not in [e.key for e in identify(name)]
    assert match_rule(_line(name), rules).material == "lh_sewer_pvc_pipe"     # --owner LH: 하수용 PVC관 규칙(L7-R8)
    base = {k: r for k, r in rules.items() if not r.owner}
    assert match_rule(_line(name), base) is None                                   # 별표2만: 규칙 없음 → 목록 경고
    assert [h["key"] for h in flag_extras([_line(name)])["owner_standard_needed"]] == ["pvc_double_wall_pipe"]


@pytest.mark.parametrize("name,unit", [("고강도폴리에틸렌파이프(파상형)", "M"), ("고강도PE관 티", "개"), ("고강도PE관 Y", "개")])
def test_hs_pe_corrugated_flagged(rules, name, unit):
    ln = _line(name, unit, "D150 MM")
    assert match_rule(ln, rules) is None
    assert [h["key"] for h in flag_extras([ln])["owner_standard_needed"]] == ["hs_pe_corrugated_pipe"]


def test_pe_double_wall_still_rule(rules):
    ln = _line("폴리에틸렌(PE)이중벽관", "M", "D150mm,일반관")
    assert identify(ln.name)[0].key == "double_wall_hdpe_pipe"
    assert match_rule(ln, rules).material == "double_wall_hdpe_pipe"
