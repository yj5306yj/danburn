"""품질관리계획서 한 권(HWPX)을 조립한다: 표지 → A 목차 → B 승인 및 개정이력 → 1~10장(별표1 순서).

전부 A4 세로(원본 현장 계획서와 같음). 쪽 머리가 바뀌는 단위마다 구역을 하나씩 둔다 —
원본처럼 표지 / A / B / (절 없는 장 1~3 묶음) / 절마다(4.1, 4.2 …) 각각 쪽 머리
"문서명 / 절 제목 + 개정일자 [Rev.N] Np."를 달고 쪽 번호는 구역마다 1부터 다시 센다.
모양 수치(표지 배치, 목차·이력 표 열, 절 개요 칸, 본문 글자·줄 간격·들여쓰기)의 기준은
docs/design/plan-layout.md — 정본 현장 계획서를 재어 얻은 값이며 아래 상수와 1:1로 맞춘다.
절 구역은 첫머리에 정본과 같은 절 개요 칸(목적·적용범위·적용기준·관련문서·첨부(양식))을 두고,
8.11 절은 그 뒤 새 쪽에서 hwpx_out.add_811_tables 로 같은 구역에 표를 채운다.

본문은 data/templates/qplan.yaml(자체 작성 템플릿)의 자리표시 {키}를 project 입력으로 채운다.
주의: add_heading 은 뒤 문단에 개요 번호를 물려준다(루프 0 교훈) → 제목도 일반 문단 + 글자 모양으로 쓴다.
"""
from __future__ import annotations

import re
import struct
import zipfile
from pathlib import Path

import yaml
from hwpx import HwpxDocument
from lxml import etree

from . import hwpx_out, plan_parts
from .hwpx_out import HP, LINE_OUTER, LINE_THIN, NOTICE, PAGE, add_811_tables, compact_date, grid_table, hold
from .model import PlanRow

DEFAULT_TEMPLATE = Path(__file__).resolve().parents[2] / "data" / "templates" / "qplan.yaml"
MARK_811 = "{8.11}"
_PH = re.compile(r"\{([^{}]+)\}")
_MM = 7200 / 25.4                               # mm → HWPUNIT
BODY_MM = 210 - PAGE["margin_left_mm"] - PAGE["margin_right_mm"]   # 세로 A4 본문폭(8.11과 같은 여백)
BODY_TOP_MM = PAGE["margin_top_mm"] + PAGE["header_margin_mm"]    # 본문 시작 37.5
LAND_BODY_MM = 297 - PAGE["margin_left_mm"] - PAGE["margin_right_mm"]   # 가로 A4 본문폭(가로 양식 쪽)
BODY_END_MM = 277.6                             # 정본 쪽을 채우는 표(목차)의 아래 선
DOC_TITLE = "품질관리계획서"                     # 표지 제목·쪽 머리 첫 줄 기본값(project.문서명 으로 바꿀 수 있다)
# danburn start 판정 결과 치환 키(템플릿 L7-C5). 없으면 기본 문장(판정 전)으로 채우고 요약에 알린다
JUDGED_KEYS = ("작성근거", "승인절차_문장", "품질관리_대상등급", "시험실")
PRE_JUDGE_MARK = "확인 필요(danburn start"
JUDGED_DEFAULTS = {
    "승인절차_문장": "본 계획서는 착공 전에 공사감독자 또는 건설사업관리기술인의 검토·확인을 받아 발주자의 승인을 받으며, "
                "내용을 변경할 때도 같다(「건설기술 진흥법 시행령」 제90조제1항).",
    "품질관리_대상등급": "확인 필요(danburn start 로 판정)",
    "시험실": "확인 필요(danburn start 로 판정)",
}
PRE_JUDGE_NOTE = "판정 전 — 승인 절차·배치 등급·시험실 규모를 기본 문장으로 작성함(danburn start 로 판정 권장)"

# ── 정본 실측(docs/design/plan-layout.md). 길이 mm, 글자 pt, 줄 간격 % ─────────────
# 표지 §2: 3칸(왼 여백 · 정보 상자 79.1 · 오른 여백) 행 높이로 자리를 고정한다(문단 쌓기는 뷰어마다 어긋난다)
COVER_COLS_MM = [51.5, 79.1, 50.4]
COVER_PT = dict(site=25, title=45.5, sub=18, info=12, company=16)
COVER_ROWS_MM = dict(top=57.0, site=15.2, gap1=13.8, title=22.0, sub=8.3, gap2=32.7, info=10.7, gap3=34.2,
                     logo=15.0, company=8.0)     # top = 공사명 줄 윗변(쪽 위에서)
