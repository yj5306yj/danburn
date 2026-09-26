"""공개용 예제(L5-P2): 합성 도급내역서 → danburn plan 이 끝까지 돈다."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from danburn.cli import main

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "src" / "danburn" / "data" / "templates" / "project.example.yaml"
VALIDATE = Path(sys.executable).parent / "hwpx-validate"


def _make_example():
    spec = importlib.util.spec_from_file_location("make_example_boq", ROOT / "scripts" / "make_example_boq.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("example")
    boq = _make_example().build(tmp / "example_boq.xlsx")
    return tmp, boq


def test_inspect_sees_two_blocks(example, capsys):
    _, boq = example
    assert main(["inspect", "--boq", str(boq)]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["supported"] and set(info["blocks"]) == {"가동", "나동"}
    assert "원가계산서" in info["sheets"] and "원가계산서" not in info["by_sheet"]   # 그 밖의 시트는 건너뜀


@pytest.fixture(scope="module")
def planned(example):
    tmp, boq = example
    out = tmp / "out" / "plan.hwpx"
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(["plan", "--boq", str(boq), "--block", "나동", "--project", str(PROJECT), "--revision", "0",
                     "--date", "2026. 01. 05.", "--offline", "--out", str(out)])
    return code, out, json.loads(buf.getvalue())


def test_plan_runs_and_has_core_rows(planned):
    code, out, summary = planned
    assert code == 0 and out.exists()
    rows = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    mats = {r["material"] for r in rows}
    for m in ("ready_mixed_concrete", "rebar", "concrete_brick"):
        assert m in mats, m
    assert {r["spec"] for r in rows if r["material"] == "rebar"} >= {"SD500 D13", "SD400 D10"}
    assert any("시공 행 추정" in (r["note"] or "") for r in rows if r["material"] == "pvc_waterstop")
    assert summary["unread_spec_lines"] == 0


def test_plan_warns_uncovered_materials(planned):
    _, _, summary = planned
    keys = {x["key"] for x in summary["owner_standard_needed"]}
    assert {"sealant", "furniture"} <= keys
    assert any(w.startswith("발주처 기준 필요 — 시험계획 미작성") for w in summary["warnings"])


@pytest.mark.skipif(not VALIDATE.exists(), reason="hwpx-validate 없음")
def test_example_plan_validates(planned):
    _, out, _ = planned
    r = subprocess.run([str(VALIDATE), str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
