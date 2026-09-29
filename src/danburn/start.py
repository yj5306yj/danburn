"""`danburn start` — 첫 실행 인터뷰: 몇 가지 질문 → 법 판정 → project.yaml → 계획서(plan) → 확인할 것 목록.

설계: 조사 L7-S1 §2·§3·§5. 질문 목록은 data/interview.yaml(스킬과 공유), 판정은 judge.py.
모드: 대화형(기본) · --plain(한 줄 질문, 에이전트·스크린리더용) · --answers <yaml>(비대화형).
개인정보(L7-S1 §3):
- 첨부(자격·경력 증빙)는 복사하지 않고 project.yaml 에 절대 경로만 적는다. 1차는 목록만(계획서에 이미지로 넣지 않음).
- 화면·요약·로그에는 첨부 파일 이름·경로를 쓰지 않고 개수만 쓴다.
- 산출 폴더 기본값은 저장소 밖(~/Documents/danburn/<공사명>/). git 작업 트리 안이면서 무시되지 않는 곳은 거부한다.
새 의존성 없음(input()·PyYAML 만).
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import yaml

from .judge import GRADES, decides, judge, number
from .paths import DATA_DIR, TEMPLATES_DIR

INTERVIEW = DATA_DIR / "interview.yaml"
EXAMPLE = TEMPLATES_DIR / "project.example.yaml"
TODO = "(작성 필요)"
ATTACH_WORDS = ("자격", "경력", "증명", "면허", "수첩", "cert", "license")
LOGO_WORDS = ("로고", "logo", "ci", "CI")
EDIT_LATER = "project.yaml 의 조직·품질목표·품질방침·결재·시험장비·건설사업관리자·문서번호(예시 값이거나 비어 있음)"


class StartError(Exception):
    """인터뷰를 계속할 수 없다(메시지를 그대로 보여 주고 종료 2)."""


# ── 경로 ──────────────────────────────────────────────────────────────

WIN_SHAPE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\[^\\\s]|\.{1,2}\\)")   # C:\ · C:/ · \\server · .\ · ..\
SHELL_ESCAPED = re.compile(r"\\([ \t!\"#$&'()*,;<=>?\[\\\]^`{|}~])")      # 맥 터미널이 끌어다 놓을 때 붙이는 이스케이프


def clean_path(s: str) -> str:
    """끌어다 놓은 경로 정리: 앞뒤 빈칸·따옴표, file:// URI, 맥 터미널의 역슬래시 이스케이프(\\ 공백), ~.

    Windows 모양(드라이브 문자·UNC 공유 경로·점-역슬래시 상대 경로)이거나 Windows 에서 실행 중이면 역슬래시는 구분자라
    그대로 둔다(WIN_SHAPE).
    맥·리눅스에서는 셸 특수문자 앞의 역슬래시만 푼다(한글·영문 앞 역슬래시는 남긴다)."""
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1]
    if s.lower().startswith("file://"):
        rest = unquote(s[len("file://"):])
        if rest.lower().startswith("localhost/"):
            rest = rest[len("localhost"):]
        if re.match(r"^/[A-Za-z]:[\\/]", rest):               # file:///C:/x → C:/x
            s = rest[1:]
        elif rest.startswith("/"):                             # file:///Users/x → /Users/x
            s = rest
        else:                                                  # file://server/share/x → UNC
            s = "\\\\" + rest.replace("/", "\\") if os.name == "nt" else "//" + rest
        return s
    # 맥·리눅스, 또는 Windows 에서도 '/' 로 시작하는 경로(Windows 경로일 수 없음 — 맥식 끌어다 놓기)는 이스케이프를 푼다
    if not WIN_SHAPE.match(s) and (os.name != "nt" or s.startswith("/")):
        s = SHELL_ESCAPED.sub(r"\1", s)
    return os.path.expanduser(s)


def home_dir() -> Path:
    """초안 저장 폴더(저장소 밖). 테스트는 DANBURN_HOME 으로 바꾼다."""
    return Path(os.environ.get("DANBURN_HOME") or Path.home() / ".danburn")


def default_out_dir(name: str) -> Path:
    root = Path(os.environ.get("DANBURN_OUT_ROOT") or Path.home() / "Documents" / "danburn")
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_") or "현장"
    return root / safe


def tracked_in_repo(path: Path) -> str | None:
    """path 가 git 작업 트리 안이면서 무시되지 않는 곳이면 그 저장소 루트(커밋 사고 방지). 아니면 None."""
    p = Path(path).expanduser().resolve()
    probe = p if p.is_dir() else p.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    # Git 출력은 UTF-8(한국어 Windows 기본 cp949 로 읽으면 한글 경로가 깨진다 — W01). 루트 경로는 보여 주기용이고
    # 무시 여부는 probe 폴더에서 바로 묻는다(출력 해석에 판정을 기대지 않음).
    git = ["git", "-c", "core.quotepath=off", "-C", str(probe)]
    try:
        top = subprocess.run([*git, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=10)
        if top.returncode != 0:
            return None
        ign = subprocess.run([*git, "check-ignore", "-q", str(p)], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if ign.returncode == 0:
        return None
    root = (top.stdout or "").strip()
    return str(Path(root)) if root else str(probe)


def scan_folder(folder: Path) -> dict:
    """폴더의 내역서 후보(xlsx)·로고 후보(png/jpg)·증빙 후보 개수(이름은 모으지 않는다)."""
    files = [f for f in sorted(folder.iterdir()) if f.is_file() and not f.name.startswith(("~$", "."))] \
        if folder.is_dir() else []
    boq = [f for f in files if f.suffix.lower() == ".xlsx"]
    attach = [f for f in files if f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg")
              and any(w in f.name for w in ATTACH_WORDS)]
    logo = [f for f in files if f.suffix.lower() in (".png", ".jpg", ".jpeg") and f not in attach]
    logo.sort(key=lambda f: not any(w in f.name for w in LOGO_WORDS))
    return {"boq": boq, "logo": logo, "attach_count": len(attach)}


COVER_SHEETS = ("표지", "갑지", "원가", "총괄", "집계", "개요")
COVER_KEYS = {"공사명": ("공사명", "건명"), "발주자": ("발주자", "발주처", "발주기관", "발주청"),
              "총액": ("총공사비", "도급액", "도급금액", "총도급액", "공사비합계", "총계", "합계금액")}
PUBLIC_OWNER = re.compile(r"LH|한국토지주택공사|공사$|공단$|청$|시청|구청|군청|도청|국토교통부|조달청|교육청|공사\)")


def read_cover(path: str) -> dict:
    """표지·갑지·원가계산서 같은 시트에서 공사명·발주자·총액(원) 후보를 찾는다(못 찾으면 없음). 읽기만 한다.

    '공 사 명 : 값'처럼 한 칸에 있거나, 이름 칸 오른쪽의 첫 값 칸을 쓴다. 총액은 오른쪽의 첫 숫자(원)."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return {}
    sheets = sorted(wb.worksheets, key=lambda ws: not any(k in ws.title for k in COVER_SHEETS))
    found: dict = {}
    for ws in sheets[:8]:
        limit = 60 if any(k in ws.title for k in COVER_SHEETS) else 8
        for row in ws.iter_rows(min_row=1, max_row=limit, max_col=20, values_only=True):
            cells = list(row)
            for i, v in enumerate(cells):
                if not isinstance(v, str):
                    continue
                v = v.replace("：", ":")
                label = re.sub(r"\s+", "", v).split(":", 1)[0]
                for name, keys in COVER_KEYS.items():
                    if name in found or not any(label == k or label.endswith(k) for k in keys):
                        continue
                    rest = [x for x in cells[i + 1:] if x not in (None, "")]
                    if name == "총액":
                        nums = [x for x in rest if isinstance(x, (int, float))] or \
                               [number(x) for x in rest if number(x) is not None]
                        if nums and float(nums[0]) >= 1e6:            # 원 단위 금액만
                            found[name] = float(nums[0])
                    else:
                        text = v.split(":", 1)[1].strip() if ":" in v else (str(rest[0]).strip() if rest else "")
                        if text and len(text) >= 2:
                            found[name] = text
    return found