COVER_INFO_PAD_MM = 4.4                        # 정보 상자 글 왼쪽 띄움
COVER_SUBTITLE = "Quality Management Plan"
# 목차 §3
TOC_COLS_MM = [14.9, 117.1, 22.5, 26.5]
TOC_HEAD_MM, TOC_ROW_MM, TOC_TOP_PAD_MM = 9.4, 4.87, 4.8
TOC_TITLE_PAD_MM, TOC_SECTION_INDENT_MM = 5.5, 3.5
TOC_PT = 10
# 승인 및 개정이력 §4
HIST_COLS_MM = [15.6, 19.6, 51.6, 73.7, 19.6]
HIST_HEAD_MM, HIST_ROW_MM, HIST_MIN_ROWS = 11.5, 10.0, 11
HIST_PT = 9
SIGN_TOP_MM = 202.3                            # 결재란 윗선(쪽 위에서)
SIGN_FIRST_COL_MM, SIGN_ROW_MM, SIGN_SIGN_ROW_MM = 30.1, 12.4, 22.7
SIGN_PT = 10
# 본문(장 쪽) §5: 글 10pt 220%(줄 간격 7.75), 들여쓰기는 본문 왼끝에서
BODY_PT, BODY_LINE = 10, 220
CHAPTER_PT, SUB_PT = 12, 11
INDENT_MM = dict(text=7.9, sub=5.3, item=6.9, item_hang=5.3, subitem=12.2, subitem_hang=7.1)
CHAPTER_BEFORE_FIRST_MM, CHAPTER_BEFORE_MM, CHAPTER_AFTER_MM = 5.4, 7.75, 4.2
SUB_BEFORE_MM, SUB_AFTER_MM = 7.85, 1.9
SECTION_HEAD_AFTER_MM = 2.2                    # 흐름표 뒤 새 쪽 본문 제목 아래(정본 4.1 공사개요 표 윗선 45.5~45.8)
# 절 개요 칸 §6: 2칸(이름 29.3 · 내용), 칸마다 최소 높이, 칸 사이 3.0
BOX_COLS_MM = [29.3, BODY_MM - 29.3]
BOX_LABELS = ["목 적", "적용범위", "적용기준", "관련문서", "첨부(양식)"]
BOX_MIN_MM = [20.5, 20.5, 76.0, 20.5, 20.5]
BOX_GAP_MM = 3.0
BOX_PT, BOX_LINE = 9, 167
BOX_PAD_MM = (1.7, 1.7, 1.5, 1.5)
BOX_NUM_HANG_MM = 4.8                          # "1. " 내어쓰기
# P7 공사개요 표(§16): 가운데로 들어간 폭 166.6(x 23.4 ~ 190.0), 항목 20.5 % · 값, 줄 13.2, 10pt 가운데
OVERVIEW_OFFSET_MM, OVERVIEW_W_MM, OVERVIEW_LABEL_PCT = 6.9, 166.6, 20.5
OVERVIEW_ROW_MM, OVERVIEW_PT = 13.2, 10
OVERVIEW_REQUIRED = ["공사명", "공사위치", "공사금액", "공사기간", "발주자", "시공자", "건설사업관리자",
                     "주요공종", "계약특이사항"]
# 정본 순서. 확장 키(대지면적 등)는 값이 없으면 줄을 뺀다
OVERVIEW_ORDER = ["공사명", "공사위치", "대지면적", "건축면적", "연면적", "규모", "구조", "공사기간", "공사금액",
                  "발주자", "설계자", "건설사업관리자", "시공자", "현장대리인", "주요공종", "계약특이사항"]
OVERVIEW_LABEL = {"규모": "공사규모"}


class PlaceholderError(ValueError):
    """템플릿 자리표시를 채울 값이 없다."""


def load_template(path: str | Path = DEFAULT_TEMPLATE) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fill(text: str, values: dict) -> str:
    """{키}를 values 로 바꾼다. 없는 키가 있으면 PlaceholderError(빈칸 문서를 내지 않는다)."""
    missing = [k for k in _PH.findall(text) if k not in values]
    if missing:
        raise PlaceholderError(f"자리표시 값 없음: {missing} — 문장: {text[:40]}")
    return _PH.sub(lambda m: str(values[m.group(1)]), text)


def placeholders(template: dict) -> set[str]:
    """템플릿이 쓰는 자리표시 키 전부(특수 표지 {표:…}·{8.11} 제외)."""
    keys: set[str] = set()

    def walk(v):
        if isinstance(v, str):
            keys.update(k for k in _PH.findall(v) if not k.startswith("표:") and k != "8.11")
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(template)
    return keys


def toc_entries(template: dict) -> list[tuple[str, str, int]]:
    """(번호, 제목, 깊이) — 장은 0, 절은 1."""
    out = []
    for ch in template["chapters"]:
        out.append((ch["id"], ch["title"], 0))
        for s in ch.get("sections", []):
            out.append((s["id"], s["title"], 1))
    return out


def _date_key(d: str) -> tuple[int, ...]:
    """'2026. 06. 01.'·'2026-06-01'·'2026.6.1' 을 같은 값으로 본다."""
    return tuple(int(x) for x in re.findall(r"\d+", str(d)))


def _revisions(project: dict, revision: int | str, date: str) -> list[dict]:
    """개정이력을 현재 개정(revision 인자)에 맞춰 검사·보충한다. 문서의 현재 개정 = revision.

    - 이력에 revision 보다 큰 번호가 있으면 ValueError(표지와 쪽 머리가 서로 다른 개정을 말하게 된다)
    - 같은 번호가 있는데 일자가 date 와 다르면 ValueError
    - 없으면 revision·date 로 한 줄 추가
    """
    try:
        cur = int(revision)
    except (TypeError, ValueError):
        raise ValueError(f"revision 은 정수여야 합니다: {revision!r}") from None
    revs = [dict(r) for r in project.get("개정이력", [])]
    newer = sorted(int(r["개정"]) for r in revs if int(r["개정"]) > cur)
    if newer:
        raise ValueError(f"개정이력에 현재 개정(Rev.{cur})보다 큰 번호가 있습니다: "
                         f"{', '.join(f'Rev.{n}' for n in newer)} — --revision 을 올리거나 이력을 고치세요")
    same = [r for r in revs if int(r["개정"]) == cur]
    if same:
        if _date_key(same[0]["일자"]) != _date_key(date):
            raise ValueError(f"Rev.{cur} 의 개정이력 일자({same[0]['일자']})와 date 인자({date})가 다릅니다")
    else:
        first = cur == 0
        revs.append({"개정": cur, "일자": date, "장": ["전체"] if first else [],
                     "사유": "최초 제정" if first else ""})
    return sorted(revs, key=lambda r: int(r["개정"]))


def _last_rev(revs: list[dict], no: str) -> dict | None:
    """no(예: "8.11", "1")를 바꾼 가장 늦은 개정. "전체"·장 번호·절 번호가 맞으면 해당."""
    chapter = no.split(".")[0]
    hit = None
    for r in revs:
        chs = [str(c) for c in r.get("장", [])]
        if "전체" in chs or no in chs or chapter in chs or any(c.startswith(no + ".") for c in chs):
            hit = r
    return hit


