"""L4-G6 자재 규칙(각형강관·파이프서포트·비계용 강관·굽도리 페인트·비닐 바닥재 접착제·목재 접착제):
로드, 색인 연결, 합성 내역서 행 매칭, 8.11 행 산출, 노무·손료 행 제외."""
from pathlib import Path

import pytest

from danburn.calc import aggregate, match_rule, match_rule_kind, plan_rows
from danburn.index import coverage, load_index
from danburn.model import BoqLine
from danburn.rules import load_rule, load_rules

RULES = Path(__file__).resolve().parents[2] / "data" / "rules"

G6 = ("square_steel_pipe", "temp_pipe_support", "temp_scaffold_pipe", "baseboard_paint",
      "vinyl_floor_adhesive", "wood_glue")
KS_EXEMPT = {"square_steel_pipe", "vinyl_floor_adhesive", "wood_glue"}
PAGES = {"square_steel_pipe": (12,), "temp_pipe_support": (15,), "temp_scaffold_pipe": (15,),
         "baseboard_paint": (49,), "vinyl_floor_adhesive": (51, 52), "wood_glue": (52,)}


@pytest.fixture(scope="module")
def rules():
    return {k: r for k, r in load_rules(RULES).items() if not r.owner}     # cli 기본(발주처 규칙 끔)


def _line(name, unit, qty=100.0, spec="합성규격", disc="건축"):
    return BoqLine(disc, "합성", 1, name, spec, unit, qty, "", "사급")


def _rows(lines, rules, **kw):
    mats, unread = aggregate(lines, rules)
    assert not unread
    return plan_rows(mats, rules, **kw)


@pytest.mark.parametrize("key", G6)
def test_rule_file_links_index(key):
    rule = load_rule(RULES / f"{key}.yaml")
    assert rule.material == key and rule.index_keys == (key,)
    entry = {e.key: e for e in load_index()}[key]
    assert rule.ks_mark == bool(entry.ks)                    # 종별 괄호 KS 가 있을 때만 ◎(※주석 p.52)
    for t in rule.tests:
        assert any(f"(PDF p.{p})" in t.basis for p in PAGES[key])
    assert "2026-360" in rule.basis_version


def test_test_counts_follow_byeolpyo2():
    n = {k: len(load_rule(RULES / f"{k}.yaml").tests) for k in G6}
    assert n == {"square_steel_pipe": 6, "temp_pipe_support": 1, "temp_scaffold_pipe": 4,
                 "baseboard_paint": 7, "vinyl_floor_adhesive": 5, "wood_glue": 9}


# (자재, 합성 품명, 내역서 단위)
SAMPLES = [
    ("square_steel_pipe", "각형강관 SPSR275", "TON"),
    ("square_steel_pipe", "일반구조용 각형강관", "KG"),
    ("temp_pipe_support", "파이프서포트", "EA"),
    ("temp_scaffold_pipe", "비계용 강관", "M"),
    ("temp_scaffold_pipe", "비계클램프", "EA"),
    ("baseboard_paint", "굽도리 페인트", "M2"),
    ("vinyl_floor_adhesive", "비닐바닥재 접착제", "KG"),
    ("wood_glue", "목공용 접착제", "KG"),
]


@pytest.mark.parametrize("key,name,unit", SAMPLES)
def test_synthetic_line_matches(rules, key, name, unit):
    line = _line(name, unit)
    assert match_rule(line, rules).material == key
    rows = [r for r in _rows([line], rules) if r.material == key]
    assert rows
    if key in KS_EXEMPT:                                      # KS 면제 묶음 행
        assert len(rows) == 1 and rows[0].count_ks == "◎" and rows[0].calc_basis == "KS자재"
        assert rows[0].count_external == 0
    else:                                                     # 비KS: 횟수 있음
        assert all(r.count_ks == "" for r in rows)
        assert all(r.count_site + r.count_external >= 1 for r in rows)
    covered = frozenset(k for r in rules.values() for k in r.index_keys)   # cli 와 같은 방식
    assert not coverage([line], covered_keys=covered)["uncovered"]


