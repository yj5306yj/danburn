"""규격 묶음(spec_group, L4-D2): all·pattern·없음, 단위 섞임, 레미콘·철근 불변. 합성 자료만 쓴다."""
from dataclasses import replace
from pathlib import Path

import pytest

from danburn.calc import aggregate, plan_rows
from danburn.model import BoqLine
from danburn.rules import load_rule, load_rules

RULES = Path(__file__).resolve().parents[1] / "src" / "danburn" / "data" / "rules"

BASE = '''material: synthetic_pipe
label: 합성관
basis_version: "합성"
match: {names: [합성관], units: [m, m2]}
ks_mark: true
ks_count: none
group_tests: true
group: {frequency: "제조회사별, 제품규격별", basis: "합성"}
tests:
  - {test_type: 겉모양, method: "KS", where: 외부, frequency: {per_qty: null, unit: null, text: "제조회사별"}, basis: "실무 관행 — 합성"}
'''


def _rules(tmp_path, extra: str = "", non_ks_freq: bool = False):
    text = BASE + extra
    if non_ks_freq:
        text = text.replace("per_qty: null, unit: null", "per_qty: 100, unit: m")
    (tmp_path / "p.yaml").write_text(text, encoding="utf-8")
    return load_rules(tmp_path)


def _line(row, name, spec, qty, unit="M"):
    return BoqLine("건축", "지급(건)", row, name, spec, unit, qty, "", "지급")


LINES = [_line(1, "합성관 VG1", "D35", 10), _line(2, "합성관 VG1", "D50", 20),
         _line(3, "합성관 VG2", "D75", 30), _line(4, "합성관", "D100", 40)]


def test_no_spec_group_keeps_rows_per_spec(tmp_path):
    rows = plan_rows(aggregate(LINES, _rules(tmp_path))[0], _rules(tmp_path))
    assert len(rows) == 4


def test_all_merges_to_one_row_and_sources(tmp_path):
    rules = _rules(tmp_path, "spec_group: all\n")
    mats, _ = aggregate(LINES, rules)
    assert len(mats) == 1 and mats[0].spec == "규격별" and mats[0].qty == 100
    assert [r for _, r in mats[0].sources] == [1, 2, 3, 4]
    row = plan_rows(mats, rules)[0]
    assert row.item == "합성관(규격별)" and row.count_ks == "◎" and row.calc_basis == "KS자재"


def test_all_with_label(tmp_path):
    rules = _rules(tmp_path, "spec_group: {label: 전체}\n")
    assert aggregate(LINES, rules)[0][0].spec == "전체"


def test_all_splits_by_unit(tmp_path):
    rules = _rules(tmp_path, "spec_group: all\n")
    mats, _ = aggregate(LINES + [_line(5, "합성관", "판", 7, unit="M2")], rules)
    assert sorted((m.unit, m.qty) for m in mats) == [("m", 100), ("m2", 7)]


def test_pattern_groups_by_regex_then_name_then_other(tmp_path):
    rules = _rules(tmp_path, 'spec_group: {pattern: "(VG1|VG2)", label: "{1}", other: 규격별}\n')
    mats, _ = aggregate(LINES, rules)
    assert {m.spec: m.qty for m in mats} == {"VG1": 30, "VG2": 30, "규격별": 40}   # VG 는 품명에서 찾음


def test_pattern_prefers_spec_and_ignores_case(tmp_path):
    rules = _rules(tmp_path, 'spec_group: {pattern: "(VG1|VG2)"}\n')
    mats, _ = aggregate([_line(1, "합성관 VG1", "vg2 D50", 5), _line(2, "합성관", "D50", 1)], rules)
    assert {m.spec: m.qty for m in mats} == {"VG2": 5, "기타": 1}               # 기본 label {1}, other 기타


def test_pattern_optional_groups_render_empty(tmp_path):
    rules = _rules(tmp_path, 'spec_group: {pattern: "/(SD|AW)|(방화문)", label: "{1}{2}"}\n')
    mats, _ = aggregate([_line(1, "합성관 10X21/SD", "", 1), _line(2, "합성관 방화문", "", 1)], rules)
    assert {m.spec for m in mats} == {"SD", "방화문"}


def test_merged_non_ks_row_counts_on_total_qty(tmp_path):
    rules = _rules(tmp_path, "spec_group: all\n", non_ks_freq=True)
    row = plan_rows(aggregate(LINES, rules)[0], rules, non_ks=True)[0]
    assert row.count_external == 1 and "100m/100m" in row.calc_basis              # ⌈100/100⌉ × 제조사 1곳
    row = plan_rows(aggregate(LINES, rules)[0], rules, non_ks=True, makers={"*": 3})[0]
    assert row.count_external == 3


@pytest.mark.parametrize("bad", ["spec_group: 3\n", 'spec_group: {pattern: "(a"}\n',
                                 'spec_group: {pattern: "(a)", label: "{2}"}\n'])
def test_loader_rejects_bad_spec_group(tmp_path, bad):
    (tmp_path / "p.yaml").write_text(BASE + bad, encoding="utf-8")
    with pytest.raises(ValueError):
        load_rule(tmp_path / "p.yaml")


def test_concrete_and_rebar_untouched():
    rules = load_rules(RULES)
    assert rules["ready_mixed_concrete"].spec_group == "" and rules["rebar"].spec_group == ""
    lines = [_line(1, "레미콘", "25-24-150", 300, unit="M3"), _line(2, "레미콘", "25-30-150", 200, unit="M3"),
             BoqLine("건축", "지급(건)", 3, "이형철근", "SD400 D13", "TON", 10, "", "지급"),
             BoqLine("건축", "지급(건)", 4, "이형철근", "SD400 D16", "TON", 12, "", "지급")]
    mats, _ = aggregate(lines, rules)
    by = {(m.material, m.spec) for m in mats}
    assert {("ready_mixed_concrete", "25-24-150"), ("ready_mixed_concrete", "25-30-150"),
            ("rebar", "SD400 D13"), ("rebar", "SD400 D16")} <= by


def test_real_rules_door_window_pvc_grouping():
    rules = load_rules(RULES)
    lines = [_line(1, "10X21/FSD", "", 4, unit="EA"), _line(2, "9X21/FSD", "", 6, unit="EA"),
             _line(3, "9X21/SD", "", 2, unit="EA"), _line(4, "12X10/AW", "", 3, unit="EA"),
             _line(5, "15X12/AW", "", 5, unit="EA"),
             _line(6, "경질폴리염화비닐관 VG1", "D=35", 10), _line(7, "경질폴리염화비닐관 VG1", "D=50", 10),
             _line(8, "경질폴리염화비닐관", "D=75", 10)]
    mats, _ = aggregate(lines, rules)
    got = {(m.material, m.spec): m.qty for m in mats}
    assert got[("door_set", "FSD")] == 10 and got[("door_set", "SD")] == 2
    assert got[("window_set", "AW")] == 8
    assert got[("general_pvc_pipe", "VG1")] == 20 and got[("general_pvc_pipe", "규격별")] == 10


def test_without_spec_group_real_rule_would_split():
    """같은 입력을 spec_group 을 끈 규칙으로 돌리면 규격별로 되돌아간다(전후 비교 기준)."""
    rules = load_rules(RULES)
    off = {k: replace(r, spec_group="") for k, r in rules.items()}
    lines = [_line(i, "경질폴리염화비닐관", f"D={d}", 1) for i, d in enumerate((35, 40, 50, 65, 75, 100), 1)]
    assert len(aggregate(lines, off)[0]) == 6 and len(aggregate(lines, rules)[0]) == 1
