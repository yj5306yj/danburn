"""L4-LH 발주처(LH) 규칙: LHCS 10 40 00:2020 부록 「품질시험 및 검사기준」의 별표2 밖 자재.
로드, --owner 없으면 꺼짐·있으면 켜짐(cli main + 합성 xlsx), extra_keys 로 “발주처 기준 필요” 경고 제거, 합성 행 매칭."""
import json
import math
from pathlib import Path

import openpyxl
import pytest

from danburn.calc import aggregate, match_rule, plan_rows
from danburn.cli import main
from danburn.extra import load_catalog
from danburn.model import BoqLine
from danburn.rules import load_rules

RULES = Path(__file__).resolve().parents[2] / "src" / "danburn" / "data" / "rules"
BV = "LHCS 10 40 00:2020(2020-12-09) 부록 「품질시험 및 검사기준」"
BV_2026 = "LHCS 10 40 00 V2026.04 부록4 「품질시험 및 검사기준」"   # L14-C2 새 LH 규칙
# 부록에 종별이 일부만 있는 목록 항목 — 경고를 지우지 않는다(extra_keys 로 주장하지 않음)
PARTIAL = {"fire_shutter", "balcony_drain", "pvc_molding", "ventilation", "spray_coating"}
# 부록에 종별이 없는 목록 항목
ABSENT = {"railing", "safety_net", "sanitary_ware", "form_tie", "mailbox",
          "bath_cabinet", "high_strength_pvc_pipe", "refrigerant_fitting", "pressure_reducing_valve",   # 설비(부록 Ⅲ에 없음)
          "fiber_reinforcement", "wp_polymer_mortar", "hs_pe_corrugated_pipe"}   # L7-R6·R7(부록에 없음). pvc_double_wall_pipe 는 lh_sewer_pvc_pipe 가 주장(L7-R8)
# 별표2 문세트(door_set) 동의어 '방화문'에 먼저 걸리는 이름 — door_set.match.exclude 보강 제안(보고서)
SHADOWED = {("lh_refuge_fire_door", "대피공간방화문")}
RAW_UNIT = {"ea": "EA", "m2": "㎡", "m3": "㎥"}


@pytest.fixture(scope="module")
def all_rules():
    return load_rules(RULES)


@pytest.fixture(scope="module")
def lh(all_rules):
    return {k: r for k, r in all_rules.items() if r.owner == "LH"}


@pytest.fixture(scope="module")
def active(all_rules):
    return {k: r for k, r in all_rules.items() if not r.owner or r.owner.upper() == "LH"}   # cli 와 같은 거름


def _line(name, unit="EA", qty=450.0, spec="합성규격"):
    return BoqLine("건축", "지급(건)", 7, name, spec, unit, qty, "", "지급")


def test_lh_rules_shape(lh):
    catalog = {m["key"] for m in load_catalog()["materials"]}
    assert len(lh) >= 30
    claimed = set()
    for key, r in lh.items():
        assert key.startswith("lh_") and r.material == key
        assert r.basis_version in (BV, BV_2026)
        assert r.match_names and r.tests and not r.index_keys        # 별표2 색인 종별을 주장하지 않는다
        assert set(r.extra_keys) <= catalog
        claimed |= set(r.extra_keys)
        if r.group_tests:
            assert r.group_frequency and "LHCS 10 40 00" in r.group_basis
        for t in r.tests:
            assert "LHCS" in t.basis, (key, t.test_type)
            assert t.frequency.text and t.method
    assert not claimed & (PARTIAL | ABSENT)
    assert claimed == catalog - PARTIAL - ABSENT


def test_non_lh_rules_keep_their_matches(all_rules, active):
    """LH 규칙을 켜도 별표2 규칙이 자기 동의어로 여전히 잡힌다."""
    for key, r in all_rules.items():
        if r.owner:
            continue
        for n in r.match_names:
            unit = r.match_units[0] if r.match_units else "EA"
            got = match_rule(_line(n, RAW_UNIT.get(unit, unit)), all_rules)
            if got is r:                                   # LH 없이도 이 규칙이 잡던 이름만 비교
                assert match_rule(_line(n, RAW_UNIT.get(unit, unit)), active) is r, (key, n)