@pytest.mark.parametrize("name,unit", [
    ("강관비계 손료", "M2"),            # 손료: 자재 아님
    ("파이프서포트 손료", "EA"),
    ("강관동바리 운반", "TON"),
    ("시스템비계 설치 및 해체", "M2"),   # 조립형 비계는 별도 종별
    ("각관 멍에", "M"),                # 거푸집·동바리 멍에·장선용 각형강관은 별도 종별(가설기자재)
    ("각형강관 가공조립", "TON"),        # 노무
    ("스테인리스 각관", "M"),           # 다른 강재
    ("걸레받이 수성페인트", "M2"),       # 수성도료(KS M 6010)
    ("강마루 바닥재 접착제", "KG"),      # 마루 접착제는 별표2 이 종별 아님
    ("목재 마루 접착제", "KG"),
])
def test_labor_and_other_lines_not_matched(rules, name, unit):
    rule = match_rule(_line(name, unit), rules)
    assert rule is None or rule.material not in G6 or rule.material == "temp_system_scaffold"


def test_install_rows_accepted_only_without_material_rows(rules):
    """비계·동바리 시공 행(설치 및 해체, 공㎥·㎡)만 있으면 그 물량으로 받고 비고 '시공 행 추정'."""
    inst = _line("강관동바리 설치 및 해체", "공㎥", 500)
    rule, is_install = match_rule_kind(inst, rules)
    assert rule.material == "temp_pipe_support" and is_install
    rows = [r for r in _rows([inst], rules) if r.material == "temp_pipe_support"]
    assert len(rows) == 1 and "시공 행 추정" in rows[0].note and rows[0].count_external == 1
    # 자재 행이 함께 있으면 시공 행은 중복이므로 버린다
    mat = _line("파이프서포트", "EA", 300)
    rows = [r for r in _rows([inst, mat], rules) if r.material == "temp_pipe_support"]
    assert len(rows) == 1 and rows[0].qty == 300 and "시공 행 추정" not in rows[0].note

    scaf = _line("강관비계 설치 및 해체", "M2", 1200)
    rows = [r for r in _rows([scaf], rules) if r.material == "temp_scaffold_pipe"]
    assert len(rows) == 1 and "시공 행 추정" in rows[0].note and "조인트 압축하중" in rows[0].test_type
    assert "공급자" in rows[0].calc_basis


def test_square_pipe_groups_by_grade_and_non_ks_counts(rules):
    """각형강관: 치수별 행을 강종별로 묶고, kg 은 톤으로 환산해 합산. 비KS 는 ⌈톤/100⌉×제조사 수."""
    lines = [_line("각형강관", "TON", 60, spec="SPSR275 □-100x100x3.2"),
             _line("각형강관", "KG", 70000, spec="SPSR275 □-50x50x2.3")]
    rows = [r for r in _rows(lines, rules) if r.material == "square_steel_pipe"]
    assert len(rows) == 1 and rows[0].spec == "SPSR275" and rows[0].qty == 130
    assert rows[0].count_ks == "◎"
    rows = [r for r in _rows(lines, rules, non_ks=True) if r.material == "square_steel_pipe"]
    assert rows[0].count_external == 2                        # ⌈130/100⌉ × 1곳
    assert "굽힘성" not in rows[0].test_type                   # 굽힘성은 필요시(optional)


def test_non_ks_paint_counts_makers(rules):
    row = _rows([_line("굽도리페인트", "M2", 800)], rules)[0]
    assert row.material == "baseboard_paint" and row.count_external == 1 and row.count_ks == ""
    assert "주도(KU)" in row.test_type and "도막의 상태" not in row.test_type


def test_lh_finish_carpentry_adhesive_takes_precedence_with_owner():
    """--owner LH 이면 의장목공사용 접착제는 LH 규칙, 아니면 별표2 목재 접착제."""
    everything = load_rules(RULES)
    line = _line("의장목공용 접착제", "KG")
    assert match_rule(line, everything).material == "lh_finish_carpentry_adhesive"
    base = {k: r for k, r in everything.items() if not r.owner}
    assert match_rule(line, base).material == "wood_glue"