def read_boq_info(path: str) -> dict:
    """내역서를 읽어 블록 목록·분야·표지 후보(공사명·발주자·총액)를 돌려준다. 못 읽으면 StartError."""
    from .boq import read_boq
    try:
        lines = read_boq(path)
    except Exception as e:                                   # openpyxl·양식 오류를 사용자 말로
        raise StartError(f"내역서를 읽지 못했습니다: {type(e).__name__}") from None
    if not lines:
        from .boq import diagnose
        reasons = diagnose(path)
        raise StartError("내역서를 읽을 수 없습니다 — " + " / ".join(reasons))
    blocks = sorted({ln.block for ln in lines if ln.block})
    disc = {ln.discipline for ln in lines}
    kind = "건축+토목" if {"건축", "토목"} <= disc else "토목" if disc == {"토목"} else "건축"
    cover = read_cover(path)
    cand = {"공사종류": kind}
    ks = ks_lines(lines)
    if cover.get("공사명"):
        cand["공사명"] = cover["공사명"]
    if cover.get("발주자"):
        cand["발주자"] = cover["발주자"]
        if PUBLIC_OWNER.search(cover["발주자"]):
            cand["발주자_구분"] = "발주청"
    if cover.get("총액"):
        cand["총공사비_억원"] = round(cover["총액"] / 1e8, 1)
    return {"blocks": blocks, "kind": kind, "lines": len(lines), "disciplines": sorted(disc), "cand": cand,
            "ks_lines": ks}


def ks_lines(lines) -> int:
    """KS 인증 여부로 계산이 갈리는 내역 행 수(KS 종별 묶음 규칙 — calc.plan_rows 의 non_ks 가 바꾸는 행)."""
    from .calc import match_rule
    from .paths import RULES_DIR
    from .rules import load_rules
    rules = {k: r for k, r in load_rules(RULES_DIR).items() if r.group_tests and r.ks_mark}
    return sum(1 for ln in lines if match_rule(ln, rules) is not None)


def read_lines(info: dict) -> list[str]:
    """'이렇게 읽었습니다' 화면 줄."""
    c = info.get("cand", {})
    cost = f"약 {c['총공사비_억원']:,}억원(도급 총계 — 관급자재가 빠졌을 수 있음)" if c.get("총공사비_억원") else "못 찾음"
    return [f"  동(블록)  : {', '.join(info['blocks']) or '(동 구분 없음)'}",
            f"  분야      : {'·'.join(info.get('disciplines', []))}",
            f"  공사명    : {c.get('공사명', '못 찾음')}",
            f"  총액      : {cost}",
            f"  발주자    : {c.get('발주자', '못 찾음')}",
            f"  내역 행   : {info['lines']:,}행"]


