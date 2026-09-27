"""루프 10 L10-A: Windows 첫 사용자 경로 — 인코딩(W01)·실패 재생성 보존(W03)·경로(W04)·입력 실수(W06).

근거: docs/harness/2026-09-27-Windows-검증-인계.md. 맥에서 한국어 Windows 기본값(로캘 cp949, UTF-8 설정 없음, stdout
파이프)을 흉내 내려고 자식 프로세스의 stdin/stdout/stderr 를 cp949 TextIOWrapper 로 바꾼 뒤 danburn.cli.main() 을
부른다(PYTHONIOENCODING 을 쓰면 '명시 설정 존중' 경로를 타므로 그것은 기존 동작 재현용 대조군으로만 쓴다).
모든 입력은 합성 예제(scripts/make_example_boq.py)다.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from danburn import cli
from danburn.cli import _Utf8OrCp949Lines, main
from danburn.start import clean_path

ROOT = Path(__file__).resolve().parents[1]
DANBURN = Path(sys.executable).parent / "danburn"
PROJECT = ROOT / "src" / "danburn" / "data" / "templates" / "project.example.yaml"

# 한국어 Windows 기본(로캘 cp949)처럼: 표준 입출력을 cp949 로 연 뒤 명령행 진입점을 그대로 부른다
CP949_ENTRY = (
    "import io, sys\n"
    "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='cp949', line_buffering=True)\n"
    "sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='cp949', line_buffering=True)\n"
    "sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='cp949')\n"
    "from danburn.cli import main\n"
    "sys.exit(main())\n"
)


@pytest.fixture(scope="module")
def boq(tmp_path_factory):
    d = tmp_path_factory.mktemp("boq")
    p = d / "합성 내역서.xlsx"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_example_boq.py"), "--out", str(p)],
                   check=True, capture_output=True)
    return p


def _env(home: Path, **extra) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "DANBURN"))}
    env.update(DANBURN_HOME=str(home), **extra)
    return env


def _cp949_run(args: list[str], home: Path, stdin: bytes = b"", cwd: Path | None = None):
    """UTF-8 설정 없는 한국어 Windows + LLM 실행기(파이프) 흉내. 결과 stdout/stderr 는 bytes."""
    return subprocess.run([sys.executable, "-X", "utf8=0", "-c", CP949_ENTRY, *args], input=stdin,
                          capture_output=True, env=_env(home), cwd=cwd, timeout=300)


def _plan_args(boq: Path, out: Path, date: str = "2026. 01. 05.") -> list[str]:
    return ["plan", "--boq", str(boq), "--block", "나동", "--project", str(PROJECT), "--revision", "0",
            "--date", date, "--offline", "--out", str(out)]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ── W01 인코딩 ────────────────────────────────────────────────────────

def test_w01_control_explicit_cp949_reproduces_old_failure(boq, tmp_path):
    """대조군: PYTHONIOENCODING=cp949 를 명시하면(존중) 수정 전과 같은 UnicodeEncodeError 경로 — 재현 장치가 유효함."""
    r = subprocess.run([str(DANBURN), *_plan_args(boq, tmp_path / "c.hwpx")], capture_output=True, timeout=300,
                       env=_env(tmp_path / "h", PYTHONIOENCODING="cp949"))
    assert r.returncode != 0
    assert b"cp949" in r.stderr


def test_w01_plan_pipe_cp949_locale(boq, tmp_path):
    r = _cp949_run(_plan_args(boq, tmp_path / "계획서.hwpx"), tmp_path / "h")
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    summary = json.loads(r.stdout.decode("utf-8"))                 # 파이프 출력은 UTF-8
    assert Path(summary["hwpx"]).is_file() and Path(summary["json"]).is_file()


def test_w01_start_answers_pipe_cp949_locale(boq, tmp_path):
    ans = tmp_path / "답.yaml"
    ans.write_text(yaml.safe_dump({"내역서": str(boq), "블록": "나동", "발주자_구분": "민간", "발주자": "합성개발",
                                   "공사종류": "건축", "총공사비_억원": 850, "연면적": 42000, "지상층수": 22,
                                   "건설사업관리_대상": "아니오", "공사명": "합성 예시 공동주택", "시공자": "합성건설",
                                   "현장대리인": "합성 갑", "품질관리자": "합성 을"}, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "산출"
    r = _cp949_run(["start", "--answers", str(ans), "--out-dir", str(out), "--offline"], tmp_path / "h")
    text = r.stdout.decode("utf-8")
    assert r.returncode == 0, text + r.stderr.decode("utf-8", "replace")
    assert "계획서:" in text
    assert (out / "요약.json").is_file() and (out / "project.yaml").is_file()


def test_w01_start_plain_eof_and_cp949_answers(boq, tmp_path):
    """인계 §6 probe 의 질문 재실행: 빈 stdin → 첫 질문 후 종료 2, cp949 로 보낸 한글 답 → 판정까지, 끝까지 → 0."""
    plain = ["start", "--plain", "--offline", "--folder", str(boq.parent), "--out-dir", str(tmp_path / "replay")]
    r = _cp949_run(plain, tmp_path / "h0")
    out = r.stdout.decode("utf-8")
    assert r.returncode == 2 and out.startswith("Q") and "멈춤:" in out

    answers = [str(boq), "3", "합성 검증 공동주택", "합성발주", "1", "Y", "850", "42000", "22", "", "합성건설", ""]
    r = _cp949_run(plain, tmp_path / "h1", ("\r\n".join(answers) + "\r\n").encode("cp949"))
    out = r.stdout.decode("utf-8")
    assert r.returncode == 2 and "JUDGE" in out, out

    r = _cp949_run(plain, tmp_path / "h2", ("\n".join(answers + ["Y", "Y", "", "", "", ""]) + "\n").encode("cp949"))
    out = r.stdout.decode("utf-8")
    assert r.returncode == 0, out + r.stderr.decode("utf-8", "replace")
    proj = yaml.safe_load((tmp_path / "replay" / "project.yaml").read_text(encoding="utf-8"))
    assert proj["공사명"] == "합성 검증 공동주택"                     # cp949 답이 한글 그대로 들어감
    for name in ("요약.json", "품질관리계획서.hwpx", "품질관리계획서.json"):
        assert (tmp_path / "replay" / name).is_file(), name


def test_w01_stdin_decoder_utf8_then_cp949():
    raw = io.BytesIO("합성건설\r\n".encode("cp949") + "\ufeff합성 을\n".encode("utf-8") + b"Y")
    d = _Utf8OrCp949Lines(raw)
    assert [d.readline(), d.readline(), d.readline(), d.readline()] == ["합성건설\n", "합성 을\n", "Y", ""]


def test_w01_in_process_call_leaves_streams_alone(boq, tmp_path, capsys):
    """start 가 같은 프로세스에서 cli.main(args) 를 부를 때는 표준 입출력을 바꾸지 않는다."""
    before = sys.stdin
    assert main(["inspect", "--boq", str(boq)]) == 0
    assert sys.stdin is before
    assert json.loads(capsys.readouterr().out)["supported"]


# ── W03 실패 재생성 보존 ──────────────────────────────────────────────

@pytest.fixture()
def made(boq, tmp_path, capsys):
    out = tmp_path / "계획서.hwpx"
    assert main(_plan_args(boq, out)) == 0
    capsys.readouterr()
    return out, out.with_suffix(".json")


def test_w03_date_mismatch_keeps_both_files(boq, made, capsys):
    out, js = made
    before = (_sha(out), _sha(js))
    assert main(_plan_args(boq, out, date="2026. 01. 06.") + ["--non-ks"]) == 2    # 예제 이력의 Rev.0 은 01. 05.
    assert "계획서를 만들지 않았습니다" in capsys.readouterr().err
    assert (_sha(out), _sha(js)) == before
    assert sorted(p.name for p in out.parent.iterdir()) == sorted([out.name, js.name])   # 임시 파일도 남지 않음


def test_w03_build_failure_after_json_keeps_both_files(boq, made, capsys, monkeypatch):
    """계산 JSON 을 쓴 뒤 HWPX 조립이 실패해도(로고 파일 없음 등) 기존 두 파일은 그대로."""
    out, js = made
    before = (_sha(out), _sha(js))
    assert main(_plan_args(boq, out) + ["--non-ks", "--logo", str(out.parent / "없는 로고.png")]) == 2
    assert (_sha(out), _sha(js)) == before
    assert sorted(p.name for p in out.parent.iterdir()) == sorted([out.name, js.name])


@pytest.mark.parametrize("locked", ["hwpx", "json"])
def test_w03_locked_output_keeps_both_files(boq, made, capsys, monkeypatch, locked):
    """Windows 에서 한글이 열어 둔 파일은 이름을 바꿀 수 없다 → '닫고 다시 실행', 종료 2, 두 파일 원래 해시."""
    out, js = made
    target = out if locked == "hwpx" else js
    before = (_sha(out), _sha(js))
    real = os.replace

    def replace(src, dst):
        if Path(src) == target:
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return real(src, dst)
    monkeypatch.setattr(cli.os, "replace", replace)
    assert main(_plan_args(boq, out) + ["--non-ks"]) == 2
    err = capsys.readouterr().err
    assert "닫고 다시 실행" in err and "기존 파일은 그대로" in err
    assert (_sha(out), _sha(js)) == before
    assert sorted(p.name for p in out.parent.iterdir()) == sorted([out.name, js.name])


def test_w03_success_replaces_both(boq, made, capsys):
    out, js = made
    old_json = js.read_text(encoding="utf-8")
    assert main(_plan_args(boq, out) + ["--non-ks"]) == 0
    assert js.read_text(encoding="utf-8") != old_json                 # 철근 KS 아님 → 계산이 바뀜
    assert sorted(p.name for p in out.parent.iterdir()) == sorted([out.name, js.name])


# ── W04 경로 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,want", [
    ("\\\\server\\share\\boq.xlsx", "\\\\server\\share\\boq.xlsx"),              # UNC 공유 폴더
    (".\\내 폴더\\내역서.xlsx", ".\\내 폴더\\내역서.xlsx"),                          # 상대 경로
    ("..\\내역서.xlsx", "..\\내역서.xlsx"),
    ("file:///C:/folder/boq.xlsx", "C:/folder/boq.xlsx"),                        # 파일 URI(드라이브)
    ("file:///C:/%EB%82%B4%20%ED%8F%B4%EB%8D%94/boq.xlsx", "C:/내 폴더/boq.xlsx"),
    ("C:\\내 폴더\\내역서.xlsx", "C:\\내 폴더\\내역서.xlsx"),                          # 드라이브
    ('"C:\\내 폴더\\내역서.xlsx"', "C:\\내 폴더\\내역서.xlsx"),                        # 탐색기 '경로로 복사'(따옴표)
    ("C:/folder/boq.xlsx", "C:/folder/boq.xlsx"),
    ("/Users/a/내\\ 파일\\(1\\).xlsx", "/Users/a/내 파일(1).xlsx"),                  # 맥 터미널 끌어다 놓기(계속 동작)
    ("'/Users/a/내 파일.xlsx'", "/Users/a/내 파일.xlsx"),
    ("file:///Users/a/%EB%82%B4.xlsx", "/Users/a/내.xlsx"),
])
def test_w04_clean_path_table(raw, want):
    assert clean_path(raw) == want


def test_w04_windows_keeps_every_backslash(monkeypatch):
    """Windows 에서 실행 중이면 모양과 상관없이 역슬래시는 구분자(맥 이스케이프 해제를 하지 않는다)."""
    monkeypatch.setattr(os, "name", "nt")
    assert clean_path("내 폴더\\내역서 (1).xlsx") == "내 폴더\\내역서 (1).xlsx"
    assert clean_path("file://server/share/boq.xlsx") == "\\\\server\\share\\boq.xlsx"


# ── W06 입력 실수 ────────────────────────────────────────────────────

def _one_line_error(r) -> str:
    err = r.stderr.decode("utf-8") + r.stdout.decode("utf-8")
    assert "Traceback" not in err, err
    return err


def test_w06_missing_boq(tmp_path):
    r = subprocess.run([str(DANBURN), "inspect", "--boq", str(tmp_path / "없는 파일.xlsx")], capture_output=True,
                       env=_env(tmp_path / "h"), timeout=120)
    err = _one_line_error(r)
    assert r.returncode == 2 and "내역서 파일이 없습니다" in err and "--boq" in err


def test_w06_xls_and_folder(tmp_path, capsys):
    (tmp_path / "옛.xls").write_bytes(b"\xd0\xcf\x11\xe0")
    assert main(["inspect", "--boq", str(tmp_path / "옛.xls")]) == 2
    assert ".xlsx" in capsys.readouterr().err
    assert main(["inspect", "--boq", str(tmp_path)]) == 2
    assert "파일이 아닙니다" in capsys.readouterr().err


def test_w06_corrupt_xlsx(tmp_path, capsys):
    (tmp_path / "깨짐.xlsx").write_bytes(b"not a zip")
    assert main(["inspect", "--boq", str(tmp_path / "깨짐.xlsx")]) == 2
    assert "내역서를 읽지 못했습니다" in capsys.readouterr().err


def test_w06_missing_answers(tmp_path):
    r = subprocess.run([str(DANBURN), "start", "--answers", str(tmp_path / "없는 답.yaml")], capture_output=True,
                       env=_env(tmp_path / "h"), timeout=120)
    err = _one_line_error(r)
    assert r.returncode == 2 and "답(--answers) 파일이 없습니다" in err


def test_w06_broken_project_yaml(boq, tmp_path):
    bad = tmp_path / "broken.yaml"
    bad.write_text("공사명: [\n", encoding="utf-8")
    out = tmp_path / "o.hwpx"
    r = subprocess.run([str(DANBURN), *_plan_args(boq, out)[:-2], "--project", str(bad), "--out", str(out)],
                       capture_output=True, env=_env(tmp_path / "h"), timeout=120)
    err = _one_line_error(r)
    assert r.returncode == 2 and "YAML 구문" in err and "broken.yaml" in err and "째 줄" in err
    assert not out.exists() and not out.with_suffix(".json").exists()


def test_w06_debug_env_shows_traceback(tmp_path, monkeypatch, capsys):
    """예상 못 한 오류는 한 줄 + 종료 1, DANBURN_DEBUG=1 이면 원래 예외가 그대로 올라온다."""
    def boom(a):
        raise RuntimeError("합성 오류")
    monkeypatch.setattr(cli, "cmd_check_basis", boom)
    assert main(["check-basis", "--offline"]) == 1
    assert "DANBURN_DEBUG=1" in capsys.readouterr().err
    monkeypatch.setenv("DANBURN_DEBUG", "1")
    with pytest.raises(RuntimeError):
        main(["check-basis", "--offline"])
