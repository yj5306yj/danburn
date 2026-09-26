import os
from datetime import date
from pathlib import Path

import pytest

from danburn.basis import MIRROR_URL, OFFICIAL_URL, check_basis
from danburn.model import Rule
from danburn.rules import load_rules

RULES_DIR = Path(__file__).resolve().parents[1] / "src" / "danburn" / "data" / "rules"
TODAY = date(2026, 9, 26)


def _front(number="2026-360", effective="2026-07-08", in_force="Y"):
    return (
        "---\n"
        "행정규칙명: '건설공사 품질관리 업무지침'\n"
        f"발령번호: '{number}'\n"
        f"시행일자: {effective}\n"
        f"현행여부: '{in_force}'\n"
        "---\n\n본문\n"
    )


def _rule(basis_version):
    return Rule(material="x", label="x", tests=(), basis_version=basis_version)


@pytest.fixture(scope="module")
def rules():
    return load_rules(RULES_DIR)


def test_current(rules):
    seen = []
    res = check_basis(rules, fetch=lambda url: seen.append(url) or _front(), today=TODAY)
    assert seen == [MIRROR_URL]
    assert res["status"] == "current"
    assert res["current"]["number"] == "2026-360"
    assert res["current"]["effective_date"] == "2026-07-08"
    assert OFFICIAL_URL in res["current"]["source"]
    assert res["checked_at"] == "2026-09-26"
    # basis_version 뒤쪽의 비교용 옛 번호(제2025-311호)는 쓰지 않는다
    assert {o["number"] for o in res["ours"]} == {"2026-360"}


def test_outdated(rules):
    res = check_basis(rules, fetch=lambda url: _front("2027-15", "2027-02-01"), today=TODAY)
    assert res["status"] == "outdated"
    assert res["current"]["number"] == "2027-15"
    msg = res["message"]
    for words in ("개정됨", "2027-15", "2027-02-01", "부칙", "60일", "레미콘", "철근", "data/rules"):
        assert words in msg


def test_number_compare_is_numeric():
    res = check_basis({"a": _rule("국토교통부고시 제2026-99호")}, fetch=lambda url: _front("2026-360"), today=TODAY)
    assert res["status"] == "outdated"


def test_ours_newer_than_mirror_is_unknown():
    res = check_basis({"a": _rule("국토교통부고시 제2027-1호")}, fetch=lambda url: _front("2026-360"), today=TODAY)
    assert res["status"] == "unknown"
    assert "공식 페이지" in res["message"]


def test_offline_is_unknown(rules):
    def boom(url):
        raise TimeoutError("timed out")
    res = check_basis(rules, fetch=boom, today=TODAY)
    assert res["status"] == "unknown"
    assert "TimeoutError" in res["message"]
    assert res["current"]["number"] is None


@pytest.mark.parametrize("text", [
    "",
    "발령번호: '2026-360'\n",               # 머리말 없음
    "---\n발령번호: '2026-360'\n",          # 끝 없음
    "---\n- a\n---\n",                     # 키-값 아님
    _front(number="제2026-360호?"),          # 번호 형식 이상
    _front(number=""),
])
def test_bad_format_is_unknown(rules, text):
    res = check_basis(rules, fetch=lambda url: text, today=TODAY)
    assert res["status"] == "unknown"
    assert res["message"]


def test_not_in_force_is_unknown(rules):
    res = check_basis(rules, fetch=lambda url: _front(in_force="N"), today=TODAY)
    assert res["status"] == "unknown"


def test_rule_without_number_is_unknown():
    res = check_basis({"a": _rule("별표2")}, fetch=lambda url: _front(), today=TODAY)
    assert res["status"] == "unknown"
    assert "a" in res["message"]


@pytest.mark.network
@pytest.mark.skipif(os.environ.get("DANBURN_NETWORK") != "1", reason="실제 네트워크 호출은 DANBURN_NETWORK=1 일 때만")
def test_live_mirror(rules):
    res = check_basis(rules)
    assert res["status"] in ("current", "outdated"), res["message"]
    assert res["current"]["number"]