# ── 질문 ──────────────────────────────────────────────────────────────

def load_questions(path: Path = INTERVIEW) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]


def load_site_check(path: Path = INTERVIEW) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["site_check"]


class Interview:
    """질문을 차례로 묻고 답(ans)을 모은다. io = 대화형/한 줄/답 파일."""

    def __init__(self, *, mode: str = "tty", answers: dict | None = None, folder: Path | None = None,
                 yes: bool = False, out=None, inp=None):
        self.mode, self.given, self.yes = mode, dict(answers or {}), yes
        self.folder = folder or Path.cwd()
        self.out = out or sys.stdout
        self.inp = inp or sys.stdin
        self.replay = False                                  # --input: 답 목록 파일을 처음부터 다시 돌리는 중계(초안 없음)
        self.ans: dict = {}
        self.info: dict = {}
        self.asked = self.confirmed = 0                      # 물은 질문·확인만 한 값 수(끝 문구)
        self.scan = scan_folder(self.folder)
        self.questions = load_questions()

    # 출력·입력
    def say(self, text: str = ""):
        print(text, file=self.out, flush=True)

    def read(self) -> str:
        line = self.inp.readline()
        if line == "" and self.replay:
            raise StartError("입력이 끝났습니다 — 위 질문의 답을 답 목록 파일(--input)에 한 줄 더해 다시 실행하세요.")
        if line == "":
            raise StartError("입력이 끝났습니다(중간 답은 초안에 저장됨 — 다시 실행하면 이어서 합니다).")
        return line.rstrip("\n")

    # 조건·기본값
    def when(self, name: str | None, q: dict | None = None) -> bool:
        a = self.ans
        if not name:
            return True
        if name == "decides":                            # 이 답에 따라 계획 종류·배치 등급이 달라질 때만 묻는다
            return decides(a, q["key"], tuple(q.get("decide_values") or ("예", "아니오")))
        if name == "several_blocks":
            return len(self.info.get("blocks", [])) > 1
        if name == "owner_is_lh":
            return bool(re.search(r"LH|한국토지주택공사", str(a.get("발주자") or "")))
        if name == "ks_materials":                       # 내역서에 KS 여부로 계산이 갈리는 자재가 있을 때만
            return self.info.get("ks_lines", 1) > 0
        if name == "fill_now":                           # 사람·회사 칸: 지금 적기를 골랐거나 답 파일 모드
            return self.mode == "answers" or a.get("사람_회사_지금") == "지금"
        raise ValueError(f"알 수 없는 조건: {name}")

    def default(self, q: dict):
        src = q.get("default_from")
        if src == "boq_kind":
            return self.info.get("kind")
        if src == "judged_grade":
            g = judge(self.ans)["품질관리_대상등급"]
            return g if g in GRADES else None
        if src == "boq_title":
            return None
        if q.get("key") == "내역서" and self.scan["boq"]:
            return str(self.scan["boq"][0])
        return q.get("default")

    def choices(self, q: dict) -> list[dict]:
        if q.get("choices_from") == "blocks":
            return [{"value": "전체", "label": "전체(모든 동)"}] + [{"value": b, "label": b} for b in self.info["blocks"]]
        return q.get("choices") or []

    # 한 질문
    def ask(self, q: dict, n: int, total: int):
        key, kind = q["key"], q["type"]
        chs, dflt = self.choices(q), self.default(q)
        cand = self.info.get("cand", {}).get(q.get("from_boq")) if q.get("from_boq") else None
        if cand not in (None, "") and self.mode != "answers":
            shown = next((c["label"] for c in chs if c["value"] == cand), cand)
            note = ""
            if key == "총공사비_억원":
                shown, note = f"{cand:,}억원", " 도급 총계라 관급자재가 빠졌을 수 있습니다."
            if self.mode == "plain":
                self.say(f"Q{q['id']} {key} | 내역서에서 '{shown}'(으)로 읽었습니다.{note} 맞나요? | Y=맞음 n=고치기 | 기본=Y")
            else:
                self.say(f"\n[{q['id']}] 내역서에서 '{shown}'(으)로 읽었습니다.{note} 맞나요? [Y/n]")
                self.out.write("> ")
                self.out.flush()
            if self.read().strip().lower() not in ("n", "no", "아니오"):
                self.confirmed += 1
                return cand
            dflt = cand                                  # 고치기: 읽은 값을 기본값으로 두고 원래 질문을 묻는다
        if cand not in (None, "") and self.mode == "answers" and self.given.get(key) in (None, ""):
            return cand                                  # 답 파일에 없으면 내역서에서 읽은 값
        if self.mode != "answers":
            self.asked += 1
        if self.mode == "answers":
            v = self.given.get(key)
            if isinstance(v, bool) and kind == "choice":        # yaml 의 yes/no·true/false
                v = "예" if v else "아니오"
            if v in (None, ""):
                if dflt is None and self.yes and any(c["value"] == "모름" for c in chs):
                    dflt = "모름"
                if dflt is not None and (self.yes or q.get("optional") or kind == "choice"):
                    v = dflt
                elif q.get("optional"):
                    return None
                else:
                    raise StartError(f"답 파일에 '{key}' 가 없습니다({q['text']})")
            return self.parse(q, chs, str(v) if not isinstance(v, list) else v, dflt)
        while True:
            self.prompt(q, chs, dflt, n, total)
            raw = self.read().strip()
            if raw == "?":
                self.say(f"  도움말: {q.get('help') or '—'}")
                continue
            if kind == "files":
                return self.collect_files(q, raw)
            try:
                return self.parse(q, chs, raw, dflt)
            except StartError as e:
                self.say(f"  {e} 다시 입력하세요.")

    def prompt(self, q, chs, dflt, n, total):
        dlabel = next((c["label"] for c in chs if c["value"] == dflt), dflt)
        if self.mode == "plain":
            opts = " ".join(f"{i}={c['label']}" for i, c in enumerate(chs, 1))
            if q["type"] == "file" and q["key"] == "내역서" and self.scan["boq"]:
                opts = " ".join(f"{i}={f.name}" for i, f in enumerate(self.scan["boq"], 1))
            if q["type"] == "file" and q["key"] == "로고" and self.scan["logo"]:
                opts = " ".join(f"{i}={f.name}" for i, f in enumerate(self.scan["logo"], 1))
            self.say(f"Q{q['id']} {q['key']} | {q['text']}" + (f" | {opts}" if opts else "") +
                     (f" | 기본={Path(str(dlabel)).name if q['type'] == 'file' else dlabel}" if dlabel not in (None, "") else ""))
            return
        self.say(f"\n[{q['id']}] {q['text']}")                  # 질문 번호(판정 화면에서 '고칠 질문 번호'로 씀)
        if q["type"] == "file":
            cands = self.scan["boq"] if q["key"] == "내역서" else self.scan["logo"] if q["key"] == "로고" else []
            for i, f in enumerate(cands, 1):
                self.say(f"  {i}) {f.name}")
        for i, c in enumerate(chs, 1):
            self.say(f"  {i}) {c['label']}")
        tail = []
        if dlabel not in (None, ""):
            tail.append(f"Enter = {Path(str(dlabel)).name if q['type'] == 'file' else dlabel}")
        tail += ["? = 도움말", "- = 모름·건너뛰기"]
        self.say("  (" + ", ".join(tail) + ")")
        self.out.write("> ")
        self.out.flush()

    def parse(self, q, chs, raw, dflt):
        kind = q["type"]
        if kind == "site":                                   # 현장 확인: 번호·넣기/빼기/나중에
            return _site_value(raw)
        if kind == "files":
            return self.check_files(q, raw if isinstance(raw, list) else [raw])
        if raw in ("", None):
            if dflt not in (None, ""):
                raw = str(dflt)
            elif q.get("optional"):
                return None
            else:
                raise StartError("답이 필요합니다.")
        if raw == "-":
            if kind == "choice" and any(c["value"] == "모름" for c in chs):
                return "모름"
            if q.get("optional") or kind in ("number", "text"):
                return None
            raise StartError("이 질문은 건너뛸 수 없습니다.")
        if kind == "choice":
            if raw.isdigit() and 1 <= int(raw) <= len(chs):
                return chs[int(raw) - 1]["value"]
            for c in chs:
                if raw in (c["value"], c["label"]):
                    return c["value"]
            raise StartError("목록의 번호로 고르세요.")
        if kind == "yesno":
            if raw.lower() in ("y", "yes", "예", "네", "ㅇ"):
                return "예"
            if raw.lower() in ("n", "no", "아니오", "아니요"):
                return "아니오"
            raise StartError("Y 또는 n 으로 답하세요.")
        if kind == "number":
            v = number(raw)
            if v is None:
                raise StartError("숫자로 적으세요(예: 850).")
            return f"{v:,.0f}{q.get('unit', '')}" if q.get("unit") else (int(v) if v == int(v) else v)
        if kind == "file":
            cands = self.scan["boq"] if q["key"] == "내역서" else self.scan["logo"] if q["key"] == "로고" else []
            p = Path(str(cands[int(raw) - 1])) if raw.isdigit() and 1 <= int(raw) <= len(cands) else Path(clean_path(raw))
            if not p.is_file():
                raise StartError("그 파일을 찾을 수 없습니다.")
            if q["key"] == "내역서" and p.suffix.lower() in (".hwp", ".hwpx", ".pdf"):
                raise StartError("그 파일은 계획서입니다. 새로 만들기에는 도급내역서(.xlsx)가 필요합니다. "
                                 f"가진 계획서의 기준이 현행인지 보려면: danburn check \"{p}\"")
            if q["key"] == "내역서" and p.suffix.lower() == ".xls":
                from .boq import diagnose
                raise StartError("내역서를 읽을 수 없습니다 — " + " / ".join(diagnose(p)))
            if p.suffix.lower() not in q.get("exts", [p.suffix.lower()]):
                raise StartError(f"{'·'.join(q['exts'])} 파일이어야 합니다.")
            if q["key"] == "로고" and tracked_in_repo(p):
                raise StartError("저장소 안의 추적되는 파일은 쓰지 않습니다(커밋될 수 있음). 저장소 밖 파일을 고르세요.")
            if q["key"] == "내역서":
                self.info = read_boq_info(str(p))
            return str(p.resolve())
        return raw

    def check_files(self, q, raws) -> list[str]:
        out = []
        for r in raws:
            p = Path(clean_path(str(r)))
            if not p.is_file() or p.suffix.lower() not in q["exts"]:
                raise StartError("첨부 파일을 찾을 수 없거나 형식(PDF·PNG·JPEG)이 아닙니다.")
            if tracked_in_repo(p):
                raise StartError("저장소 안의 추적되는 곳에 있는 첨부는 받지 않습니다(커밋될 수 있음).")
            out.append(str(p.resolve()))
        return out

    def collect_files(self, q, first: str) -> list[str]:
        files, raw = [], first
        while raw not in ("", "-"):
            try:
                files += self.check_files(q, [raw])
                self.say(f"  첨부 {len(files)}건")                     # 이름·경로는 쓰지 않는다
            except StartError as e:
                self.say(f"  {e}")
            raw = self.read().strip()
        return files

    # 전체 흐름
    def run(self, draft: Path | None = None) -> dict:
        qs = self.questions
        start_at = 0
        if draft and draft.exists() and self.mode != "answers":
            saved = yaml.safe_load(draft.read_text(encoding="utf-8")) or {}
            self.say("지난번에 하던 인터뷰가 있습니다. 이어서 할까요? [Y/n]")
            if self.read().strip().lower() not in ("n", "no", "아니오"):
                self.ans = saved.get("answers", {})
                nxt = saved.get("next")
                start_at = len(qs) if nxt is None else next((i for i, q in enumerate(qs) if q["id"] == nxt), 0)
                if self.ans.get("내역서"):
                    self.info = read_boq_info(self.ans["내역서"])
        if self.mode == "tty" and self.scan["attach_count"]:
            self.say(f"이 폴더에서 자격·경력 증빙으로 보이는 파일 {self.scan['attach_count']}개를 찾았습니다(8번 질문에서 고를 수 있음).")
        asked = qs
        for i in range(start_at, len(asked)):
            q = asked[i]
            if not self.when(q.get("when"), q):
                continue
            v = self.ask(q, i + 1, len(asked))
            if v is not None:
                self.ans[q["key"]] = v
            else:
                self.ans.pop(q["key"], None)
            if q["key"] == "내역서" and self.info:
                if self.mode == "plain":
                    self.say("READ " + " | ".join(ln.strip().replace("  ", "") for ln in read_lines(self.info)))
                elif self.mode == "tty":
                    self.say("\n이렇게 읽었습니다")
                    for ln in read_lines(self.info):
                        self.say(ln)
            if draft and self.mode != "answers":
                draft.parent.mkdir(parents=True, exist_ok=True)
                nxt = asked[i + 1]["id"] if i + 1 < len(asked) else None
                draft.write_text(yaml.safe_dump({"answers": self.ans, "next": nxt}, allow_unicode=True), encoding="utf-8")
        if self.mode == "tty" and self.info:
            self.say(f"\n내역서를 읽고 {self.confirmed}가지는 확인만, 모호한 {max(self.asked - 1, 0)}가지만 여쭤봤습니다.")
        elif self.mode == "plain" and self.info:
            self.say(f"ASKED {max(self.asked - 1, 0)} CONFIRMED {self.confirmed}")
        return self.ans

    def redo(self, qid: str):
        q = next((q for q in self.questions if q["id"] == qid), None)
        if q is None:
            self.say("  그런 질문 번호가 없습니다.")
            return
        v = self.ask(q, 0, 0)
        if v is None:
            self.ans.pop(q["key"], None)
        else:
            self.ans[q["key"]] = v


