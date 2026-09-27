"""L13-K1: KS 인증 여부 질문 — start 3-1 → project.yaml KS_인증 → plan 계산(KS/비KS)·'KS 인증 확인 전' 경고.

근거: Windows 재검증 §3(입력에 KS 여부가 없는데 철근이 KS자재·◎로 나옴). 모든 입력은 합성 예제다.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest
import yaml

from danburn import start
from danburn.cli import main
from danburn.start import Interview, read_boq_info

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "src" / "danburn" / "data" / "templates" / "project.example.yaml"
KS_WARN = "KS 인증 확인 전"


@pytest.fixture(scope="module")
def boq(tmp_path_factory):
    p = tmp_path_factory.mktemp("boq") / "example_boq.xlsx"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_example_boq.py"), "--out", str(p)],
                   check=True, capture_output=True)
    return p


def _plan(boq, tmp_path, capsys, ks="__drop__", *extra):
    """합성 예제 project.yaml 의 KS_인증 을 바꿔 plan 을 돌린다 → (종료 코드, 요약, 철근 행)."""
    proj = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    if ks == "__drop__":
        proj.pop("KS_인증", None)
    else:
        proj["KS_인증"] = ks
    pp = tmp_path / "project.yaml"
    pp.write_text(yaml.safe_dump(proj, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "계획서.hwpx"
    rc = main(["plan", "--boq", str(boq), "--block", "나동", "--project", str(pp), "--revision", "0",
               "--date", "2026. 01. 05.", "--offline", "--out", str(out), *extra])
    cap = capsys.readouterr()
    if rc != 0:
        return rc, cap.err, []
    rows = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    return rc, json.loads(cap.out), [r for r in rows if r["material"] == "rebar"]


def _ks_warns(summary):
    return [w for w in summary["warnings"] if w.startswith(KS_WARN)]


def test_yes_is_ks_without_warning(boq, tmp_path, capsys):
    rc, s, rebar = _plan(boq, tmp_path, capsys, "예")
    assert rc == 0 and rebar
    assert all(r["count_ks"] == "◎" and r["count_external"] == 1 for r in rebar)      # 제조회사·규격별 1회 + ◎
    assert not _ks_warns(s) and s["ks"] == {"KS_인증": "예", "non_ks": False, "warned": False}


def test_no_is_non_ks_external_per_50_ton(boq, tmp_path, capsys):
    rc, s, rebar = _plan(boq, tmp_path, capsys, "아니오")
    assert rc == 0 and rebar
    for r in rebar:
        assert r["count_ks"] != "◎" and r["count_external"] == max(1, math.ceil(r["qty"] / 50)) > 0
    assert any(r["count_external"] > 1 for r in rebar)                                  # 합성 나동 H-13 150.2톤 → 4회
    assert not _ks_warns(s) and s["ks"]["non_ks"] is True


def test_no_leaves_no_ks_mark_anywhere(boq, tmp_path, capsys):
    """비KS 로 답하면 시험별 행(레미콘 등)에도 KS 표시 ◎ 를 붙이지 않는다 — 답과 계획서가 어긋나지 않게. 그 행들의 횟수는 같다."""
    def rows_for(ks, sub):
        d = tmp_path / sub
        d.mkdir()
        rc, _, _ = _plan(boq, d, capsys, ks)
        assert rc == 0
        return json.loads((d / "계획서.json").read_text(encoding="utf-8"))
    yes, no = rows_for("예", "y"), rows_for("아니오", "n")
    assert any(r["count_ks"] == "◎" and r["material"] != "rebar" for r in yes)       # 예: 철근 밖 자재에도 ◎
    assert not any(r["count_ks"] == "◎" for r in no)                                  # 아니오: 어디에도 ◎ 없음
    # 묶음 시험 자재(예일 때 산출근거 'KS자재…')는 비KS 면 횟수가 바뀌는 게 설계 — 시험별 행 자재만 횟수가 같아야 한다
    grouped = {r["material"] for r in yes if str(r["calc_basis"]).startswith("KS자재")}
    key = lambda r: (r["material"], r["item"], r["test_type"])
    cnt = lambda rs: {key(r): (r["count_site"], r["count_external"]) for r in rs if r["material"] not in grouped}
    assert cnt(yes) and cnt(yes) == cnt(no)                                            # 시험별 행 자재의 횟수는 같다


@pytest.mark.parametrize("ks", ["모름", "__drop__", ""])
def test_unknown_or_missing_computes_ks_and_warns(boq, tmp_path, capsys, ks):
    rc, s, rebar = _plan(boq, tmp_path, capsys, ks)
    assert rc == 0 and all(r["count_ks"] == "◎" for r in rebar)                          # 계산은 지금처럼 KS
    warns = _ks_warns(s)
    assert len(warns) == 1 and s["warnings"][0] == warns[0] and s["ks"]["warned"] is True
    assert "철근" in warns[0] and "KS_인증" in warns[0] and "아니오" in warns[0] and "50톤마다" in warns[0]


def test_cli_non_ks_overrides_project(boq, tmp_path, capsys):
    rc, s, rebar = _plan(boq, tmp_path, capsys, "예", "--non-ks")
    assert rc == 0 and all(r["count_ks"] != "◎" for r in rebar) and s["ks"]["non_ks"] is True
    rc, s, _ = _plan(boq, tmp_path, capsys, "모름", "--non-ks")
    assert rc == 0 and not _ks_warns(s)                                                 # 비KS 로 이미 정함 — 경고 없음


def test_bad_value_stops_before_writing(boq, tmp_path, capsys):
    rc, err, _ = _plan(boq, tmp_path, capsys, "아마도")
    assert rc == 2 and "KS_인증" in err and not (tmp_path / "계획서.hwpx").exists()


def test_yaml_bool_values(boq, tmp_path, capsys):
    assert _plan(boq, tmp_path, capsys, False)[1]["ks"]["non_ks"] is True             # KS_인증: no
    assert _plan(boq, tmp_path, capsys, True)[1]["ks"]["KS_인증"] == "예"


# ── start: 질문·저장·확인할 것 ─────────────────────────────────────────

def _answers(boq, **kw):
    a = {"내역서": str(boq), "블록": "나동", "발주자_구분": "민간", "발주자": "합성개발", "공사종류": "건축",
         "총공사비_억원": 850, "연면적": 42000, "지상층수": 22, "건설사업관리_대상": "아니오",
         "공사명": "합성 예시 공동주택", "시공자": "합성건설", "현장대리인": "합성 갑", "품질관리자": "합성 을"}
    a.update(kw)
    return a


def _start(boq, tmp_path, capsys, monkeypatch, **kw):
    ans = tmp_path / "a.yaml"
    ans.write_text(yaml.safe_dump(_answers(boq, **kw), allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("DANBURN_HOME", str(tmp_path / "h"))
    ns = argparse.Namespace(answers=str(ans), plain=False, yes=False, folder=str(tmp_path), out_dir=str(tmp_path / "o"),
                            no_plan=False, offline=True, input=None)
    rc = start.main(ns)
    out = capsys.readouterr().out
    proj = yaml.safe_load((tmp_path / "o" / "project.yaml").read_text(encoding="utf-8"))
    rows = json.loads((tmp_path / "o" / "품질관리계획서.json").read_text(encoding="utf-8"))
    return rc, out, proj, [r for r in rows if r["material"] == "rebar"]


@pytest.mark.parametrize("given,saved,ks_mark,warned", [
    ("예", "예", True, False), ("아니오", "아니오", False, False), ("모름", "모름", True, True), (None, "모름", True, True)])
def test_start_answers_saved_and_applied(boq, tmp_path, capsys, monkeypatch, given, saved, ks_mark, warned):
    kw = {"KS_인증": given} if given else {}
    rc, out, proj, rebar = _start(boq, tmp_path, capsys, monkeypatch, **kw)
    assert rc == 0, out
    assert proj["KS_인증"] == saved
    assert rebar and all((r["count_ks"] == "◎") is ks_mark for r in rebar)
    todo = out.split("확인할 것", 1)[1]
    assert (KS_WARN in todo) is warned                                                   # start 끝 '확인할 것'


def test_question_skipped_without_ks_materials(boq, tmp_path):
    src = tmp_path / "레미콘만.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "지급(건)"
    for r in (["품명", "규격", "단위", "수량"], ["레미콘", "25-24-150", "M3", 500]):
        ws.append(r)
    wb.save(src)
    assert read_boq_info(str(src))["ks_lines"] == 0 and read_boq_info(str(boq))["ks_lines"] > 0
    q = next(q for q in start.load_questions() if q["key"] == "KS_인증")
    iv = Interview(mode="answers", folder=tmp_path)
    iv.info = read_boq_info(str(src))
    assert not iv.when(q["when"], q)
    iv.info = read_boq_info(str(boq))
    assert iv.when(q["when"], q)
    assert Interview(mode="answers", folder=tmp_path).when(q["when"], q)                 # 내역서를 아직 안 읽었으면 묻는다
