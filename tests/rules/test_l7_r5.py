"""L7-R5 별표2 규칙 7종(보통합판·천연무늬목 치장마루판·섬유판·PVC계 바닥재·래커도료·바니시·다채무늬도료):
로드, 색인 연결, 합성 내역서 행 매칭, 8.11 행(KS ◎) 산출, 시공·노무·오탐 행 제외."""
from pathlib import Path

import pytest

from danburn.calc import aggregate, ambiguous, match_rule, plan_rows
from danburn.index import load_index
from danburn.model import BoqLine
from danburn.rules import load_rule, load_rules

RULES = Path(__file__).resolve().parents[2] / "src" / "danburn" / "data" / "rules"

R5 = ("ordinary_plywood", "veneer_floor", "fiberboard", "pvc_floor", "lacquer", "varnish", "multicolor_paint")
PAGES = {"ordinary_plywood": (39, 40), "veneer_floor": (40,), "fiberboard": (40, 41), "pvc_floor": (43, 44),
         "lacquer": (48,), "varnish": (49,), "multicolor_paint": (49,)}


# L14-C5: LHCS 10 40 00 V2026.04 부록4 비고 '현장시험' 종목은 where 현장(병합 칸으로 범위 확인)
LHCS_ONSITE = {("concrete_brick", "겉모양"), ("concrete_brick", "치수"), ("concrete_brick", "기건 비중"), ("concrete_brick", "압축 강도"),
               ("concrete_brick", "흡수율"), ("hollow_concrete_block", "겉모양 및 치수"), ("hollow_concrete_block", "흡수율"),
               ("clay_brick", "겉모양"), ("clay_brick", "치수"), ("clay_brick", "흡수율"), ("clay_brick", "압축강도"),
               ("curb_block", "겉모양, 모양 및 치수"), ("fiberboard", "함수율"), ("ordinary_plywood", "함수율"),
               ("mineral_wool", "겉모양, 치수, 밀도"), ("door_set", "치수"), ("window_set", "치수"),
               ("synthetic_window_profile", "겉모양, 치수 및 질량")}


@pytest.fixture(scope="module")
def rules():
    return load_rules(RULES)


def _line(name, unit, qty=100.0, spec="합성규격", supply="사급"):
    return BoqLine("건축", "합성", 1, name, spec, unit, qty, "", supply)


def _rows(lines, rules, **kw):
    mats, unread = aggregate(lines, rules)
    assert not unread
    return plan_rows(mats, rules, **kw)


@pytest.mark.parametrize("key", R5)
def test_rule_file_links_index_and_basis(key):
    rule = load_rule(RULES / f"{key}.yaml")
    assert rule.material == key and rule.index_keys == (key,)
    entry = {e.key: e for e in load_index()}[key]
    assert entry.ks and rule.ks_mark and rule.ks_count == "none"      # 종별 괄호 KS → ◎(※주석 p.52)
    assert rule.work
    assert "2026-360" in rule.basis_version
    for t in rule.tests:
        assert any(f"(PDF p.{p})" in t.basis for p in PAGES[key]), t.basis
        assert t.where == ("현장" if (key, t.test_type) in LHCS_ONSITE else "외부"), (key, t.test_type)


def test_test_counts_follow_byeolpyo2():
    n = {k: (len(r.tests), sum(not t.optional for t in r.tests))
         for k in R5 for r in [load_rule(RULES / f"{k}.yaml")]}
    assert n == {"ordinary_plywood": (10, 10), "veneer_floor": (18, 17), "fiberboard": (23, 4), "pvc_floor": (13, 6),
                 "lacquer": (15, 3), "varnish": (12, 11), "multicolor_paint": (10, 10)}


def test_needed_only_tests_are_optional():
    for k in R5:
        for t in load_rule(RULES / f"{k}.yaml").tests:
            if t.frequency.text == "필요시":
                assert t.optional, (k, t.test_type)


# (자재, 합성 품명, 내역서 단위, 시공 행 추정)
SAMPLES = [
    ("ordinary_plywood", "보통합판 12T", "M2", False),
    ("veneer_floor", "강화합판마루재", "M2", False),
    ("veneer_floor", "천연무늬목 치장마루판", "M2", False),
    ("fiberboard", "MDF 9T", "M2", False),
    ("fiberboard", "하드보드", "매", False),
    ("pvc_floor", "비닐장판깔기", "M2", True),
    ("pvc_floor", "PVC 바닥재", "M2", False),
    ("lacquer", "래커도료", "L", False),
    ("varnish", "우레탄 바니시", "L", False),
    ("multicolor_paint", "다채무늬도료", "M2", False),
]


@pytest.mark.parametrize("key,name,unit,install", SAMPLES)
def test_samples_make_one_ks_row(rules, key, name, unit, install):
    line = _line(name, unit)
    assert match_rule(line, rules).material == key
    assert not ambiguous(line, rules)
    rows = [r for r in _rows([line], rules) if r.material == key]
    assert len(rows) == 1
    r = rows[0]
    assert r.count_ks == "◎" and r.calc_basis == "KS자재" and r.work
    assert ("시공 행 추정" in r.note) == install


def test_spec_group_merges_specs(rules):
    rows = _rows([_line("다채무늬도료", "M2", spec="벽"), _line("다채무늬도료", "M2", spec="천장")], rules)
    assert len(rows) == 1 and rows[0].qty == 200


# 걸리면 안 되는 품명(다른 규칙으로 가거나 아무 규칙에도 안 걸림)
NOT_OURS = [
    ("합판거푸집", "M2", "form_plywood"),
    ("제치장코팅합판 거푸집", "M2", "form_plywood"),
    ("작업용 합판깔기", "M2", None),                 # 가설 작업대 시공 행
    ("합판마루 깔기(마루재별도)", "M2", None),        # 자재 별도 시공 행 — 지급 자재와 중복 방지
    ("마루귀틀 설치", "M", None),
    ("장판접착제", "KG", "vinyl_floor_adhesive"),
    ("탈의실 락카", "식", None),                      # 사물함
    ("피트니스센터 세면대", "식", None),              # '니스' 오탐
    ("비닐시트 방수", "M2", "polymer_waterproof_sheet"),
    ("다채무늬도료 노무비", "M2", None),
]


@pytest.mark.parametrize("name,unit,want", NOT_OURS)
def test_not_our_rows(rules, name, unit, want):
    m = match_rule(_line(name, unit), rules)
    assert (m.material if m else None) == want


def test_install_row_dropped_when_material_row_exists(rules):
    rows = _rows([_line("비닐바닥재", "M2", 300.0, spec="T2"), _line("비닐바닥재 깔기", "M2", 300.0, spec="T2")], rules)
    assert len(rows) == 1 and rows[0].qty == 300 and "시공 행 추정" not in rows[0].note