# ── 현장 확인(요약 ask 목록, L7-I2 · 엔진 L7-E7) ───────────────────────────

SITE_ANSWER = {"1": "예", "넣기": "예", "예": "예", "y": "예", "2": "아니오", "빼기": "아니오", "아니오": "아니오",
               "n": "아니오", "3": None, "나중에": None, "모름": None, "-": None, "": None}


def _site_value(raw) -> str | None:
    """넣기/빼기/나중에 답 → '예'·'아니오'·None(나중에). 모르는 답은 StartError."""
    key = str(raw if raw is not None else "").strip()
    if key.lower() in SITE_ANSWER:
        return SITE_ANSWER[key.lower()]
    if key in SITE_ANSWER:
        return SITE_ANSWER[key]
    raise StartError("1(넣기)·2(빼기)·3(나중에) 중에서 고르세요.")


RULE_KEY = re.compile(r"[a-z][a-z0-9_]*")


def site_answers(given) -> dict[str, str]:
    """답 파일의 현장_확인 {key: 넣기/예/1|빼기/아니오/2|나중에} → {key: 예|아니오}(나중에는 뺀다).
    'name:<품명>' 키는 종별 key(예: steel_fiber — 그 규칙으로 넣기)도 받는다(엔진 L7-E8)."""
    if not isinstance(given, dict):
        return {}
    out = {}
    for k, v in given.items():
        if str(k).startswith("name:") and RULE_KEY.fullmatch(str(v).strip()) and str(v).strip() not in ("y", "n"):
            out[str(k)] = str(v).strip()
            continue
        val = _site_value(v)
        if val:
            out[str(k)] = val
    return out


