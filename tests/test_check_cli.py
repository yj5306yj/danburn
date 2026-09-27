"""`danburn check` (기존 계획서 검사) 명령 표면: 종료 코드·사람용 요약·JSON·못 읽는 파일. 합성 산출물만 쓴다."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from danburn.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "src/danburn/data/templates/project.example.yaml"


@pytest.fixture(scope="module")
def our_plan(tmp_path_factory):
    d = tmp_path_factory.mktemp("check")
    boq = d / "boq.xlsx"
    subprocess.run([sys.executable, str(ROOT / "scripts/make_example_boq.py"), "--out", str(boq)], check=True,
                   capture_output=True)
    out = d / "plan.hwpx"
    assert main(["plan", "--boq", str(boq), "--block", "나동", "--project", str(EXAMPLE), "--revision", "0",
                 "--date", "2026. 01. 05.", "--offline", "--out", str(out)]) == 0
    return out


def test_check_our_plan_summary(our_plan, capsys):
    rc = main(["check", str(our_plan), "--offline"])
    text = capsys.readouterr().out
    assert rc == 0                                   # 우리 템플릿이 스스로 '개정됨'으로 나오면 안 된다
    assert text.startswith("단번 기준 검사 — plan.hwpx (HWPX)")
    assert "결과: " in text and "모두 현행입니다" in text and "개정·폐지된 기준" not in text
    assert "[참고]" not in text                      # 판정 안 한 인용은 한 줄로 묶는다
    assert "공식 원문" in text


OLD_REFS = "적용기준: KCS 14 20 10 : 2022 일반콘크리트, KCS 11 44 00 : 2021 공동구, 건설기술관리법 시행령"


def _make_old_plan(src: Path, dst: Path) -> None:
    """우리 합성 계획서를 '옛 기준으로 쓴 계획서'로 바꾼다: 업무지침 제2022-30호, 작성일 2023년, 옛 코드·옛 법령명."""
    import re
    import zipfile
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("Contents/section"):
                xml = data.decode("utf-8").replace("제2026-360호", "제2022-30호").replace("2026. 01. 05.", "2023. 03. 02.")
                if item.filename == "Contents/section0.xml":                 # 첫 글자 칸 뒤에 옛 인용 문장을 붙인다
                    xml = re.sub(r"(<hp:t>[^<]*)(</hp:t>)", lambda m: f"{m.group(1)} {OLD_REFS}{m.group(2)}", xml, count=1)
                data = xml.encode("utf-8")
            zout.writestr(item, data)


def test_check_catches_plan_written_on_old_standards(our_plan, tmp_path, capsys):
    """옛 기준으로 쓴 계획서 한 권을 끝까지 넣으면 옛 업무지침·작성일·옛 연도판·폐지 코드·옛 법령명을 모두 '개정됨'으로 잡는다."""
    old = tmp_path / "옛기준 계획서.hwpx"
    _make_old_plan(our_plan, old)
    assert main(["check", str(old), "--offline", "--json"]) == 3
    res = json.loads(capsys.readouterr().out)
    got = {(f["kind"], f.get("norm") or f.get("cited")) for f in res["findings"] if f["status"] == "outdated"}
    kinds = {k for k, _ in got}
    assert {"admrule", "plan_date", "code", "obsolete_name"} <= kinds, got
    codes = {n for k, n in got if k == "code"}
    assert "KCS 14 20 10" in codes and "KCS 11 44 00" in codes, codes
    rc = main(["check", str(old), "--offline"])
    text = capsys.readouterr().out
    assert rc == 3 and "결과: 개정·폐지된 기준" in text and "KCS 29 10 00" in text     # 폐지 코드는 이어받은 코드를 알려 준다


def test_check_json_is_parseable(our_plan, capsys):
    rc = main(["check", str(our_plan), "--offline", "--json"])
    res = json.loads(capsys.readouterr().out)
    assert rc == 0 and res["status"] == "current"
    assert res["file"]["format"] == "hwpx" and res["snapshot_checked_at"].startswith("20")


def test_headline_does_not_say_all_current_when_unknown_remains():
    """독립 리뷰 H2: 확인 필요가 남았는데 '모두 현행'이라고 하면 안 된다(종료 코드 0 은 설계대로 유지)."""
    from types import SimpleNamespace
    from danburn.cli import _plan_report_text
    res = {"status": "current", "findings": [
        {"kind": "admrule", "status": "current", "cited": "고시 제2026-360호"},
        {"kind": "code", "status": "unknown", "cited": "KCS 98 10 10 : 2015", "advice": "직접 확인"}]}
    text = _plan_report_text("a.hwpx", SimpleNamespace(format="hwpx", warnings=[]), res)
    assert "모두 현행입니다\n" not in text and "판정하지 못한 인용 1건" in text


def test_check_unreadable_file_exit_2(tmp_path, capsys):
    bad = tmp_path / "계획서.pdf"
    bad.write_bytes(b"not a pdf")
    assert main(["check", str(bad), "--offline"]) == 2
    assert "계획서를 읽지 못했습니다" in capsys.readouterr().out


def test_check_plan_old_name_removed(capsys):
    with pytest.raises(SystemExit):
        main(["check-plan", "x.hwpx"])