@pytest.mark.parametrize("key", sorted(k for k in load_rules(RULES) if k.startswith("lh_")))
def test_synthetic_line_matches_and_rows(active, key):
    r = active[key]
    unit = RAW_UNIT.get(r.match_units[0], r.match_units[0]) if r.match_units else "EA"
    for n in r.match_names:
        if (key, n) in SHADOWED:
            continue
        assert match_rule(_line(n, unit), active) is r, (key, n)
    mats, unread = aggregate([_line(r.match_names[-1], unit)], active)
    assert not unread and [m.material for m in mats] == [key]
    rows = plan_rows(mats, active, owner="LH")
    assert rows and all(x.item.startswith(r.label) for x in rows)
    if r.group_tests:
        if r.ks_mark:                                      # LH + KS: 종목별 행(L14-D2)
            assert len(rows) == len([t for t in r.tests if not t.optional])
            assert all(x.count_ks == "◎" for x in rows)
        else:
            assert len(rows) == 1 and rows[0].count_external >= 1


def test_per_qty_frequency(active):
    mats, _ = aggregate([_line("스틸그레이팅", "EA", 450)], active)
    row = plan_rows(mats, active, makers={"*": 2})[0]
    assert row.count_external == math.ceil(450 / 200) * 2
    mats, _ = aggregate([_line("점자블록", "㎡", 80)], active)         # 빈도는 개, 내역은 ㎡ → 조용히 계산하지 않음
    row = plan_rows(mats, active)[0]
    assert "단위 확인" in row.note


def test_labor_rows_are_not_materials(active):
    for name in ("실링재 시공", "바닥완충재 설치 인건비", "방충망 설치"):
        assert match_rule(_line(name), active) is None, name


def test_interior_sealant_and_fire_lock_split(active):
    assert match_rule(_line("내부용 실링재"), active).material == "lh_sealant_interior"
    assert match_rule(_line("실리콘 실링재"), active).material == "lh_sealant"
    assert match_rule(_line("방화용 도어락"), active).material == "lh_fire_door_lock"
    assert match_rule(_line("도어락"), active).material == "lh_door_lock"
    assert match_rule(_line("디지털도어록"), active).material == "lh_digital_door_lock"   # V2026.04 부록4 Ⅱ.5 아. 디지털 도어록(L14-C4)
    assert match_rule(_line("HDPE 보호재"), active).material == "lh_hdpe_wp_protection"


def _xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "지급(건)"
    ws.append(["품명", "규격", "단위", "수량"])
    for r in rows:
        ws.append(r)
    wb.save(path)


def _build(tmp_path, capsys, *extra):
    src = tmp_path / "synth.xlsx"
    _xlsx(src, [["레미콘", "25-24-15", "M3", 500], ["실링재", "실리콘계", "M", 1200], ["방충망", "합성규격", "EA", 300],
                ["바닥완충재", "20T", "㎡", 900], ["방화셔터", "합성규격", "EA", 4]])
    out = tmp_path / f"o{len(extra)}.hwpx"
    assert main(["build", "--boq", str(src), "--out", str(out), "--offline", *extra]) == 0
    summary = json.loads(capsys.readouterr().out)
    rows = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    return summary, rows


def test_owner_off_by_default_on_with_flag(tmp_path, capsys):
    summary, rows = _build(tmp_path, capsys)
    mats = {r.get("material") for r in rows}
    assert not any(str(m).startswith("lh_") for m in mats)
    need = {x["key"] for x in summary["owner_standard_needed"]}
    assert {"sealant", "insect_screen", "floor_cushion", "fire_shutter"} <= need
    assert all(BV not in v for v in summary["basis_version"])

    summary, rows = _build(tmp_path, capsys, "--owner", "LH")
    mats = {r.get("material") for r in rows}
    assert {"lh_sealant", "lh_insect_screen", "lh_floor_cushion"} <= mats
    need = {x["key"] for x in summary["owner_standard_needed"]}
    assert not need & {"sealant", "insect_screen", "floor_cushion"}   # extra_keys 로 경고 제거
    assert "fire_shutter" in need                                     # 부록에 없는 방화셔터는 계속 알린다
    assert BV in summary["basis_version"]