def ask_site_checks(iv: "Interview", items: list[dict]) -> dict[str, str]:
    """ask 목록을 묻고 {key: 예|아니오} 를 돌려준다(나중에는 빼고). 답 파일 모드는 묻지 않는다."""
    cfg = load_site_check()
    items = [it for it in items if it.get("key")]
    if iv.mode == "answers" or not items:                  # 답 파일의 현장_확인은 첫 계획서 전에 이미 넣었다
        return {}
        return {}
    iv.say("\n" + cfg["intro"].format(n=len(items)) if iv.mode != "plain" else f"SITE {len(items)}")
    groups: dict[str, list[dict]] = {}
    for it in items:
        g = it.get("discipline") or it.get("분야") or cfg["group_names"].get(it.get("kind"), it.get("kind") or "기타")
        groups.setdefault(g, []).append(it)
    out: dict[str, str] = {}
    for name, its in groups.items():
        if len(items) > cfg["many"]:
            q = {"id": "확인", "key": name, "type": "choice", "text": cfg["group"].format(group=name, n=len(its)),
                 "choices": cfg["group_choices"], "default": "each"}
            if iv.ask(q, 0, 0) == "later":
                continue
        for it in its:
            if it.get("kind") == "name_unknown":
                v = _ask_name_unknown(iv, it, cfg)
                if v:
                    out[it["key"]] = v
                continue
            ex = ", ".join(str(x) for x in (it.get("examples") or [])[:3]) or "—"
            text = cfg["question"].get(it.get("kind"), cfg["question"]["rule_miss"]).format(
                label=it.get("label", it["key"]), lines=it.get("lines", "?"), examples=ex)
            q = {"id": "확인", "key": it["key"], "type": "site", "text": text, "choices": cfg["choices"],
                 "default": cfg["default"], "help": cfg["help"].format(rule=it.get("rule") or it.get("label", it["key"]))}
            v = iv.ask(q, 0, 0)
            if v:
                out[it["key"]] = v
    return out


