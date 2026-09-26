"""8.11 공종 칸 채우기(L6-E1) — 합성 내역 행으로 확인한다."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from danburn.calc import aggregate, added_spec_rows, plan_rows, work_from_section, work_missing, work_title
from danburn.model import BoqLine
from danburn.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def rules():
    return load_rules(ROOT / "src" / "danburn" / "data" / "rules")


def _line(name, spec, unit, qty, section="", row=1, supply="사급"):
    return BoqLine(discipline="건축", sheet="내역(건)", row=row, name=name, spec=spec, unit=unit, qty=qty,
                   block="", supply=supply, section=section)


def _rows(lines, rules):
    mats, _ = aggregate(lines, rules)
    return plan_rows(mats, rules)


@pytest.mark.parametrize("text, want", [
    ("1-1 0101. 철근콘크리트공사", "철근콘크리트공사"),
    ("0105. 방 수 공 사", "방수공사"),
    ("가. 조적공사", "조적공사"),
    ("=== 토공 ===", "토공"),
    ("0106. 창호 및  유리공사", "창호 및 유리공사"),
    ("이하 제거식앵커 공사", "제거식앵커공사"),   # 앞 설명어(L6-E2)
    ("상기 방수공사", "방수공사"),
    ("기타 부대공사", "부대공사"),
    ("기타공사", "기타공사"),                      # 붙은 것은 공종 이름 그대로
    ("0107. 방수 공사", "방수공사"),
    ("가상동 아파트 신축공사", ""),       # 사업명
    ("101동", ""),                         # 동
    ("A-1BL", ""),                         # 블록
    ("건축공사", ""),                      # 분야
    ("상부공사", ""),                      # 부위(부재 추정용 구분)
    ("기초", ""),                          # 공사 제목 아님
])
def test_work_title(text, want):
    assert work_title(text) == want


def test_work_from_section_takes_deepest_work():
    assert work_from_section("가상동 아파트 신축공사 > 건축공사 > 1-2 0102. 미장공사 > 101동") == "미장공사"
    assert work_from_section("건축공사 > 101동") == ""
    assert work_from_section("") == ""


def test_section_fills_work(rules):
    rows = _rows([_line("액체방수제", "", "kg", 100, "건축공사 > 0103. 방수공사")], rules)
    assert rows and {r.work for r in rows} == {"방수공사"}


def test_mixed_sections_use_quantity_weighted_majority(rules):
    lines = [
        _line("레미콘", "25-24-150", "㎥", 300, "건축공사 > 0101. 철근콘크리트공사", row=1),
        _line("레미콘", "25-24-150", "㎥", 100, "건축공사 > 0104. 조적공사", row=2),
        _line("레미콘", "25-24-150", "㎥", 150, "건축공사 > 0104. 조적공사", row=3),
    ]
    rows = _rows(lines, rules)
    assert {r.work for r in rows} == {"철근콘크리트공사"}          # 300 > 250
    rows = _rows(lines + [_line("레미콘", "25-24-150", "㎥", 60, "건축공사 > 0104. 조적공사", row=4)], rules)
    assert {r.work for r in rows} == {"조적공사"}                   # 310 > 300


def test_rule_work_when_section_has_none(rules):
    assert rules["liquid_waterproofing"].work == "방수공사"
    rows = _rows([_line("액체방수제", "", "kg", 100, "건축공사 > 101동")], rules)
    assert {r.work for r in rows} == {"방수공사"}


def test_group_row_gets_work(rules):
    rows = _rows([_line("철근", "SD400 D13", "ton", 20, "")], rules)
    assert rows and {r.work for r in rows} == {"철근콘크리트공사"}


def test_empty_when_neither(rules):
    rules = {k: replace(r, work="") for k, r in rules.items()}
    rows = _rows([_line("액체방수제", "", "kg", 100, "건축공사")], rules)
    assert rows and {r.work for r in rows} == {""}
    assert work_missing(rows) == len(rows)


def test_added_spec_rows_use_rule_work(rules):
    rows = added_spec_rows(["건축:rebar:SD400 D10"], rules)
    assert rows[0].work == "철근콘크리트공사"


def test_work_missing_counts_blank_rows(rules):
    rows = _rows([_line("액체방수제", "", "kg", 100, "")], rules)
    assert work_missing(rows) == 0
    rows[0].work = ""
    assert work_missing(rows) == 1


def test_loader_reads_optional_work(tmp_path):
    src = (ROOT / "src" / "danburn" / "data" / "rules" / "liquid_waterproofing.yaml").read_text(encoding="utf-8")
    (tmp_path / "a.yaml").write_text(src.replace("work: 방수공사\n", ""), encoding="utf-8")
    assert load_rules(tmp_path)["liquid_waterproofing"].work == ""


def _mat(material, work="", spec="x", discipline="건축", unit="ea"):
    from danburn.model import MaterialQty
    return MaterialQty(material=material, spec=spec, unit=unit, qty=10.0, block="", discipline=discipline, work=work)


def test_sort_by_work_groups_within_discipline(rules):
    from danburn.calc import sort_by_work
    rules = {k: replace(r, order=o) for k, r, o in [
        ("a", rules["concrete_brick"], 10), ("b", rules["dry_cement_mortar"], 20),
        ("c", rules["ceramic_tile"], 30), ("d", rules["liquid_waterproofing"], 40)]}
    rules = {k: replace(r, material=k) for k, r in rules.items()}
    mats = [_mat("a", "철근콘크리트공사"), _mat("b", "미장공사"), _mat("c", "철근콘크리트공사"),
            _mat("d", ""), _mat("a", "미장공사", spec="y"), _mat("b", "", discipline="토목"),
            _mat("a", "토공사", discipline="토목")]
    rules["d"] = replace(rules["d"], work="")
    rules["b"] = replace(rules["b"], work="")
    got = [(m.discipline, m.material, m.work or rules[m.material].work) for m in sort_by_work(mats, rules)]
    assert got == [
        ("건축", "a", "철근콘크리트공사"), ("건축", "c", "철근콘크리트공사"),   # 철근콘크리트(최소 order 10, 먼저 나옴)
        ("건축", "b", "미장공사"), ("건축", "a", "미장공사"),               # 미장(최소 order 10, 나중) — 공종 안은 들어온 순서
        ("건축", "d", ""),                                                  # 공종 빈 자재는 분야 끝
        ("토목", "a", "토공사"), ("토목", "b", ""),
    ]


def test_plan_rows_follow_work_groups(rules):
    lines = [
        _line("액체방수제", "", "kg", 100, "건축공사 > 0103. 방수공사", row=1),
        _line("레미콘", "25-24-150", "㎥", 300, "건축공사 > 0101. 철근콘크리트공사", row=2),
        _line("레미콘", "25-21-150", "㎥", 50, "건축공사 > 0103. 방수공사", row=3),
    ]
    works = [r.work for r in _rows(lines, rules)]
    # 방수공사 안에 레미콘(order 작음)이 있어 방수공사가 먼저 올 수도 있다 — 핵심은 같은 공종 행이 이어지는 것
    blocks = [w for i, w in enumerate(works) if i == 0 or works[i - 1] != w]
    assert len(blocks) == len(set(blocks)), works
