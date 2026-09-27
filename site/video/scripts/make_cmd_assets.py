#!/usr/bin/env python3
"""랜딩 "두 가지 일" 영상(CmdStart·CmdCheck) 재료를 도구의 실제 출력에서 만든다(합성 예제만, 실제 현장 자료 없음).

- start: 합성 내역서(scripts/make_example_boq.py)를 빈 폴더에 두고
  `danburn start --plain --input <답 목록> --offline --folder … --out-dir <tmp>` 를 돌린다.
  출력 줄(out)과 답 목록(answers)을 그대로 적고, 화면에 보일 줄(screen)은 그중에서 고르기만 한다.
  질문 줄 다음에는 그 질문이 읽은 답을 입력 줄(› 답)로 둔다(한 줄 모드는 답을 되풀이해 찍지 않으므로).
  만든 계획서(.hwpx)는 rhwp → PDF → 쪽 PNG(표지·8.11)로.
- check: 우리 합성 계획서(`danburn plan`, tests/test_check_cli.py 의 our_plan 과 같은 인자)를
  tests/test_check_cli.py 의 _make_old_plan 으로 옛 기준 계획서로 바꾸고(같은 함수를 불러 씀)
  `danburn check "옛기준 계획서.hwpx"` 출력 줄을 적는다 — skills/check/SKILL.md 처럼 --offline·--json 없이(에이전트가
  보여 주는 사람용 결과 화면과 같게). 인터넷 확인이 안 되면 --offline 으로 다시 돌리고 그 사실을 JSON(online)에 남긴다.

화면 줄 규칙(대조표의 기준): screen 항목의 text 는 out[i] 와 같거나, 임시 폴더 경로 앞부분만 "…/" 로 줄인 것이다.
줄을 건너뛴 자리는 {"k": "gap", "text": "…"}. 긴 줄의 끝 자르기(…)는 영상 쪽 줄 수(rows)로만 한다 — 글자는 바꾸지 않는다.

산출: site/video/public/cmd/{start,check}.json, site/video/public/cmd/start-*.png
사용(저장소 루트에서): .venv/bin/python site/video/scripts/make_cmd_assets.py
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


def make_start(tmp: Path) -> dict:
    folder = tmp / "현장"
    folder.mkdir()
    run(PY, ROOT / "scripts" / "make_example_boq.py", "--out", folder / BOQ_NAME)
    inp = tmp / "답목록.txt"
    inp.write_text("\n".join(ANSWERS) + "\n", encoding="utf-8")
    outdir = tmp / "산출"
    _, text = run(DANBURN, "start", "--plain", "--input", inp, "--offline", "--folder", folder, "--out-dir", outdir)
    out = text.splitlines()

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
    """화면 줄 = 실제 출력 줄(경로 앞부분 …/ 만 허용), 입력 줄 = 답 목록."""
    for s in d["screen"]:
        if s["k"] == "out":
            assert s["text"] == d["out"][s["i"]], s
        elif s["k"] == "in":
            assert s["text"] == d["answers"][s["a"]], s
        elif s["k"] == "cmd":
            assert s["text"] == d["command"], s
        else:
            assert s == {"k": "gap", "text": "…"}, s


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as t:
        start = make_start(Path(t))
    with tempfile.TemporaryDirectory() as t:
        check = make_check(Path(t))
    for name, d in (("start", start), ("check", check)):
        verify(d)
        (OUT / f"{name}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"start: out {len(start['out'])}줄 → 화면 {len(start['screen'])}줄, 계획서 {start['doc']['pages']}쪽(8.11 p{start['doc']['table_page']})")
    print(f"check: out {len(check['out'])}줄 → 화면 {len(check['screen'])}줄, 종료 {check['exit']}, 인터넷 확인 {'됨' if check['online'] else '실패 → --offline'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