def _ask_name_unknown(iv: "Interview", it: dict, cfg: dict) -> str | None:
    """품명으로 자재를 알 수 없는 행: 1) <추정 규칙>으로 넣기(있을 때) 2) 시험 대상 자재(발주처 기준 필요) 3) 자재 아님
    4) 나중에. 답은 종별 key·'예'·'아니오', 나중에는 None."""
    given = it.get("choices") or {}
    words = cfg["name_unknown_choices"]
    rules = [k for k in given if k not in ("예", "아니오", "나중에") and RULE_KEY.fullmatch(k)]
    chs = [{"value": k, "label": str(given[k])} for k in rules] + \
          [{"value": k, "label": words[k]} for k in ("예", "아니오", "나중에")]
    text = cfg["question"]["name_unknown"].format(label=it.get("label", it["key"][5:]), lines=it.get("lines", "?"),
                                                    spec_word=it.get("spec_word") or "—")
    q = {"id": "확인", "key": it["key"], "type": "choice", "text": text, "choices": chs, "default": "나중에",
         "optional": True, "help": cfg["help"].format(rule=" / ".join(str(given[k]) for k in rules) or "—")}
    v = iv.ask(q, 0, 0)
    return None if v in (None, "나중에") else v


# ── 판정 화면·project.yaml ─────────────────────────────────────────────

def judgment_lines(r: dict) -> list[str]:
    lines = [f"  계획 종류   : {r['계획종류']}" + ("" if r["계획종류_확정"] else "  (확인 필요)"),
             f"  근거 조문   : {r['작성근거']}",
             f"  배치 등급   : {r['품질관리_대상등급']}",
             f"  시험실 규모 : {r['시험실']}",
             f"  인력 기준   : {r['인력기준']}",
             f"  승인 절차   : {r['승인절차_문장']}"]
    for n in r["확인필요"]:
        lines.append(f"  ! 확인 필요: {n}")
    return lines


