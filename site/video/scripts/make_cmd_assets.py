#!/usr/bin/env python3
"""랜딩 "세 가지 일" 영상(CmdStart·CmdTestPlan·CmdCheck) 재료를 도구의 실제 출력에서 만든다(합성 예제만, 실제 현장 자료 없음).

- start: 합성 내역서(scripts/make_example_boq.py)를 빈 폴더에 두고
  `danburn start --plain --input <답 목록> --offline --folder … --out-dir <tmp>` 를 돌린다.
  출력 줄(out)과 답 목록(answers)을 그대로 적고, 화면에 보일 줄(screen)은 그중에서 고르기만 한다.
  질문 줄 다음에는 그 질문이 읽은 답을 입력 줄(› 답)로 둔다(한 줄 모드는 답을 되풀이해 찍지 않으므로).
  만든 계획서(.hwpx)는 rhwp → PDF → 쪽 PNG(표지·8.11)로.
- testplan: start 와 같은 답으로 산출 폴더를 만든 뒤 `danburn test-plan --project 산출/project.yaml --offline`.
  출력 줄(사람용 결과 화면)을 out 으로, 화면 줄은 그중에서 고른다. 파일 위치·행 수는 같은 명령의 --json 으로 받고
  화면의 '시험 N행' 이 JSON rows 와 같은지 verify 가 본다. 만든 한글 문서는 rhwp → PDF → 쪽 PNG(2부 가로 표·시험실 (스캔첨부)),
  엑셀은 openpyxl 로 다시 읽어 시트 이름만 적는다(엑셀을 그림으로 그리지 않는다 — 오피스 프로그램 없음).
- check: 우리 합성 계획서(`danburn plan`, tests/test_check_cli.py 의 our_plan 과 같은 인자)를
  tests/test_check_cli.py 의 _make_old_plan 으로 옛 기준 계획서로 바꾸고(같은 함수를 불러 씀)
  `danburn check "옛기준 계획서.hwpx"` 출력 줄을 적는다 — skills/check/SKILL.md 처럼 --offline·--json 없이(에이전트가
  보여 주는 사람용 결과 화면과 같게). 인터넷 확인이 안 되면 --offline 으로 다시 돌리고 그 사실을 JSON(online)에 남긴다.

화면 줄 규칙(대조표의 기준): screen 항목의 text 는 out[i] 와 같거나, 임시 폴더 경로 앞부분만 "…/" 로 줄인 것이다.
줄을 건너뛴 자리는 {"k": "gap", "text": "…"}. 긴 줄의 끝 자르기(…)는 영상 쪽 줄 수(rows)로만 한다 — 글자는 바꾸지 않는다.

산출: site/video/public/cmd/{start,testplan,check}.json, site/video/public/cmd/{start,testplan}-*.png
사용(저장소 루트에서): .venv/bin/python site/video/scripts/make_cmd_assets.py [--only start,testplan,check]
  --only 를 주면 그 재료만 새로 만들고 나머지 파일은 그대로 둔다(이미 렌더한 영상과 재료가 어긋나지 않게).
필요: .venv(danburn), rhwp(.tools/rhwp/rhwp — 워크트리에 없으면 원래 체크아웃의 것), pdftoppm·pdftotext·pdfinfo(poppler)
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parents[1] / "public" / "cmd"
PY = ROOT / ".venv" / "bin" / "python"
DANBURN = ROOT / ".venv" / "bin" / "danburn"
PROJECT = ROOT / "src" / "danburn" / "data" / "templates" / "project.example.yaml"
BOQ_NAME = "도급내역서.xlsx"
OLD_NAME = "옛기준 계획서.hwpx"
DPI = 110

# start 답 목록(한 줄에 답 하나, 빈 줄 = 기본값). 값은 합성 예제(project.example.yaml)의 것.
ANSWERS = [
    "1",                                   # Q1 내역서: 1=도급내역서.xlsx
    "3",                                   # Q1-1 블록: 3=나동
    "가상시 예시지구 공동주택 신축공사",       # Q6-1 공사명
    "예시공사(발주기관)",                     # Q2-1 발주자
    "1",                                   # Q2 발주자_구분: 발주청
    "Y",                                   # Q3 공사종류(내역서에서 읽은 값 확인)
    "1",                                   # Q3-1 KS_인증: 예(KS 인증품)
    "100",                                 # Q4-1 총공사비_억원
    "40000",                               # Q4-2 연면적
    "15",                                  # Q4-3 지상층수
    "1",                                   # Q5-2 계약_품질관리계획: 예
    "1",                                   # Q5-3 주용도: 해당 없음(공동주택 등)
    "",                                    # Q7 로고: 없음
    "샘플건설 주식회사",                      # Q6-4 시공자
    "2",                                   # Q6 사람_회사_지금: 나중에
    "Y",                                   # 판정 맞나요?
    "Y",                                   # 지금 계획서를 만들까요?
]
PROMPT = re.compile(r"^Q[\d-]+ |\[Y/n\]")     # 답 하나를 읽는 줄(한 줄 모드)


def run(*cmd, cwd: Path | None = None, ok=(0,)) -> tuple[int, str]:
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd)
    if p.returncode not in ok:
        raise SystemExit(f"실패({p.returncode}): {' '.join(map(str, cmd))}\n{p.stdout}\n{p.stderr}")
    return p.returncode, p.stdout


def rhwp() -> Path:
    here = ROOT / ".tools" / "rhwp" / "rhwp"
    if here.exists():
        return here
    common = Path(run("git", "rev-parse", "--path-format=absolute", "--git-common-dir", cwd=ROOT)[1].strip())
    return common.parent / ".tools" / "rhwp" / "rhwp"


def shorten(line: str, tmp: Path) -> str:
    """임시 폴더 경로 앞부분만 …/ 로(나머지 글자는 그대로)."""
    s = line.replace(str(tmp.resolve()) + "/", "…/").replace(str(tmp) + "/", "…/")
    return re.sub(r"…/(?:[^/\s]+/)+", "…/", s)


def pick(out: list[str], tmp: Path, pred) -> dict:
    i = next(n for n, t in enumerate(out) if pred(t))
    return {"k": "out", "i": i, "text": shorten(out[i], tmp)}


def run_start(tmp: Path) -> tuple[Path, list[str]]:
    """합성 내역서 + ANSWERS 로 danburn start(한 줄 모드) → (산출 폴더, 출력 줄)."""
    folder = tmp / "현장"
    folder.mkdir()
    run(PY, ROOT / "scripts" / "make_example_boq.py", "--out", folder / BOQ_NAME)
    inp = tmp / "답목록.txt"
    inp.write_text("\n".join(ANSWERS) + "\n", encoding="utf-8")
    outdir = tmp / "산출"
    _, text = run(DANBURN, "start", "--plain", "--input", inp, "--offline", "--folder", folder, "--out-dir", outdir)
    return outdir, text.splitlines()


def pdf_pages(hwpx: Path, pdf: Path) -> list[str]:
    """hwpx → rhwp PDF → 쪽마다 글(빈칸 뺌)."""
    run(rhwp(), "export-pdf", hwpx, "-o", pdf)
    pages = int(re.search(r"Pages:\s+(\d+)", run("pdfinfo", pdf)[1]).group(1))
    return [re.sub(r"\s", "", run("pdftotext", "-f", n, "-l", n, pdf, "-")[1]) for n in range(1, pages + 1)]


def make_start(tmp: Path) -> dict:
    outdir, out = run_start(tmp)

    # 질문 줄 ↔ 답: 한 줄 모드는 질문마다 답 한 줄을 읽는다(되묻기 없이 끝났는지 확인)
    prompts = [n for n, t in enumerate(out) if PROMPT.search(t)]
    assert len(prompts) == len(ANSWERS), (len(prompts), len(ANSWERS), out)
    answer_of = dict(zip(prompts, range(len(ANSWERS))))

    def with_answer(pred) -> list[dict]:
        q = pick(out, tmp, pred)
        a = answer_of[q["i"]]
        return [q, {"k": "in", "a": a, "text": ANSWERS[a]}]

    gap = {"k": "gap", "text": "…"}
    screen = [
        {"k": "cmd", "text": "/danburn:start"},
        *with_answer(lambda t: t.startswith("Q1 내역서")),
        pick(out, tmp, lambda t: t.startswith("READ ")),
        *with_answer(lambda t: t.startswith("Q1-1 블록")),
        gap,
        pick(out, tmp, lambda t: t == "JUDGE"),
        pick(out, tmp, lambda t: t.strip().startswith("계획 종류")),
        pick(out, tmp, lambda t: t.strip().startswith("배치 등급")),
        gap,
        *with_answer(lambda t: t.startswith("지금 계획서를 만들까요?")),
        {**pick(out, tmp, lambda t: t.startswith("계획서: ")), "hl": True},
    ]

    hwpx = next(outdir.glob("*.hwpx"))
    pdf = tmp / "start.pdf"
    run(rhwp(), "export-pdf", hwpx, "-o", pdf)
    pages = int(re.search(r"Pages:\s+(\d+)", run("pdfinfo", pdf)[1]).group(1))
    table = next(n for n in range(1, pages + 1)
                 if "품질시험및검사계획" in re.sub(r"\s", "", run("pdftotext", "-f", n, "-l", n, pdf, "-")[1]))
    shots = {}
    for name, n in (("cover", 1), ("table", table)):
        run("pdftoppm", "-r", DPI, "-png", "-singlefile", "-f", n, "-l", n, pdf, OUT / f"start-{name}")
        shots[name] = f"cmd/start-{name}.png"
    return {"command": "/danburn:start",
            "tool": "danburn start --plain --input 답목록.txt --offline --folder 현장 --out-dir 산출",
            "answers": ANSWERS, "out": [shorten(t, tmp) for t in out], "screen": screen,
            "doc": {"file": hwpx.name, "pages": pages, "table_page": table, "shots": shots}}


def next_steps(out: list[str], tmp: Path) -> list[dict]:
    """'다음 할 일' 부분: 한 줄이면 그 줄(강조), 두 단계면 머리 줄 + 1) 줄(강조) + …(화면 줄 수 안에서)."""
    head = pick(out, tmp, lambda t: t.startswith("다음 할 일"))
    if head["text"] != "다음 할 일:":
        return [{**head, "hl": True}]
    one = pick(out, tmp, lambda t: t.startswith("  1) "))
    return [head, {**one, "hl": True}, {"k": "gap", "text": "…"}]


def make_testplan(tmp: Path) -> dict:
    import openpyxl
    outdir, _ = run_start(tmp)
    project = outdir / "project.yaml"
    # 화면 = 사람용 결과 화면(기본 출력). 파일 위치·행 수는 같은 명령의 --json 으로(두 번 돌려도 같은 계산)
    _, text = run(DANBURN, "test-plan", "--project", project, "--offline")
    _, raw = run(DANBURN, "test-plan", "--project", project, "--offline", "--json")
    obj = json.loads(raw)
    out = [shorten(t, tmp) for t in text.splitlines()]
    rows = obj["test_plan"]["rows"]
    gap = {"k": "gap", "text": "…"}
    warn_head = next(n for n, t in enumerate(out) if t.startswith("확인할 것"))
    screen = [
        {"k": "cmd", "text": "/danburn:test-plan 산출"},
        pick(out, tmp, lambda t: t.startswith("단번 품질시험계획서")),
        {**pick(out, tmp, lambda t: t.startswith("만든 파일: ")), "hl": True},
        {**pick(out, tmp, lambda t: t.startswith("시험 ")), "mark": f"시험 {rows}행"},
        {"k": "out", "i": warn_head, "text": out[warn_head]},
        *([{"k": "out", "i": warn_head + 1, "text": out[warn_head + 1]}, gap] if out[warn_head].endswith(":") else []),
        {**(scan := pick(out, tmp, lambda t: t.startswith("(스캔첨부) 빈칸"))), "mark": scan["text"].split(":")[0]},
        *next_steps(out, tmp),
    ]
    hwpx, xlsx = Path(obj["hwpx"]), Path(obj["xlsx"])
    texts = pdf_pages(hwpx, tmp / "testplan.pdf")
    table = next(n for n, t in enumerate(texts, 1) if "계획물량" in t and "시험품목" in t)          # 2부 표 첫 쪽(목차에는 이 칸 이름이 없다)
    room = next(n for n, t in enumerate(texts, 1) if "(스캔첨부)시험실배치평면도" in t)
    shots = {}
    for name, n in (("table", table), ("room", room)):
        run("pdftoppm", "-r", DPI, "-png", "-singlefile", "-f", n, "-l", n, tmp / "testplan.pdf", OUT / f"testplan-{name}")
        shots[name] = f"cmd/testplan-{name}.png"
    sheets = openpyxl.load_workbook(xlsx, read_only=True).sheetnames
    return {"command": "/danburn:test-plan 산출",
            "tool": "danburn test-plan --project 산출/project.yaml --offline (그림·행 수는 같은 명령 --json)",
            "out": out, "screen": screen, "json_rows": rows,
            "doc": {"file": hwpx.name, "xlsx": xlsx.name, "pages": len(texts), "table_page": table, "room_page": room,
                    "shots": shots, "sheets": sheets, "rows": rows}}


def make_check(tmp: Path) -> dict:
    spec = importlib.util.spec_from_file_location("test_check_cli", ROOT / "tests" / "test_check_cli.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    boq = tmp / "boq.xlsx"
    run(PY, ROOT / "scripts" / "make_example_boq.py", "--out", boq)
    plan = tmp / "plan.hwpx"                      # tests/test_check_cli.py our_plan 과 같은 인자
    run(DANBURN, "plan", "--boq", boq, "--block", "나동", "--project", PROJECT, "--revision", "0",
        "--date", "2026. 01. 05.", "--offline", "--out", plan)
    mod._make_old_plan(plan, tmp / OLD_NAME)
    rc, text = run(DANBURN, "check", OLD_NAME, cwd=tmp, ok=(3,))                # 3 = 개정·폐지된 기준 있음
    online = "인터넷(공개 법령 사본)으로 확인" in text                           # src/danburn/plancheck.py 의 온라인 확인 줄
    tool = f'danburn check "{OLD_NAME}"'
    if not online:                                                              # 인터넷 실패: 동봉 기준표로(화면에 뽑는 줄은 같음)
        rc, text = run(DANBURN, "check", OLD_NAME, "--offline", cwd=tmp, ok=(3,))
        tool += " --offline"
    out = text.splitlines()
    gap = {"k": "gap", "text": "…"}
    items = [{"k": "out", "i": n, "text": t, "item": True} for n, t in enumerate(out) if t.startswith("[개정됨]")]
    result = pick(out, tmp, lambda t: t.startswith("결과: "))
    m = re.search(r"개정됨 \d+", result["text"])
    screen = [
        {"k": "cmd", "text": f"/danburn:check {OLD_NAME}"},
        pick(out, tmp, lambda t: t.startswith("단번 기준 검사 — ")),
        {**result, "hl": True, "mark": m.group(0)},
        gap,
        *items,
        gap,
        pick(out, tmp, lambda t: t.startswith("이 결과는 알림입니다")),
    ]
    return {"command": f"/danburn:check {OLD_NAME}", "tool": tool, "online": online,
            "exit": rc, "out": out, "screen": screen}


def verify(d: dict) -> None:
    """화면 줄 = 실제 출력 줄(경로 앞부분 …/ 만 허용), 입력 줄 = 답 목록. 강조 글(mark)은 그 줄 안의 글자 그대로."""
    for s in d["screen"]:
        if s.get("mark"):
            assert s["mark"] in s["text"], s
        if s["k"] == "out":
            assert s["text"] == d["out"][s["i"]], s
        elif s["k"] == "in":
            assert s["text"] == d["answers"][s["a"]], s
        elif s["k"] == "cmd":
            assert s["text"] == d["command"], s
        else:
            assert s == {"k": "gap", "text": "…"}, s
    if "json_rows" in d:                                   # testplan: 화면의 행 수 = --json 의 rows
        assert any(s.get("mark") == f"시험 {d['json_rows']}행" for s in d["screen"]), d["json_rows"]


MAKERS = {"start": make_start, "testplan": make_testplan, "check": make_check}


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(MAKERS), help="만들 재료(쉼표로): start, testplan, check")
    names = [n.strip() for n in ap.parse_args(argv).only.split(",") if n.strip()]
    bad = [n for n in names if n not in MAKERS]
    if bad:
        raise SystemExit(f"--only 는 {', '.join(MAKERS)} 중에서: {bad}")
    if set(names) == set(MAKERS) and OUT.exists():
        shutil.rmtree(OUT)                      # 전부 새로 만들 때만 비운다
    OUT.mkdir(parents=True, exist_ok=True)
    for name in names:
        for old in OUT.glob(f"{name}-*.png"):
            old.unlink()
        with tempfile.TemporaryDirectory() as t:
            d = MAKERS[name](Path(t))
        verify(d)
        (OUT / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        if name == "start":
            print(f"start: out {len(d['out'])}줄 → 화면 {len(d['screen'])}줄, 계획서 {d['doc']['pages']}쪽(8.11 p{d['doc']['table_page']})")
        elif name == "testplan":
            print(f"testplan: out {len(d['out'])}줄 → 화면 {len(d['screen'])}줄, 시험 행 {d['doc']['rows']}, 한글 {d['doc']['pages']}쪽"
                  f"(표 p{d['doc']['table_page']}, 시험실 p{d['doc']['room_page']}), 엑셀 시트 {len(d['doc']['sheets'])}")
        else:
            print(f"check: out {len(d['out'])}줄 → 화면 {len(d['screen'])}줄, 종료 {d['exit']}, 인터넷 확인 {'됨' if d['online'] else '실패 → --offline'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
