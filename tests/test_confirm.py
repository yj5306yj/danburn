"""현장 확인(L7-E7): 규칙 밖 행·설치 행에만 있는 종별을 사용자 답으로 8.11 에 넣거나 뺀다 — 합성 자료."""
from __future__ import annotations

import argparse
import json

import openpyxl
import pytest

from danburn.cli import _confirmations, main

# 품명으로 강섬유가 식별되지만 규칙 제외어(셀룰로)로 안 걸리는 행. 규격에서만 식별되는 행은 test_name_unknown(L7-E8)
FIBER = ["강섬유(셀룰로오스 혼합)", "투입", "M3", 40]


def _xlsx(path, extra_rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "내역(건)"
    for r in [["품명", "규격", "단위", "수량"], ["레미콘", "25-24-15", "M3", 500], *extra_rows]:
        ws.append(r)
    wb.save(path)
    return path


def _run(tmp_path, capsys, extra_rows, *args):
    src = _xlsx(tmp_path / "b.xlsx", extra_rows)
    out = tmp_path / "o.hwpx"
    assert main(["build", "--boq", str(src), "--out", str(out), "--offline", *args]) == 0
    summary = json.loads(capsys.readouterr().out)
    rows = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    return summary, rows


def test_unanswered_is_asked_and_warned(tmp_path, capsys):
    summary, rows = _run(tmp_path, capsys, [FIBER])
    ask = {x["key"]: x for x in summary["ask"]}
    a = ask["steel_fiber"]
    assert a["kind"] == "rule_miss" and a["lines"] == 1 and a["units"] == ["M3"]
    assert a["examples"] == ["강섬유(셀룰로오스 혼합)"] and a["rule"].startswith("steel_fiber(")
    assert any(w.startswith("규칙 밖 행") and "강섬유" in w for w in summary["warnings"])
    assert not [r for r in rows if r["material"] == "steel_fiber"]
    assert summary["confirmed_included"] == [] and summary["confirmed_excluded"] == []


def test_yes_puts_row_into_811(tmp_path, capsys):
    summary, rows = _run(tmp_path, capsys, [FIBER], "--confirm", "steel_fiber=예")
    r = [x for x in rows if x["material"] == "steel_fiber"]
    assert len(r) == 1 and r[0]["count_ks"] == "◎" and "현장 확인으로 포함" in r[0]["note"]
    assert not any(w.startswith("규칙 밖 행") and "강섬유" in w for w in summary["warnings"])
    assert "steel_fiber" not in {x["key"] for x in summary["ask"]}
    assert summary["confirmed_included"] == [{"key": "steel_fiber", "rule": "steel_fiber", "lines": 1}]


def test_no_drops_warning_and_records(tmp_path, capsys):
    summary, rows = _run(tmp_path, capsys, [FIBER], "--confirm", "steel_fiber=아니오")
    assert not [r for r in rows if r["material"] == "steel_fiber"]
    assert not any("강섬유" in w for w in summary["warnings"] if w.startswith("규칙 밖 행"))
    assert [x["key"] for x in summary["confirmed_excluded"]] == ["steel_fiber"]
    assert "steel_fiber" not in {x["key"] for x in summary["ask"]}


def test_unit_not_convertible_gives_row_without_quantity(tmp_path, capsys):
    # 섬유판 규칙 단위(㎡·매·장)가 아닌 '식' → 수량 없이 ◎ 행(지어내지 않음)
    summary, rows = _run(tmp_path, capsys, [["MDF 붙임판", "T9", "식", 1]], "--confirm", "fiberboard=예")
    r = [x for x in rows if x["material"] == "fiberboard"]
    assert len(r) == 1 and r[0]["qty"] == 0 and r[0]["count_ks"] == "◎"
    assert "시공 행 추정(수량 환산 없음)" in r[0]["note"] and "현장 확인으로 포함" in r[0]["note"]


def test_install_only_kind(tmp_path, capsys):
    install = ["섬유강화시멘트판 설치", "6T", "M2", 300]
    summary, rows = _run(tmp_path, capsys, [install])
    ask = {x["key"]: x for x in summary["ask"]}
    assert ask["fiber_cement_board"]["kind"] == "install_only"
    summary, rows = _run(tmp_path, capsys, [install], "--confirm", "fiber_cement_board=예")
    r = [x for x in rows if x["material"] == "fiber_cement_board"]
    assert len(r) == 1 and r[0]["qty"] == 300 and "시공 행 추정" in r[0]["note"] and "현장 확인으로 포함" in r[0]["note"]
    assert not any(w.startswith("설치 행에만 있음") and "섬유강화" in w for w in summary["warnings"])


def test_yes_only_forces_rows_the_user_saw(tmp_path, capsys):
    # 자재 행(규칙 밖 행)이 있으면 같은 종별의 설치 행은 넣지 않는다 — 보인 목록과 같게
    summary, rows = _run(tmp_path, capsys, [FIBER, ["강섬유 투입 인건비", "", "M3", 40]], "--confirm", "steel_fiber=예")
    assert summary["confirmed_included"][0]["lines"] == 1


def test_confirmations_parse_and_cli_wins(tmp_path):
    proj = tmp_path / "p.yaml"
    proj.write_text("현장_확인:\n  steel_fiber: 예\n  fiberboard: 아니오\n  ordinary_plywood: yes\n", encoding="utf-8")
    ns = argparse.Namespace(project=str(proj), confirm="fiberboard=예,board_x=아니요")
    assert _confirmations(ns) == {"steel_fiber": True, "fiberboard": True, "ordinary_plywood": True, "board_x": False}
    with pytest.raises(ValueError, match="예 또는 아니오"):
        _confirmations(argparse.Namespace(project=None, confirm="steel_fiber=글쎄"))


def test_bad_answer_exits_2(tmp_path, capsys):
    src = _xlsx(tmp_path / "b.xlsx", [FIBER])
    assert main(["build", "--boq", str(src), "--out", str(tmp_path / "o.hwpx"), "--offline", "--confirm", "steel_fiber=몰라"]) == 2
    assert "예 또는 아니오" in capsys.readouterr().err