def build_project(ans: dict, r: dict, today: str, base_path: Path = EXAMPLE) -> tuple[dict, list[str]]:
    """답 + 판정 → project dict. 두 번째 값은 '(작성 필요)'로 남긴 항목 이름."""
    p = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    p = copy.deepcopy(p)
    todo = []

    def put(key, value, label=None):
        if value in (None, ""):
            p[key] = TODO
            todo.append(label or key)
        else:
            p[key] = value
    for k in ("공사명", "공사위치", "공사기간", "시공자", "발주자", "현장대리인"):
        put(k, ans.get(k))
    cost = number(ans.get("총공사비_억원"))
    put("공사금액", f"약 {cost:,.0f}억원(관급자재 포함·보상비 제외)" if cost is not None else None)
    for k in ("건설사업관리자", "계약특이사항", "문서번호"):
        put(k, None)
    p["주요공종"] = str(ans.get("공사종류") or TODO)
    for k in ("대지면적", "건축면적", "구조", "설계자"):          # 예시 값은 지운다(비우면 공사개요에서 줄을 뺌)
        p.pop(k, None)
    p["연면적"] = ans.get("연면적") or ""
    fl = number(ans.get("지상층수"))
    p["규모"] = f"지상 최고 {fl:.0f}층" if fl is not None else ""
    p.pop("시험장비", None)
    p["회사명"] = ans.get("시공자") or ""
    p["로고"] = ans.get("로고") or ""
    p["문서명"] = ""                                               # 비우면 "품질관리계획서"
    qm, grade = ans.get("품질관리자"), ans.get("품질관리자_등급")
    if qm:
        p["품질관리자"] = [{"직무": "품질관리자", "성명": qm, "등급": grade or TODO, "배치기간": TODO, "비고": ""}]
    else:
        p["품질관리자"] = TODO
        todo.append("품질관리자")
    p["품질관리자_등급"] = grade or TODO
    rep = ans.get("현장대리인") or TODO
    p["조직"] = [{"직무": "현장대리인", "성명": rep, "자격": TODO, "담당": "현장 총괄, 품질방침 수립"},
                {"직무": "품질관리자", "성명": qm or TODO, "자격": TODO, "담당": "품질시험·검사, 내부심사 주관"}]
    p["결재"] = [{"구분": "작성", "직책": "품질관리자", "성명": qm or TODO},
                {"구분": "승인", "직책": "현장대리인", "성명": rep}]
    p["제정일자"] = today
    p["개정이력"] = [{"개정": 0, "일자": today, "장": ["전체"], "사유": "최초 제정"}]
    for k in ("발주자_구분", "공사종류", "총공사비_억원", "지상층수", "건설사업관리_대상", "계약_품질관리계획", "주용도"):
        if ans.get(k) not in (None, ""):
            p[k] = ans[k]
    for k in ("작성근거", "승인절차_문장", "품질관리_대상등급", "시험실"):   # 템플릿 치환용 최상위 키(L7-C5)
        p[k] = r[k]
    if r["계획종류"] == "품질시험계획":
        p["문서명"] = "품질시험계획서"                              # 표지 제목·쪽 머리(본문 구성은 그대로 — 확인필요에 적힘)
    p["판정"] = {k: r[k] for k in ("계획종류", "작성근거", "품질관리_대상등급", "시험실", "인력기준", "승인절차_문장", "확인필요")}
    p["내역서"] = {"경로": ans.get("내역서"), "블록": ans.get("블록") or "전체"}
    if ans.get("발주처기준") == "예":
        p["발주처기준"] = "LH"
    files = ans.get("첨부") or []
    p["첨부"] = {"방식": "목록만", "파일": files}
    p["첨부_개수"] = len(files)
    p["KS_인증"] = ans.get("KS_인증") or "모름"                   # plan 이 읽는다: 아니오 = 비KS 계산, 모름 = KS 로 계산 + 경고
    return p, todo


def plan_args(p: dict, project_path: Path, out: Path, today: str, *, offline: bool) -> list[str]:
    args = ["plan", "--boq", p["내역서"]["경로"], "--project", str(project_path), "--revision", "0",
            "--date", today, "--out", str(out)]
    if p["내역서"].get("블록") and p["내역서"]["블록"] != "전체":
        args += ["--block", p["내역서"]["블록"]]
    if p.get("발주처기준"):
        args += ["--owner", p["발주처기준"]]
    if offline:
        args.append("--offline")
    return args


def run_plan(args: list[str]) -> tuple[int, dict | None, str]:
    """cli plan 을 같은 프로세스에서 돌려 (종료 코드, 요약, 오류 글)을 돌려준다."""
    from . import cli
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        rc = cli.main(args)
    try:
        summary = json.loads(buf.getvalue()) if buf.getvalue().strip() else None
    except json.JSONDecodeError:
        summary = None
    return rc, summary, err.getvalue()


def today_text() -> str:
    d = dt.date.today()
    return f"{d.year}. {d.month:02d}. {d.day:02d}."


def _answer_lines(path: str):
    """--input 답 목록 파일(한 줄에 답 하나) → 줄 스트림. UTF-8(BOM 포함) 우선, 안 되면 cp949(한국어 Windows 메모장)."""
    import io
    p = Path(clean_path(path))
    if not p.is_file():
        raise StartError(f"답 목록 파일이 없습니다: {p} — --input 경로를 확인하세요(처음엔 빈 파일을 만들어 주면 됩니다).")
    raw = p.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp949", errors="replace")
    return io.StringIO(text.replace("\r\n", "\n").replace("\r", "\n"))


