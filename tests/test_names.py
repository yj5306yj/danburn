"""이름 단번(Danburn) 통일(L7-N1): 출력 파일 이름·옛 환경변수 호환·명령 이름."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DANBURN = Path(sys.executable).parent / "danburn"


@pytest.fixture(scope="module")
def boq(tmp_path_factory):
    p = tmp_path_factory.mktemp("boq") / "boq.xlsx"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_example_boq.py"), "--out", str(p)], check=True,
                   capture_output=True)
    return p


def _answers(boq, **kw):
    a = {"내역서": str(boq), "블록": "나동", "발주자_구분": "민간", "발주자": "합성개발", "공사종류": "건축",
         "총공사비_억원": 850, "연면적": 42000, "지상층수": 22, "건설사업관리_대상": "아니오",
         "공사명": "합성 예시 공동주택", "시공자": "합성건설", "현장대리인": "합성 갑", "품질관리자": "합성 을"}
    a.update(kw)
    return a


def _start(boq, tmp_path, **kw):
    ans = tmp_path / "a.yaml"
    ans.write_text(yaml.safe_dump(_answers(boq, **kw), allow_unicode=True), encoding="utf-8")
    out = tmp_path / "o"
    env = {**os.environ, "DANBURN_HOME": str(tmp_path / "h")}
    r = subprocess.run([str(DANBURN), "start", "--answers", str(ans), "--out-dir", str(out), "--offline", "--yes"],
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return sorted(p.name for p in out.iterdir())


def test_command_name():
    r = subprocess.run([str(DANBURN), "--help"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and r.stdout.startswith("usage: danburn")


def test_quality_management_plan_file_names(boq, tmp_path):
    assert _start(boq, tmp_path) == ["project.yaml", "요약.json", "품질관리계획서.hwpx", "품질관리계획서.json"]


def test_quality_test_plan_file_names(boq, tmp_path):
    names = _start(boq, tmp_path, 총공사비_억원=30, 연면적=3000, 지상층수=5, 계약_품질관리계획="아니오", 주용도="공동주택")
    assert names == ["project.yaml", "요약.json", "품질시험계획서.hwpx", "품질시험계획서.json"]


@pytest.mark.parametrize("var", ["DANBURN_OFFLINE", "QCPLAN_OFFLINE"])     # 옛 이름도 한동안 읽는다
def test_offline_env_names(var, boq, tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("DANBURN_OFFLINE", "QCPLAN_OFFLINE")}
    env[var] = "1"
    r = subprocess.run([str(DANBURN), "build", "--boq", str(boq), "--block", "나동", "--out", str(tmp_path / "o.hwpx")],
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=300)
    assert r.returncode == 0, r.stderr
    summary = __import__("json").loads(r.stdout.strip().splitlines()[-1])
    assert summary["basis_check"]["status"] == "unknown" and "offline" in summary["basis_check"]["message"]