def _image_size(data: bytes) -> tuple[int, int]:
    """PNG·JPEG 픽셀 크기(외부 의존성 없이 머리만 읽는다)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker, seg = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + seg
    raise ValueError("로고는 PNG 또는 JPEG 만 받습니다")


def _logo(project: dict) -> tuple[bytes, str] | None:
    """project.로고(로컬 경로)를 읽는다. 비어 있으면 None(칸만 둔다). 경로가 있는데 없으면 오류."""
    path = str(project.get("로고") or "").strip()
    if not path:
        return None
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"로고 파일이 없습니다: {p}")
    fmt = p.suffix.lower().lstrip(".")
    fmt = {"jpeg": "jpg"}.get(fmt, fmt)
    if fmt not in ("png", "jpg"):
        raise ValueError(f"로고는 PNG 또는 JPEG 만 받습니다: {p.name}")
    data = p.read_bytes()
    _image_size(data)
    return data, fmt



_ITEM = re.compile(r"^\d+\)\s")
_SUBITEM = re.compile(r"^\(\d+\)\s")
_SUBHEAD = re.compile(r"^\d+\.\d+\s")


def _est_mm(text: str, width_mm: float, pt: float, line_pct: float, pad_mm: float = 0) -> float:
    """글이 차지할 높이 추정(hwpx_out._text_height_mm 의 줄 수 × 이 줄 간격)."""
    lines = (hwpx_out._text_height_mm(text, width_mm - pad_mm + hwpx_out.CELL_PAD_MM[0] + hwpx_out.CELL_PAD_MM[1], pt)
             - hwpx_out.CELL_PAD_MM[2] - hwpx_out.CELL_PAD_MM[3]) / (pt * 25.4 / 72 * 1.3)
    return round(lines) * pt * 25.4 / 72 * line_pct / 100


class _Writer:
    def __init__(self, doc: HwpxDocument, notice_footer: bool = False):
        self.doc = doc
        self.notice_footer = notice_footer
        self.st = hwpx_out._Styles(doc)
        st = self.st
        self.sec = None
        self.prev = None                              # 직전 문단 종류(제목 간격 계산용)
        self.c_body = st.char(BODY_PT)
        self.c_ch = st.char(CHAPTER_PT, bold=True)
        self.c_sub = st.char(SUB_PT, bold=True)
        self.p_left = st.para("LEFT", 100)
        self.p_text = st.para("JUSTIFY", BODY_LINE, left=INDENT_MM["text"])
        # 내어쓰기: 왼쪽 여백 = 첫 줄 자리, 음수 들여쓰기 = 둘째 줄부터 더 들어가는 폭(한컴·rhwp 같은 해석)
        self.p_item = st.para("JUSTIFY", BODY_LINE, left=INDENT_MM["item"], indent=-INDENT_MM["item_hang"])
        self.p_subitem = st.para("JUSTIFY", BODY_LINE, left=INDENT_MM["subitem"], indent=-INDENT_MM["subitem_hang"])

    def raw(self, el):
        """본문에 문단을 붙인다. 구역의 첫 내용은 구역 설정을 담은 첫 문단에 합친다 — 따로 두면 그 빈 문단이
        한 줄(5.6mm)을 차지해 본문 시작이 정본(37.5)보다 내려간다."""
        if self.fresh:
            self.fresh = False
            first = self.sec.element.find(f"{HP}p")
            first.set("paraPrIDRef", el.get("paraPrIDRef"))
            first.set("pageBreak", el.get("pageBreak", "0"))
            for run in el.findall(f"{HP}run"):
                first.append(run)
        else:
            self.sec.element.append(el)
        self.sec.mark_dirty()

    def para(self, text: str = "", *, char=None, para=None, page_break=False):
        self.raw(hwpx_out._para(text, para or self.p_text, char or self.c_body, page_break=page_break))

    def table(self, tbl, *, page_break=False):
        self.raw(hold(tbl, self.p_left, self.c_body, page_break=page_break))
        self.prev = "table"

    def chapter(self, text: str, *, page_break: bool = False):
        """장 제목(12pt 굵게, 본문 왼끝). 쪽 첫 줄이면 위 5.4, 아니면 7.75 띄운다.

        쪽 첫 문단의 '문단 위' 간격은 뷰어가 버리므로(rhwp 실측) 쪽 첫 제목 앞은 그 높이의 빈 줄로 띄운다."""
        before = CHAPTER_BEFORE_MM
        if page_break:                            # 흐름표 뒤 본문 쪽: 제목이 쪽 윗줄(정본 37.0), 아래 표와 1.5
            self.para(text, char=self.c_ch, para=self.st.para("LEFT", 160, after=SECTION_HEAD_AFTER_MM),
                      page_break=True)
            self.prev = "chapter"
            return
        elif self.prev is None:
            self.para("", para=self.st.para("LEFT", round(CHAPTER_BEFORE_FIRST_MM / (BODY_PT * 25.4 / 72) * 100)))
            before = 0
        self.para(text, char=self.c_ch, para=self.st.para("LEFT", 160, before=before, after=CHAPTER_AFTER_MM))
        self.prev = "chapter"

    def body(self, text: str):
        """본문 한 줄. 모양은 글머리로 정한다: '2.1 …' 소제목, '1) …' 항목, '(1) …' 세부 항목, 그 밖 본문."""
        if _SUBHEAD.match(text):
            before = 0 if self.prev in (None, "chapter") else SUB_BEFORE_MM
            self.para(text, char=self.c_sub, para=self.st.para("LEFT", 160, left=INDENT_MM["sub"], before=before,
                                                               after=SUB_AFTER_MM))
            self.prev = "sub"
            return
        para = self.p_item if _ITEM.match(text) else self.p_subitem if _SUBITEM.match(text) else self.p_text
        self.para(text, para=para)
        self.prev = "body"

    def orient(self, landscape: bool):
        """방향이 바뀌면 같은 쪽 머리의 새 구역을 연다(가로 양식 쪽). 쪽 번호는 이어 센다(startNum 0, 새 번호 없음)."""
        if landscape == self.landscape:
            return
        self.sec = self.doc.add_section()
        self.prev, self.fresh, self.landscape = None, True, landscape
        self.doc.page.setup(section=self.sec, **PAGE)
        hwpx_out._set_orientation(self.sec, landscape)
        for sn in self.sec.element.iter(f"{HP}startNum"):
            sn.set("page", "0")
        self.sec.mark_dirty()
        self.frame(**self.frame_args, body_w_mm=LAND_BODY_MM if landscape else BODY_MM)

    def new_unit(self, *, first: bool = False):
        """쪽 머리 단위 하나 = 구역 하나. 세로 A4(8.11과 같은 여백), 쪽 번호 1부터."""
        self.sec = self.doc.sections[0] if first else self.doc.add_section()
        self.prev = None
        self.fresh = True
        self.landscape = False
        self.doc.page.setup(section=self.sec, **PAGE)
        pp = next(e for e in self.sec.element.iter() if e.tag.endswith("}pagePr"))
        pp.set("landscape", "WIDELY")                  # 스키마 값 세로(python-hwpx 의 "PORTRAIT" 쓰지 않음)
        pp.set("width", str(round(210 * _MM)))
        pp.set("height", str(round(297 * _MM)))
        for sn in self.sec.element.iter():
            if sn.tag.endswith("}startNum"):
                sn.set("page", "1")
        # 구역 시작 번호(startNum)만으로는 이어 세는 렌더러가 있어(rhwp 0.8.6) 새 번호 조판부호도 둔다.
        run = next(e for e in self.sec.element.iter() if e.tag == f"{HP}run")
        ctrl = etree.SubElement(run, f"{HP}ctrl")
        etree.SubElement(ctrl, f"{HP}newNum", num="1", numType="PAGE")
        self.sec.mark_dirty()
        return self.sec

    def frame(self, *, doc_title: str, title: str, revision: str, date: str, header: bool = True,
              logo: str | None = None, company: str = "", body_w_mm: float = BODY_MM):
        """쪽 머리(hwpx_out.page_header — 로고·회사명 칸 포함)와 꼬리말(공개 문서 고지)을 단다."""
        self.frame_args = dict(doc_title=doc_title, title=title, revision=revision, date=date, header=header,
                               logo=logo, company=company)
        if header:
            hwpx_out.page_header(self.doc, self.sec, doc_title=doc_title, title=title, revision=revision,
                                 date=date, logo=logo, company=company, body_w_mm=body_w_mm)
        if self.notice_footer:                      # 고지 줄은 켰을 때만(hwpx_out.NOTICE 설명)
            self.doc.page.set_footer(text=" ", section=self.sec)
            hwpx_out._fill_story(self.sec, "footer", [hwpx_out._para(
                NOTICE, self.st.para("CENTER", 100), self.st.char(hwpx_out.PT["footer"]))])


def _box(o=LINE_OUTER, i=LINE_THIN, *, left=True, right=True, top=True, bottom=True):
    """(좌, 우, 위, 아래) 선: 바깥이면 o, 아니면 i."""
    return (o if left else i, o if right else i, o if top else i, o if bottom else i)


def _simple_table(w: _Writer, rows: list[list[str]], widths_mm: list[float], *, pt: float = 9,
                  head_mm: float = 8.0, row_mm: float = 7.0, left_cols=()):
    """{표:…} 자료 표: 머리 1행(굵게, 쪽마다 반복) + 자료 행. 바깥 0.4 · 안 0.12."""
    widths = [x * BODY_MM / sum(widths_mm) for x in widths_mm]
    n, m = len(rows), len(widths)
    heights = [head_mm] + [max(row_mm, max(_est_mm(str(v), widths[c], pt, 120, 1.0) + 1.0 for c, v in enumerate(r)))
                           for r in rows[1:]]
    cells = [dict(r=r, c=c, text=str(v), pt=pt, bold=r == 0, align="LEFT" if r and c in left_cols else "CENTER",
                  pad=(1.0, 1.0, 0.5, 0.5),
                  border=_box(left=c == 0, right=c == m - 1, top=r == 0, bottom=r in (0, n - 1)))
             for r, row in enumerate(rows) for c, v in enumerate(row)]
    for cell in cells:                                  # 머리행 아래 선은 바깥 굵기(정본 목차·이력과 같음)
        if cell["r"] == 1:
            cell["border"] = cell["border"][:2] + (LINE_OUTER, cell["border"][3])
    w.table(grid_table(w.st, widths, heights, cells, repeat_header=1, gap_mm=1.5))


def _spaced(label: str) -> str:
    """정본처럼 짧은 항목 이름은 자간을 벌린다: 공사명 → 공 사 명, 구조 → 구    조."""
    if len(label) == 2:
        return f"{label[0]}    {label[1]}"
    if len(label) == 3:
        return " ".join(label)
    return label


def _overview_table(w: _Writer, project: dict):
    """공사개요(P7, 정본 4.1): 머리행 없이 항목 · 값 두 칸, 가운데로 들어간 폭. 확장 키는 값이 있을 때만."""
    rows = [(OVERVIEW_LABEL.get(k, k), str(project[k])) for k in OVERVIEW_ORDER
            if k in project and str(project[k]).strip() and not isinstance(project[k], (list, dict))]
    widths = [OVERVIEW_W_MM * OVERVIEW_LABEL_PCT / 100, OVERVIEW_W_MM * (100 - OVERVIEW_LABEL_PCT) / 100]
    heights = [max(OVERVIEW_ROW_MM, _est_mm(v, widths[1] - 2, OVERVIEW_PT, 130) + 3.0) for _, v in rows]
    n = len(rows)
    cells = []
    for i, (label, value) in enumerate(rows):
        for c, text in enumerate((_spaced(label), value)):
            cells.append(dict(r=i, c=c, text=text, pt=OVERVIEW_PT, pad=(1.0, 1.0, 0.5, 0.5),
                              border=(LINE_OUTER if c == 0 else LINE_THIN, LINE_OUTER if c == 1 else LINE_THIN,
                                      LINE_OUTER if i == 0 else LINE_THIN, LINE_OUTER if i == n - 1 else LINE_THIN)))
    w.table(plan_parts.offset(grid_table(w.st, widths, heights, cells, gap_mm=1.5), OVERVIEW_OFFSET_MM))


def _special(w: _Writer, mark: str, project: dict):
    """{표:…} 표지를 표로 그린다."""
    kind = mark[len("{표:"):-1]
    if kind == "공사개요":
        missing = [k for k in OVERVIEW_REQUIRED if k not in project]
        if missing:
            raise PlaceholderError(f"공사개요 표 값 없음: {missing}")
        _overview_table(w, project)
    elif kind == "조직":
        rows = project.get("조직") or []
        if not rows:
            raise PlaceholderError("조직 표 값 없음: 조직")
        plan_parts.add_org(w, rows, lambda t: t)       # 상위 관계가 있으면 조직도(P6)를 표 위에
        people = [r for r in rows if r.get("성명")]      # 회사·부서처럼 성명 없는 조직 단위는 조직도에만
        _simple_table(w, [["직무", "성명", "자격", "담당업무"]] + [[r["직무"], r["성명"], r.get("자격", ""), r.get("담당", "")]
                                                            for r in people], [30, 35, 40, BODY_MM - 105], left_cols={3})
    elif kind == "품질목표":
        rows = project.get("품질목표") or []
        if not rows:
            raise PlaceholderError("품질목표 표 값 없음: 품질목표")
        _simple_table(w, [["품질목표", "측정 지표", "확인 주기", "담당"]] + [[r["목표"], r["지표"], r["주기"], r["담당"]]
                                                                    for r in rows], [40, 70, 30, BODY_MM - 140],
                      left_cols={0, 1})
    else:
        raise PlaceholderError(f"알 수 없는 표 표지: {mark}")


def _lines(w: _Writer, items, values, project):
    """문단 목록을 쓴다. {표:…} 한 줄은 표로 그린다. ({8.11}은 body_after 에만 둔다.)"""
    for t in items or []:
        if t.startswith("{표:") and t.endswith("}"):
            _special(w, t, project)
        else:
            w.body(fill(t, values))


def _section_boxes(w: _Writer, s: dict, tpl: dict, values: dict, nums: dict[str, int] | None = None):
    """절 첫머리 개요 칸(정본 절 첫 쪽): 목적 · 적용범위 · 적용기준(업무 절차) · 관련문서(작성기준 근거) · 첨부(양식)(기록).

    칸마다 따로 선을 두르고 칸 사이를 3.0 띄운다 — 한 표 안에 선 없는 띄움 행을 끼워 뷰어와 상관없이 같은 간격이 되게 한다.
    """
    st = w.st
    inner = BOX_COLS_MM[1] - BOX_PAD_MM[0] - BOX_PAD_MM[1]
    p_plain = st.para("JUSTIFY", BOX_LINE)
    p_num = st.para("JUSTIFY", BOX_LINE, indent=-BOX_NUM_HANG_MM)
    steps = [fill(x, values) for x in s.get("steps") or []]
    body_text = [fill(x, values) for x in s.get("body") or [] if not x.startswith("{표:")]
    criteria = ([(f"{i}. {x}", p_num) for i, x in enumerate(steps, 1)] if steps
                else [(x, p_plain) for x in body_text])
    if not criteria and s.get("body"):              # 표만 있는 절(4.1 등): 칸을 비우지 않고 아래 표를 가리킨다
        criteria = [(f"아래 「{s.get('body_label', '주요 내용')}」 표에 따른다.", p_plain)]
    basis = str(s.get("basis") or "").strip()
    contents = [
        [(fill(s["purpose"], values), p_plain)] if s.get("purpose") else [],
        [(fill(s.get("scope", tpl["default_scope"]), values), p_plain)],
        criteria,
        [(f"- 건설공사 품질관리 업무지침 {basis}", p_plain)] if basis else [],
        [(f"{i}. {fill(r, values)}", p_num) for i, r in enumerate(s.get("records") or [], 1)],
    ]
    attached = plan_parts.records_lines(s, nums or {}, lambda t: fill(t, values))
    if attached is not None:                        # 양식이 있으면 '양식 N 이름'(P4)으로
        contents[4] = [(t, p_plain) for t in attached]
    heights, cells = [], []
    for k, (label, lines) in enumerate(zip(BOX_LABELS, contents)):
        if k:
            heights.append(BOX_GAP_MM)
            cells.append(dict(r=len(heights) - 1, c=0, cs=2, text="", border=(None,) * 4, pt=2))
        need = sum(_est_mm(t, inner, BOX_PT, BOX_LINE) for t, _ in lines) + BOX_PAD_MM[2] + BOX_PAD_MM[3]
        heights.append(max(BOX_MIN_MM[k], need))
        r = len(heights) - 1
        cells.append(dict(r=r, c=0, text=label, pt=BOX_PT, bold=True, border=_box(right=False)))
        cells.append(dict(r=r, c=1, text="", lines=lines or None, pt=BOX_PT, align="LEFT", pad=BOX_PAD_MM,
                          border=_box(left=False)))
    w.table(grid_table(st, BOX_COLS_MM, heights, cells))


def _units(tpl: dict) -> list[dict]:
    """쪽 머리 단위 목록. 절 없는 장이 이어지면 한 단위로 묶고(원본 1·2·3장처럼), 절은 하나씩."""
    units: list[dict] = []
    for ch in tpl["chapters"]:
        secs = ch.get("sections", [])
        if not secs:
            if units and units[-1]["kind"] == "chapters":
                units[-1]["chapters"].append(ch)
            else:
                units.append({"kind": "chapters", "chapters": [ch]})
            continue
        for i, s in enumerate(secs):
            units.append({"kind": "section", "chapter": ch if i == 0 else None, "section": s,
                          "is_811": MARK_811 in (s.get("body_after") or [])})
    if not any(u.get("is_811") for u in units):
        raise ValueError(f"템플릿에 {MARK_811} 표지가 없습니다")
    return units


def build_plan(rows: list[PlanRow], project: dict, out: str | Path, *, basis_version: str,
               revision: int | str, date: str, template: str | Path | dict = DEFAULT_TEMPLATE,
               unlisted: list[dict] | None = None, notice_footer: bool = False,
               notes: list[str] | None = None) -> Path:
    """notes 를 주면 사용자에게 알릴 말(판정 전 기본 문장 사용 등)을 덧붙인다(cli 가 요약 warnings 에 싣는다)."""
    tpl = template if isinstance(template, dict) else load_template(template)
    revs = _revisions(project, revision, date)
    values = {k: v for k, v in project.items() if isinstance(v, (str, int, float))}
    staff = project.get("품질관리자")
    if isinstance(staff, list) and staff and isinstance(staff[0], dict):
        # 품질관리자 배치 목록(부표 source)도 받는다 — 자리표시 {품질관리자}는 첫 사람(성명, 없으면 직무)
        values["품질관리자"] = str(staff[0].get("성명") or staff[0].get("직무") or "")
    judged = project.get("판정") if isinstance(project.get("판정"), dict) else {}
    for k in JUDGED_KEYS:                          # danburn start 의 판정 블록을 치환값으로 펼친다(최상위가 우선)
        if k not in values and isinstance(judged.get(k), (str, int, float)):
            values[k] = judged[k]
    pre = [k for k in JUDGED_DEFAULTS if k not in values or str(values[k]).startswith(PRE_JUDGE_MARK)]
    for k in pre:                                  # 옛 project.yaml(판정 전): 기본 문장으로 채우고 알린다
        values.setdefault(k, JUDGED_DEFAULTS[k])
    if pre and notes is not None:
        notes.append(PRE_JUDGE_NOTE)
    current = revs[-1]                              # = revision 인자(검사됨). 표지·목차·쪽 머리·이력이 모두 이 값
    values.update({"기준": basis_version, "개정": str(current["개정"]), "일자": current["일자"]})
    need = placeholders(tpl) - values.keys()
    if need:
        raise PlaceholderError(f"project 입력에 없는 키: {sorted(need)}")
    logo = _logo(project)
    logo_path = str(Path(str(project["로고"]).strip()).expanduser()) if logo else None
    company = str(project.get("회사명") or "")
    doc_title = str(project.get("문서명") or DOC_TITLE)
    brand = {"logo": logo_path, "company": company}

    def rev_of(no: str) -> tuple[str, str]:
        r = _last_rev(revs, no) or revs[-1]
        return f"Rev.{r['개정']}", r["일자"]

    units = _units(tpl)
    nums = plan_parts.form_numbers([u["section"] for u in units if u["kind"] == "section"])
    teams = plan_parts.teams_of(project, tpl)

    def fv(t: str) -> str:
        return fill(t, values)

    doc = HwpxDocument.new()
    w = _Writer(doc, notice_footer)
    cur = (f"Rev.{current['개정']}", current["일자"])

    w.new_unit(first=True)
    w.frame(doc_title=doc_title, title="", revision="", date="", header=False)
    _cover(w, project, current["개정"], current["일자"], logo_path, title=doc_title)

    w.new_unit()
    w.frame(doc_title=doc_title, title="A. 목차", revision=cur[0], date=cur[1], **brand)
    _toc(w, tpl, revs)

    w.new_unit()
    w.frame(doc_title=doc_title, title="B. 승인 및 개정이력", revision=cur[0], date=cur[1], **brand)
    _history(w, project, revs, tpl)

    for u in units:
        w.new_unit()
        if u["kind"] == "chapters":
            chs = u["chapters"]
            rv = max((rev_of(c["id"]) for c in chs), key=lambda x: int(x[0][4:]))
            w.frame(doc_title=doc_title, title=" / ".join(f"{c['id']}. {c['title']}" for c in chs),
                    revision=rv[0], date=rv[1], **brand)
            for ch in chs:
                w.chapter(f"{ch['id']}. {ch['title']}")
                _lines(w, ch.get("body"), values, project)
            continue
        s = u["section"]
        rv = rev_of(s["id"])
        if u["chapter"] and u["chapter"].get("body"):
            _lines(w, u["chapter"]["body"], values, project)
        _section_boxes(w, s, tpl, values, nums)
        if s.get("roles"):                          # P2 업무 분장표: 개요 칸 바로 아래
            plan_parts.add_roles(w, s["roles"], teams, fv)
        if s.get("flow"):                           # P3 업무 흐름표: 새 쪽
            plan_parts.add_flow(w, s["flow"], nums, fv)
        tables = [x for x in s.get("body") or [] if x.startswith("{표:")]
        rest = s.get("body") if s.get("steps") else tables     # 절차가 없으면 글은 적용기준 칸에 들어갔다
        if rest:
            w.prev = "table"
            w.chapter(f"1. {s.get('body_label', '주요 내용')}", page_break=bool(s.get("flow")))
            _lines(w, rest, values, project)
        if u["is_811"]:
            # 같은 구역에 8.11 쪽 머리·꼬리말·표를 채운다(design). 개요 칸 뒤 새 쪽에서 시작(정본과 같음).
            add_811_tables(doc, rows, section=w.sec, title=f"{s['id']} {s['title']}", unlisted=unlisted,
                           basis_version=basis_version, revision=rv[0], date=rv[1],
                           doc_title=doc_title, section_title=f"{2 if rest else 1}. 품질시험 및 검사계획",
                           new_page=True, notice_footer=notice_footer, **brand)
            w.frame_args = dict(doc_title=doc_title, title=f"{s['id']} {s['title']}", revision=rv[0], date=rv[1],
                                header=True, **brand)     # 가로 양식 구역이 같은 쪽 머리를 쓰도록
        else:
            w.frame(doc_title=doc_title, title=f"{s['id']} {s['title']}", revision=rv[0], date=rv[1], **brand)
        if s.get("tables"):                         # P5 부표: 흐름표·본문(8.11 표) 뒤, 양식 앞
            plan_parts.add_tables(w, s["tables"], project, fv)
        for f in s.get("forms") or []:              # P4 기록 양식: 절 끝에 양식마다 한 쪽(정본 배치)
            w.orient(bool(f.get("landscape")))      # 가로 양식은 그 쪽만 가로 구역
            plan_parts.add_form(w, f, nums[f["key"]], values, fv)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save_to_path(str(out))
    _register_bin_items(out)
    return out


_MEDIA = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}


def _register_bin_items(path: Path) -> None:
    """저장된 패키지의 매니페스트(content.hpf)에 빠진 BinData 파일을 올린다.

    python-hwpx 6.5.0 은 구역이 여럿인 문서에 같은 바이트의 그림을 여러 번 넣으면 BinData 파일·binItem 은
    모두 쓰면서 매니페스트에는 첫 항목만 남긴다 → 표지·쪽 머리마다 넣는 로고가 렌더되지 않는다(L3-T5 실측).
    메모리 안 매니페스트를 고쳐도 저장 때 되돌아가서, 저장된 zip 을 직접 고친다(mimetype 첫 항목·무압축 유지).
    """
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        parts = {i.filename: z.read(i.filename) for i in infos}
    hpf = parts["Contents/content.hpf"].decode("utf-8")
    missing = []
    for name in parts:
        m = re.fullmatch(r"BinData/((BIN\d+)\.(\w+))", name)
        if m and m[3].lower() in _MEDIA and f'href="{name}"' not in hpf:
            missing.append(f'<opf:item id="{m[2]}" href="{name}" media-type="{_MEDIA[m[3].lower()]}" isEmbeded="1"/>')
    if not missing:
        return
    hpf = re.sub(r"(</opf:manifest>)", "".join(missing) + r"\1", hpf, count=1)
    parts["Contents/content.hpf"] = hpf.encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w") as z:
        for i in infos:
            z.writestr(i, parts[i.filename], compress_type=i.compress_type)
    tmp.replace(path)


def _cover(w: _Writer, project: dict, revision, date: str, logo_path: str | None, title: str = DOC_TITLE):
    """표지(정본 §2): 공사명 24 · 문서명 44 · 영문 18 · 정보 상자(79.1 폭, 10.7 × 4줄, 12pt) · 로고 · 회사명.

    쪽 전체를 선 없는 3칸 표 하나로 두고 행 높이로 자리를 고정한다. 로고·회사명은 사용자 입력만 쓴다(없으면 빈 칸).
    """
    st, R = w.st, COVER_ROWS_MM
    heights = [R["top"] - BODY_TOP_MM, R["site"], R["gap1"], R["title"], R["sub"], R["gap2"],
               *[R["info"]] * 4, R["gap3"], R["logo"], R["company"]]
    none = (None,) * 4
    cells = [dict(r=r, c=0, cs=3, text="", pt=2, border=none) for r in (0, 2, 5, 10)]
    for r, text, pt in ((1, project["공사명"], COVER_PT["site"]), (3, title, COVER_PT["title"]),
                        (4, COVER_SUBTITLE, COVER_PT["sub"]), (12, str(project.get("회사명") or ""), COVER_PT["company"])):
        cells.append(dict(r=r, c=0, cs=3, text=text, pt=pt, bold=r == 12, border=none, pad=(0, 0, 0, 0)))
    info = [("문서번호", project.get("문서번호", "")), ("제정일자", project.get("제정일자", "")),
            ("개정번호", f"Rev.{revision}"), ("개정일자", date)]
    for k, (name, value) in enumerate(info):
        r = 6 + k
        cells.append(dict(r=r, c=0, text="", pt=2, border=none))
        pair = [(f"{name} :  ", st.char(COVER_PT["info"], bold=True)), (str(value), st.char(COVER_PT["info"]))]
        cells.append(dict(r=r, c=1, text="", lines=[(pair, st.para("LEFT", 120))], pt=COVER_PT["info"], align="LEFT",
                          pad=(COVER_INFO_PAD_MM, 1.0, 0, 0),
                          border=(LINE_OUTER, LINE_OUTER, LINE_OUTER if k == 0 else LINE_THIN,
                                  LINE_OUTER if k == 3 else LINE_THIN)))
        cells.append(dict(r=r, c=2, text="", pt=2, border=none))
    logo_cell = dict(r=11, c=0, cs=3, text="", pt=2, border=none, pad=(0, 0, 0, 0))
    cells.append(logo_cell)
    tbl = grid_table(st, COVER_COLS_MM, heights, cells)
    if logo_path:
        # 로고는 칸 높이 안에 비율대로(글자처럼 취급 그림, 쪽 머리와 같은 방식)
        run = hwpx_out._logo_run(w.doc, w.sec, logo_path, (COVER_COLS_MM[1], R["logo"] - 1.0))
        tc = next(t for t in tbl.iter(f"{HP}tc") if t.find(f"{HP}cellAddr").get("rowAddr") == "11")
        old = tc.find(f"{HP}subList/{HP}p/{HP}run")
        old.getparent().replace(old, run)
    w.table(tbl)


def _toc(w: _Writer, tpl: dict, revs: list[dict]):
    """A. 목차(정본 §3): 4칸(장번호·제목·개정번호·개정일자), 머리행 아래만 가로선, 항목은 4.87 줄, 표는 쪽 아래(277.6)까지."""
    st = w.st
    last = revs[-1]
    entries = [("A", "목차", 0, last), ("B", "승인 및 개정이력", 0, last)]
    has_sections = {ch["id"] for ch in tpl["chapters"] if ch.get("sections")}
    for no, title, depth in toc_entries(tpl):          # 절이 있는 장 줄은 개정 칸을 비운다(정본과 같음)
        entries.append((no, title, depth, None if no in has_sections else _last_rev(revs, no)))
    heights = [TOC_HEAD_MM, TOC_TOP_PAD_MM] + [TOC_ROW_MM] * len(entries)
    filler = BODY_END_MM - BODY_TOP_MM - sum(heights)
    if filler > 0.5:
        heights.append(filler)
    n, m = len(heights), 4
    p_sec = st.para("LEFT", 120, left=TOC_SECTION_INDENT_MM)
    cells = []
    for c, h in enumerate(["장번호", "제    목", "개정번호", "개정일자"]):
        cells.append(dict(r=0, c=c, text=h, pt=TOC_PT, border=(LINE_OUTER if c == 0 else LINE_THIN,
                                                               LINE_OUTER if c == m - 1 else LINE_THIN,
                                                               LINE_OUTER, LINE_OUTER)))

    def side(c, r):
        return (LINE_OUTER if c == 0 else LINE_THIN, LINE_OUTER if c == m - 1 else LINE_THIN,
                LINE_OUTER if r == 1 else None, LINE_OUTER if r == n - 1 else None)
    pad = (0.5, 0.5, 0, 0)
    for r in [1] + ([n - 1] if filler > 0.5 else []):
        for c in range(m):
            cells.append(dict(r=r, c=c, text="", pt=2, border=side(c, r), pad=pad))
    for k, (no, title, depth, rv) in enumerate(entries):
        r = 2 + k
        is_sec = depth == 1
        cells += [
            dict(r=r, c=0, text="" if is_sec else no, pt=TOC_PT, border=side(0, r), pad=pad),
            dict(r=r, c=1, text="", pt=TOC_PT, align="LEFT", border=side(1, r), pad=(TOC_TITLE_PAD_MM, 0.5, 0, 0),
                 lines=[(f"{no} {title}" if is_sec else title, p_sec if is_sec else st.para("LEFT", 120))]),
            dict(r=r, c=2, text=str(rv["개정"]) if rv else "", pt=TOC_PT, border=side(2, r), pad=pad),
            dict(r=r, c=3, text=compact_date(rv["일자"], dot=False) if rv else "", pt=TOC_PT, border=side(3, r), pad=pad),
        ]
    w.table(grid_table(st, TOC_COLS_MM, heights, cells, repeat_header=1))


def _history(w: _Writer, project: dict, revs: list[dict], tpl: dict):
    """B. 승인 및 개정이력(정본 §4): 5칸 이력 표(최소 11줄) + 쪽 아래쪽 결재란(윗선 202.3)."""
    st = w.st
    titles = {no: title for no, title, _ in toc_entries(tpl)}
    widths = [x * BODY_MM / sum(HIST_COLS_MM) for x in HIST_COLS_MM]
    rows = [["개정번호", "개정일자", "개정 장 번호", "개정 사유", "비 고"]]
    for r in revs:
        chs = "\n".join(f"{c} {titles[str(c)]}" if str(c) in titles and "." in str(c) else str(c)
                         for c in r.get("장", []))
        rows.append([str(r["개정"]), compact_date(r["일자"]), chs, str(r.get("사유", "")), ""])
    rows += [[""] * 5 for _ in range(HIST_MIN_ROWS - len(revs))]
    heights = [HIST_HEAD_MM] + [max(HIST_ROW_MM, max(_est_mm(v, widths[c], HIST_PT, 120, 1.0) + 1.0
                                                     for c, v in enumerate(row))) for row in rows[1:]]
    n = len(rows)
    cells = [dict(r=r, c=c, text=v, pt=HIST_PT, pad=(0.5, 0.5, 0.5, 0.5),
                  border=(LINE_OUTER if c == 0 else LINE_THIN, LINE_OUTER if c == 4 else LINE_THIN,
                          LINE_OUTER if r <= 1 else LINE_THIN, LINE_OUTER if r in (0, n - 1) else LINE_THIN))
             for r, row in enumerate(rows) for c, v in enumerate(row)]
    w.table(grid_table(st, widths, heights, cells, repeat_header=1))
    sign = project.get("결재") or []
    if not sign:
        return
    gap = SIGN_TOP_MM - BODY_TOP_MM - sum(heights)
    if gap > 1:                                    # 결재란을 쪽 아래쪽 제자리(정본 202.3)에 둔다
        w.table(grid_table(st, [BODY_MM], [gap], [dict(r=0, c=0, text="", pt=2, border=(None,) * 4)]))
    k = len(sign)
    widths = [SIGN_FIRST_COL_MM] + [(BODY_MM - SIGN_FIRST_COL_MM) / k] * k
    srows = [["구     분"] + [s["구분"] for s in sign], ["직     책"] + [s["직책"] for s in sign],
             ["성     명"] + [s["성명"] for s in sign], ["서     명"] + [""] * k,
             ["일     자"] + [compact_date(revs[-1]["일자"])] * k]
    heights = [SIGN_ROW_MM] * 3 + [SIGN_SIGN_ROW_MM, SIGN_ROW_MM]
    cells = [dict(r=r, c=c, text=v, pt=SIGN_PT,
                  border=(LINE_OUTER if c == 0 else LINE_THIN, LINE_OUTER if c == k else LINE_THIN,
                          LINE_OUTER if r <= 1 else LINE_THIN, LINE_OUTER if r in (0, 4) else LINE_THIN))
             for r, row in enumerate(srows) for c, v in enumerate(row)]
    w.table(grid_table(st, widths, heights, cells))