def main(a) -> int:
    """cli 의 `start` 하위 명령 본체."""
    out = sys.stdout
    try:
        if a.answers:
            from .cli import InputError, read_yaml
            try:
                given = read_yaml(a.answers, "답(--answers)", "--answers")
            except InputError as e:
                raise StartError(str(e)) from None
            iv = Interview(mode="answers", answers=given, folder=Path(a.folder), yes=a.yes)
        elif getattr(a, "input", None):
            iv = Interview(mode="plain", folder=Path(a.folder), inp=_answer_lines(a.input))
            iv.replay = True
        else:
            iv = Interview(mode="plain" if a.plain else "tty", folder=Path(a.folder))
            if not a.plain:
                iv.say("danburn start — 도급내역서를 먼저 읽고, 정해지지 않았거나 모호한 것만 여쭙니다. "
                       "사람·회사 칸은 나중에 적어도 됩니다. "
                       "(Enter = 기본값, ? = 도움말, - = 모름, 중간에 멈춰도 이어서 할 수 있습니다)")
        # --input 은 답 목록 전체를 매번 다시 돌리는 중계라서 이어 하기 초안을 읽지도 쓰지도 않는다
        draft = None if getattr(a, "input", None) else home_dir() / "start-draft.yaml"
        ans = iv.run(draft=draft)
        today = today_text()
        while True:
            r = judge(ans)
            iv.say("\n판정 — 이 현장의 계획 종류와 기준" if iv.mode != "plain" else "JUDGE")
            for line in judgment_lines(r):
                iv.say(line)
            if iv.mode == "answers":
                break
            iv.say("맞나요? [Y/n]  (n = 답 고치기)")
            if iv.read().strip().lower() not in ("n", "no", "아니오"):
                break
            iv.say("고칠 질문 번호를 적으세요(예: 4-1, 5-2):")
            iv.redo(iv.read().strip())
        if not ans.get("공사명"):
            raise StartError("공사명이 필요합니다(산출 폴더 이름에 씀).")
        out_dir = Path(a.out_dir).expanduser() if a.out_dir else default_out_dir(str(ans["공사명"]))
        repo = tracked_in_repo(out_dir)
        if repo:
            raise StartError("산출 폴더가 git 저장소 안의 추적되는 곳입니다(현장 정보가 커밋될 수 있음). "
                             "저장소 밖 폴더를 주거나 저장소 안이면 danburn-out/ 아래를 쓰세요.")
        out_dir.mkdir(parents=True, exist_ok=True)
        project, todo = build_project(ans, r, today)
        if iv.mode == "answers" and site_answers(iv.given.get("현장_확인")):
            project["현장_확인"] = site_answers(iv.given.get("현장_확인"))
        proj_path = out_dir / "project.yaml"
        proj_path.write_text("# danburn start 로 만든 현장 정보(직접 고쳐도 됩니다). 첨부는 경로만 적습니다.\n"
                             + yaml.safe_dump(project, allow_unicode=True, sort_keys=False), encoding="utf-8")
        iv.say(f"\n현장 정보 저장: {proj_path}")
        if draft and draft.exists():
            draft.unlink()
        if a.no_plan:
            return 0
        if iv.mode != "answers":
            iv.say("지금 계획서를 만들까요? [Y/n]")
            if iv.read().strip().lower() in ("n", "no", "아니오"):
                iv.say(f"나중에: danburn plan … --project {proj_path}")
                return 0
        hwpx = out_dir / f"{'품질시험계획서' if r['계획종류'] == '품질시험계획' else '품질관리계획서'}.hwpx"   # 같은 이름 .json 도 생김
        rc, summary, err = run_plan(plan_args(project, proj_path, hwpx, today, offline=a.offline))
        if rc != 0 or summary is None:
            iv.say(f"계획서를 만들지 못했습니다(종료 {rc}). {err.strip()[:300]}")
            return rc or 2
        # 현장 확인: 요약 ask 목록을 묻고, 넣기·빼기가 있으면 project.yaml 에 적고 다시 만든다
        prev = dict(project.get("현장_확인") or {})
        todo_ask = [it for it in summary.get("ask") or [] if it.get("key") not in prev]
        site = ask_site_checks(iv, todo_ask)
        if site:
            project["현장_확인"] = {**prev, **site}
            proj_path.write_text("# danburn start 로 만든 현장 정보(직접 고쳐도 됩니다). 첨부는 경로만 적습니다.\n"
                                 + yaml.safe_dump(project, allow_unicode=True, sort_keys=False), encoding="utf-8")
            iv.say(load_site_check()["rerun"] if iv.mode != "plain" else "RERUN")
            rc, summary, err = run_plan(plan_args(project, proj_path, hwpx, today, offline=a.offline))
            if rc != 0 or summary is None:
                iv.say(f"계획서를 다시 만들지 못했습니다(종료 {rc}). {err.strip()[:300]}")
                return rc or 2
        left = [it for it in summary.get("ask") or [] if it.get("key") not in (project.get("현장_확인") or {})]
        summary["start"] = {"판정": {k: r[k] for k in ("계획종류", "품질관리_대상등급", "확인필요")},
                            "작성필요": todo, "첨부_개수": len(ans.get("첨부") or []),   # 첨부는 개수만
                            "현장_확인": project.get("현장_확인") or {}, "현장_확인_남음": len(left)}
        (out_dir / "요약.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        iv.say(f"\n계획서: {hwpx}")
        iv.say(f"요약  : {out_dir / '요약.json'}")
        iv.say(f"시험계획서만 따로(엑셀 포함): danburn test-plan --project \"{proj_path}\"")
        iv.say("\n확인할 것")
        n = 0
        for item in r["확인필요"]:
            n += 1
            iv.say(f"  {n}. 판정: {item}")
        for w in summary.get("warnings", []):
            n += 1
            iv.say(f"  {n}. {w}")
        if left:
            n += 1
            iv.say(f"  {n}. " + load_site_check()["later_left"].format(n=len(left)))
        if todo:
            n += 1
            iv.say(f"  {n}. (작성 필요)로 남긴 칸: {', '.join(todo)}")
        n += 1
        iv.say(f"  {n}. 더 고칠 곳: {EDIT_LATER}")
        if ans.get("첨부"):
            n += 1
            iv.say(f"  {n}. 증빙 첨부 {len(ans['첨부'])}건 — 계획서에는 넣지 않았습니다. 제출할 때 따로 묶으세요.")
        n += 1
        iv.say(f"  {n}. 한글로 열어 README '한컴에서 확인하기' 목록 확인")
        return 0
    except StartError as e:
        print(f"멈춤: {e}", file=out)
        return 2
