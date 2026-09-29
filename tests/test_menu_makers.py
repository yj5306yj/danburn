"""L14-H: 인자 없는 danburn 메뉴의 세 번째 길(test-plan), project.yaml 제조사수 → 계산 makers 연결 — 합성 자료만."""
import argparse
import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from danburn import cli

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "src" / "danburn" / "data" / "templates" / "project.example.yaml"


# ── 메뉴 ──────────────────────────────────────────────────────────────

def _menu(monkeypatch, capsys, answers):
    it = iter(answers)
    calls = []
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))
    monkeypatch.setattr(cli, "main", lambda argv=None: calls.append(argv) or 0)
    rc = cli._no_args(argparse.ArgumentParser(prog="danburn"))
    return rc, capsys.readouterr().out, calls


def test_menu_lists_three_ways(monkeypatch, capsys):
    rc, out, calls = _menu(monkeypatch, capsys, ["q"])
    assert rc == 0 and calls == []
    assert "1) 새로 만들기" in out and "2) 기존 계획서 검사" in out          # 기존 두 줄 유지
    assert "3) 시험계획서만 따로" in out and "danburn test-plan --project" in out


def test_menu_three_runs_test_plan_with_folder_or_file(monkeypatch, capsys, tmp_path):
    (tmp_path / "project.yaml").write_text("공사명: 합성\n", encoding="utf-8")
    _, _, calls = _menu(monkeypatch, capsys, ["3", str(tmp_path)])            # 폴더를 주면 그 안의 project.yaml
    assert calls == [["test-plan", "--project", str(tmp_path / "project.yaml")]]
    _, _, calls = _menu(monkeypatch, capsys, ["3", f"'{tmp_path / 'project.yaml'}'"])   # 끌어다 놓기 따옴표
    assert calls == [["test-plan", "--project", str(tmp_path / "project.yaml")]]


# ── 제조사수 ───────────────────────────────────────────────────────────

def _ns(tmp_path, project: dict | None, makers=""):
    ns = argparse.Namespace(makers=makers, project=None)
    if project is not None:
        p = tmp_path / "project.yaml"
        p.write_text(yaml.safe_dump(project, allow_unicode=True), encoding="utf-8")
        ns.project = str(p)
    return ns


def test_project_makers_merge_under_cli(tmp_path):
    ns = _ns(tmp_path, {"제조사수": {"철근": 8, "철근:SD400 D13": 2}}, makers="철근:SD400 D13=3,*=1")
    assert cli._makers(ns) == {"철근": 8, "철근:SD400 D13": 3, "*": 1}     # --makers 가 같은 키를 덮는다
    assert cli._makers(_ns(tmp_path, None, makers="SD400 D13=2")) == {"SD400 D13": 2}
    assert cli._makers(_ns(tmp_path, {"공사명": "합성"})) == {}


@pytest.mark.parametrize("bad", [{"철근": 0}, {"철근": "여럿"}, {"철근": 2.5}, ["철근", 8]])
def test_project_makers_bad_values(tmp_path, bad):
    with pytest.raises(ValueError, match="제조사수"):
        cli._makers(_ns(tmp_path, {"제조사수": bad}))


@pytest.fixture(scope="module")
def boq(tmp_path_factory):
    p = tmp_path_factory.mktemp("boq") / "example_boq.xlsx"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_example_boq.py"), "--out", str(p)], check=True,
                   capture_output=True)
    return p


def _plan(boq, tmp_path, name, **extra):
    proj = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    proj.update(extra)
    p = tmp_path / f"{name}.yaml"
    p.write_text(yaml.safe_dump(proj, allow_unicode=True), encoding="utf-8")
    out = tmp_path / name / "품질관리계획서.hwpx"
    s = io.StringIO()
    with contextlib.redirect_stdout(s):
        rc = cli.main(["plan", "--boq", str(boq), "--block", "나동", "--project", str(p), "--revision", "0",
                       "--date", "2026. 01. 05.", "--out", str(out), "--offline"])
    assert rc == 0
    return json.loads(s.getvalue()), json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))


def test_project_makers_reach_calculation(boq, tmp_path):
    """project.yaml 제조사수 {철근: 3} → 철근 행 횟수가 1곳 계산의 3배, 요약 makers_used 에 그대로."""
    base_sum, base = _plan(boq, tmp_path, "base")
    three_sum, three = _plan(boq, tmp_path, "three", 제조사수={"철근": 3})

    def rebar(rows):
        return [(r["spec"], r["count_site"] + r["count_external"]) for r in rows if r["material"] == "rebar"]
    assert rebar(base) and [n * 3 for _, n in rebar(base)] == [n for _, n in rebar(three)]
    assert three_sum["makers_used"] == {"철근": 3} and base_sum["makers_used"] == {}
    assert any(w.startswith("제조사(골재원) 수를 1곳으로 계산한 자재") for w in base_sum["warnings"])   # 요약 한 줄


def test_bad_project_makers_is_exit_2(boq, tmp_path, capsys):
    proj = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    proj["제조사수"] = {"철근": "여럿"}
    p = tmp_path / "p.yaml"
    p.write_text(yaml.safe_dump(proj, allow_unicode=True), encoding="utf-8")
    rc = cli.main(["plan", "--boq", str(boq), "--project", str(p), "--revision", "0", "--date", "2026. 01. 05.",
                   "--out", str(tmp_path / "o.hwpx"), "--offline"])
    assert rc == 2 and "제조사수" in capsys.readouterr().err
    assert not (tmp_path / "o.hwpx").exists()


def test_makers_note_in_needs_confirmation_and_unknown_key_warned(boq, tmp_path):
    s, _ = _plan(boq, tmp_path, "unk", 제조사수={"골재없는이름": 5})     # 맞는 자재 없음 → 철근은 여전히 1곳
    notes = [x["note"] for x in s["needs_confirmation"]]
    assert any(n.startswith("제조사(골재원) 수를 1곳으로 계산한 자재") for n in notes)          # L14-D4 연결 1
    assert any("제조사수 '골재없는이름'" in w for w in s["warnings"])
    s, _ = _plan(boq, tmp_path, "ok", 제조사수={"철근": 2})
    assert not any("제조사수 '" in w for w in s["warnings"])
    assert not any(x["note"].startswith("제조사(골재원)") for x in s["needs_confirmation"])   # 합성 예제의 1곳 자재는 철근뿐
