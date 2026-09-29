"""8.11 행을 HWPX 표로 조립한다(한컴 설치 불필요, python-hwpx + lxml 직접 조립).

모양의 기준은 docs/design/8.11-layout.md(수치 명세). 이 파일의 상수는 그 명세와 1:1로 맞춘다.

주의
- add_heading 뒤 문단은 개요 번호를 물려받는다(루프 0 스모크) → 제목도 일반 문단으로 쓴다.
- 표는 라이브러리 add_table 대신 lxml로 직접 만든다. 셀마다 선 굵기(바깥 0.4mm·안 0.2mm)·
  병합·글자 크기·정렬을 따로 줘야 하는데 add_table/merge_cells로는 셀별 선 굵기를 못 준다.
- 병합된 칸은 HWPX에서 덮인 셀(tc)을 아예 쓰지 않고, 기준 셀의 cellSpan·cellSz로 나타낸다.
- 글꼴은 함초롬돋움(기본 서식의 글꼴 0)만 참조하고 임베딩하지 않는다(isEmbedded="0").
"""
from __future__ import annotations

import itertools
import math
import re
from copy import deepcopy
from pathlib import Path

from hwpx import HwpxDocument
from lxml import etree

from .model import PlanRow

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"

NOTICE = "본 제품은 한글과컴퓨터의 HWP 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다."
# 고지 줄은 기본으로 산출 쪽에 넣지 않는다(제출 문서에 소프트웨어 고지가 들어가지 않게, L7-D6).
# 고지는 NOTICE.md·README·CLI 도움말에 둔다. notice_footer=True(CLI --notice-footer)면 꼬리말에 넣는다.
# 꼬리말 여백(PAGE footer_margin_mm)은 고지 유무와 상관없이 그대로 둔다 → 본문 아래 한계 277.8 불변.

# ── 명세 수치(docs/design/8.11-layout.md) ─────────────────────────────
MM = 7200 / 25.4                     # mm → HWPUNIT
# 방향은 set_page_setup(orientation=)을 쓰지 않고 pagePr 을 직접 쓴다(_set_orientation 참고).
# 머리말 21 = 쪽 머리 표(7+8) + 본문과 띄움 6 → 본문 시작 37.5(정본 모든 쪽 유형의 첫 표·글 윗선, plan-layout.md §1)
# 꼬리말 9.2 → 본문 아래 한계 277.8(정본 목차 표 끝 277.6, 8.11 표 쪽 최대 277.1)
PAGE = dict(paper_size="A4", margin_left_mm=16.5, margin_right_mm=12.5,
            margin_top_mm=16.5, margin_bottom_mm=10, header_margin_mm=21, footer_margin_mm=9.2)
A4_MM = (210, 297)
# 8.11 표 칸(hwpx·xlsx 공용 — testplan_xlsx 도 이 상수를 쓴다). 칸 이름은 LH 품질관리 지침 별지 「품질시험계획서」
# 서식의 보편 용어(시험품목·시험종목·계획물량·계획시험횟수 현장/의뢰/KS)에 LHCS 10 40 00 부록 표의 '시험방법'을 더했다(L14-E).
HEAD = ["공종", "시험품목", "시험종목", "시험방법", "계획물량", "단위", "시험빈도", "산출근거", "현장", "의뢰", "KS", "비고"]
# 칸 번호(병합 규칙·머리 조립·xlsx 가 같이 쓴다)
C_WORK, C_ITEM, C_TEST, C_METHOD, C_QTY, C_UNIT, C_FREQ, C_BASIS, C_SITE, C_EXT, C_KS, C_NOTE = range(12)
# 2줄 머리: (행, 칸, 행 병합, 칸 병합, 글). 시험빈도는 빈도·산출근거 두 칸 위에 걸치고(아래 줄 왼칸 비움), 계획시험횟수는 세 칸
HEAD_CELLS = ([(0, c, 2, 1, HEAD[c]) for c in range(C_FREQ)]
              + [(0, C_FREQ, 1, 2, "시험빈도"), (1, C_FREQ, 1, 1, ""), (1, C_BASIS, 1, 1, HEAD[C_BASIS]),
                 (0, C_SITE, 1, 3, "계획시험횟수"), (1, C_SITE, 1, 1, HEAD[C_SITE]), (1, C_EXT, 1, 1, HEAD[C_EXT]),
                 (1, C_KS, 1, 1, HEAD[C_KS]), (0, C_NOTE, 2, 1, HEAD[C_NOTE])])
# 정본 폭(L6, plan-layout.md §8)에서 시험방법 18.0 을 시험종목(42.1→30.1)·산출근거(32.3→26.3)에서 뺐다
WIDTHS_MM = [7.6, 22.9, 30.1, 18.0, 13.6, 9.6, 21.4, 26.3, 7.7, 8.3, 7.9, 7.6]    # 합 181.0 = 세로 A4 본문폭
ALIGN = ["CENTER", "CENTER", "LEFT", "LEFT", "RIGHT", "CENTER", "LEFT", "LEFT", "CENTER", "CENTER", "CENTER", "LEFT"]
SMALL_COLS = {C_TEST, C_METHOD, C_FREQ, C_BASIS, C_NOTE}   # 7pt 칸(긴 문장). 나머지는 8pt
HEAD_ROW_MM = 6.3                    # 머리행 2줄 각각
BODY_ROW_MM = 4.8                    # 본문 행 최소 높이(내용이 길면 늘어난다)
CELL_PAD_MM = (0.5, 0.5, 0.3, 0.3)   # 좌·우·위·아래
TABLE_GAP_MM = 1.5                   # 표 아래 바깥 여백(다음 문단과 띄움)
LINE_OUTER = "0.4 mm"
LINE_INNER = "0.15 mm"                # 정본 안쪽 선 0.17~0.21(가는선)
LINE_THIN = "0.12 mm"                 # 계획서 앞쪽 표(목차·이력·절 개요 칸)의 안쪽 선(plan-layout.md §7)
PT = dict(company=8, doc_title=15, title=13.5, meta=9, section=10, discipline=10, head=8, body=8, small=6.5, note=8, footer=7)
# 쪽 머리 왼쪽 로고 칸(원본 실측: 로고 그림 약 13.2×12.1, 쪽 머리 선은 x=33.7부터). 로고·회사명은 사용자 입력만 쓴다.
LOGO_COL_MM = 17.2                   # 본문 왼끝(16.5)에서 쪽 머리 선 시작(33.7)까지
LOGO_BOX_MM = (13.2, 12.1)           # 그림이 들어갈 최대 폭·높이(비율 유지로 줄인다)
COMPANY_LINE_MM = 3.5                # 회사명 한 줄(8pt 굵게) 높이 — 회사명이 있으면 그림 상자 높이에서 뺀다
# 회사명은 로고 칸 폭(16.2)에 맞춘다(L13-H1). 글은 바꾸거나 자르지 않고 크기·줄 수·장평만 바꾼다.
#  1) 한 줄: 8pt 에서 0.5pt 씩 6pt 까지. 하한 6pt = 8.11 표의 가장 작은 글(6.5pt)보다 한 단계 아래,
#     정본 긴 시험항목 최소(6.3pt) 근처 — 굵은 글 한 줄 이름이라 이보다 작으면 A4 인쇄에서 획이 뭉친다.
#  2) 두 줄(어절 경계): 8pt→6pt, 그래도 넘치면 6pt 에서 장평 90·80·70%. 장평 하한 70% 도 같은 이유(인쇄 획 뭉침).
#  3) 두 줄(글자 경계, 어절이 칸보다 길 때): 2)와 같은 순서. 두 줄 높이만큼 로고 그림 상자를 줄인다
#     → 로고 칸·쪽 머리 표 높이와 선 위치는 그대로.
COMPANY_PT_STEPS = (8, 7.5, 7, 6.5, 6)
COMPANY_RATIO_STEPS = (100, 90, 80, 70)
COMPANY_MAX_LINES = 2
COMPANY_SLACK = 1.05                 # 한글 밖 글자(영숫자·기호·빈칸)의 굵은 글·대체 글꼴 여유. 한글은 전각 1em 그대로
HEADER_ROWS_MM = (7.0, 8.0)          # 쪽 머리 1줄(문서명)·2줄(절 제목) 높이
HEADER_PAD_MM = dict(doc=(2.3, 0.5, 0.3, 1.1), title=(2.3, 0.5, 0.3, 1.8), meta=(0.5, 0.5, 0.3, 2.5))  # 정본 글 자리
HEADER_META_MM = 42.0                # 쪽 머리 오른쪽 칸(개정일·Rev·쪽). 정본 글 158.5~196.8(38.3), 우리 글 34.2(두 자리 쪽 ~36)
ITEM_PT_STEPS = (8, 7.5, 7, 6.5)     # 시험항목이 두 줄을 넘으면 이 순서로 줄여 쓴다(정본: 보통 8, 긴 이름 6.3~6.8)
ITEM_MAX_LINES = 2
PAGE_SAFETY_MM = 3.0                 # 쪽 단위 표 나눔 여유(뷰어마다 행 높이가 조금 다르다)
VERTICAL_WORK_MIN_ROWS = 3           # 공종 병합이 이 행 수 이상이면 한 글자씩 세로로 쌓는다
ITEM_ONE_LINE_CHARS = 9              # 시험항목이 이보다 길면 규격 괄호 앞에서 줄바꿈
# 공종이 비어 오는 자재의 표시용 기본 공종(내역서 공종 추출 전 임시값)
WORK_BY_MATERIAL = {"ready_mixed_concrete": "철근콘크리트공사", "rebar": "철근콘크리트공사"}
# 8.11 뒤 "시험계획 미작성 자재" 표(명세 §11): 규칙이 없는 자재가 문서에서 조용히 빠지지 않게 한다
UNLISTED_TITLE = "시험계획 미작성 자재 (확인 필요)"
UNLISTED_HEAD = ["구분", "자재", "근거", "내역 행 수", "조치"]
UNLISTED_WIDTHS_MM = [24.0, 38.0, 42.0, 17.0, 60.0]   # 합 181.0
UNLISTED_ALIGN = ["CENTER", "LEFT", "LEFT", "RIGHT", "LEFT"]
UNLISTED_SMALL_COLS = {2, 4}
UNLISTED_KINDS = {   # kind → (구분 글, 기본 조치)
    "uncovered": ("규칙 없음", "시험계획 작성 후 8.11에 추가"),
    "rule_miss": ("규칙 밖 행", "그 자재가 맞으면 규칙 이름·제외어 보강 후 8.11에 추가"),   # L7-E4 규칙은 있으나 행이 안 걸림
    "owner_standard": ("발주처 기준 필요", "발주처 품질기준 확인 후 시험계획 작성"),
    "site_measurement": ("현장측정 확인", "법정 측정 대상 여부 확인 후 계획에 반영"),
}

_ids = itertools.count(1_000_000_001)


def _hu(mm: float) -> int:
    return int(round(mm * MM))


def _q(v: float) -> str:
    return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.2f}"


def compact_date(date: str, dot: bool = True) -> str:
    """'2026. 01. 05.'·'2026-1-5' → '2026.01.05.'(dot=False 면 끝 점 없이). 날짜 모양이 아니면 그대로."""
    d = str(date).strip()
    m = re.fullmatch(r"(\d{4})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})\.?", d)
    return f"{m[1]}.{int(m[2]):02d}.{int(m[3]):02d}" + ("." if dot else "") if m else d


def _meta_text(date: str, revision: str) -> str:
    """쪽 머리 오른쪽 '2025.03.26. [Rev.7] ' 부분(쪽 번호 앞)."""
    d = compact_date(date)
    rev = revision.strip()
    rev = f"[{rev}]" if rev and not rev.startswith("[") else rev
    return " ".join(x for x in (d, rev) if x) + " "


class _Styles:
    """header.xml에 글자·문단·테두리 모양을 필요한 만큼 더하고 id를 돌려준다(같은 요청은 재사용)."""

    def __init__(self, doc: HwpxDocument):
        self.part = doc.oxml.headers[0]
        self.head = self.part.element
        self._cache: dict[tuple, str] = {}

    def _container(self, local: str) -> etree._Element:
        return self.head.find(f".//{HH}{local}")

    def _add(self, local: str, child_local: str, el: etree._Element) -> str:
        box = self._container(local)
        new_id = str(max(int(c.get("id")) for c in box.findall(f"{HH}{child_local}")) + 1)
        el.set("id", new_id)
        box.append(el)
        box.set("itemCnt", str(len(box.findall(f"{HH}{child_local}"))))
        self.part.mark_dirty()
        return new_id

    def char(self, pt: float, bold: bool = False, ratio: int = 100) -> str:
        """글자 모양. ratio = 장평(%, 100 이 기본 — 좁은 칸에 긴 이름을 한 글자도 안 바꾸고 넣을 때만 줄인다)."""
        key = ("char", pt, bold) if ratio == 100 else ("char", pt, bold, ratio)
        if key not in self._cache:
            base = self._container("charProperties").find(f"{HH}charPr[@id='0']")
            el = deepcopy(base)
            el.set("height", str(int(round(pt * 100))))
            if ratio != 100:
                for k in el.find(f"{HH}ratio").attrib:
                    el.find(f"{HH}ratio").set(k, str(ratio))
            for k in el.find(f"{HH}fontRef").attrib:
                el.find(f"{HH}fontRef").set(k, "0")          # 함초롬돋움
            if bold:
                el.find(f"{HH}underline").addprevious(etree.Element(f"{HH}bold"))
            self._cache[key] = self._add("charProperties", "charPr", el)
        return self._cache[key]

    def para(self, align: str, line_pct: int = 130, *, left: float = 0, indent: float = 0,
             before: float = 0, after: float = 0) -> str:
        """문단 모양. left(왼쪽 여백)·indent(첫 줄, 음수 = 내어쓰기)·before/after(문단 위·아래) 는 mm."""
        key = ("para", align, line_pct, left, indent, before, after)
        if key not in self._cache:
            base = self._container("paraProperties").find(f"{HH}paraPr[@id='0']")
            el = deepcopy(base)
            el.find(f"{HH}align").set("horizontal", align)
            el.find(f"{HH}align").set("vertical", "CENTER")
            for ls in el.iter(f"{HH}lineSpacing"):
                ls.set("value", str(line_pct))
            for mg in el.iter(f"{HH}margin"):      # hp:case·hp:default 두 분기 모두(python-hwpx 와 같은 방식)
                for ch in mg:
                    v = {"intent": indent, "left": left, "prev": before, "next": after}.get(etree.QName(ch).localname)
                    if v is not None:
                        ch.set("value", str(_hu(v)))
            self._cache[key] = self._add("paraProperties", "paraPr", el)
        return self._cache[key]

    def border(self, left: str | None, right: str | None, top: str | None, bottom: str | None) -> str:
        """각 변 굵기('0.4 mm' 등, None=선 없음)로 borderFill id."""
        key = ("border", left, right, top, bottom)
        if key not in self._cache:
            el = etree.Element(f"{HH}borderFill", threeD="0", shadow="0", centerLine="NONE",
                               breakCellSeparateLine="0")
            etree.SubElement(el, f"{HH}slash", type="NONE", Crooked="0", isCounter="0")
            etree.SubElement(el, f"{HH}backSlash", type="NONE", Crooked="0", isCounter="0")
            for side, w in (("left", left), ("right", right), ("top", top), ("bottom", bottom)):
                etree.SubElement(el, f"{HH}{side}Border", type="SOLID" if w else "NONE",
                                 width=w or "0.1 mm", color="#000000")
            etree.SubElement(el, f"{HH}diagonal", type="NONE", width="0.1 mm", color="#000000")
            self._cache[key] = self._add("borderFills", "borderFill", el)
        return self._cache[key]


def _para(text: str, para_id: str, char_id: str, *, page_break: bool = False) -> etree._Element:
    p = etree.Element(f"{HP}p", id=str(next(_ids)), paraPrIDRef=para_id, styleIDRef="0",
                      pageBreak="1" if page_break else "0", columnBreak="0", merged="0")
    run = etree.SubElement(p, f"{HP}run", charPrIDRef=char_id)
    etree.SubElement(run, f"{HP}t").text = text
    return p


def _cell(st: _Styles, text: str, *, col: int, row: int, colspan: int, rowspan: int, width: int, height: int,
          border: str, align: str, pt: float, bold: bool = False, header: bool = False,
          vertical: bool = False, valign: str = "CENTER", pad: tuple[float, float, float, float] | None = None,
          lines: list[tuple[str, str]] | None = None) -> etree._Element:
    """표 칸 하나. lines=[(글, 문단 모양 id), …] 를 주면 text 대신 그 문단들을 쓴다(내어쓰기 등).
    글 자리에 [(글, 글자 모양 id), …] 를 주면 한 문단 안에 모양이 다른 조각을 잇는다(굵은 항목 이름 + 값)."""
    tc = etree.Element(f"{HP}tc", name="", header="1" if header else "0", hasMargin="1", protect="0",
                       editable="0", dirty="0", borderFillIDRef=border)
    sub = etree.SubElement(tc, f"{HP}subList", id="", textDirection="HORIZONTAL",
                           lineWrap="BREAK", vertAlign=valign, linkListIDRef="0", linkListNextIDRef="0",
                           textWidth="0", textHeight="0", hasTextRef="0", hasNumRef="0")
    pid, cid = st.para(align, 120), st.char(pt, bold)
    if lines:
        for line, lpid in lines:
            if isinstance(line, list):
                p = _para(line[0][0], lpid, line[0][1])
                for t, c in line[1:]:
                    etree.SubElement(etree.SubElement(p, f"{HP}run", charPrIDRef=c), f"{HP}t").text = t
                sub.append(p)
            else:
                sub.append(_para(line, lpid, cid))
    else:
        # 세로 글은 textDirection=VERTICAL 대신 한 글자씩 문단으로 쌓는다(뷰어마다 세로쓰기 줄바꿈이 달라 깨졌다)
        for line in (list(text.replace(" ", "")) if vertical and text else (text.split("\n") if text else [""])):
            sub.append(_para(line, pid, cid))
    etree.SubElement(tc, f"{HP}cellAddr", colAddr=str(col), rowAddr=str(row))
    etree.SubElement(tc, f"{HP}cellSpan", colSpan=str(colspan), rowSpan=str(rowspan))
    etree.SubElement(tc, f"{HP}cellSz", width=str(width), height=str(height))
    l, r, t, b = (_hu(v) for v in (pad or CELL_PAD_MM))
    etree.SubElement(tc, f"{HP}cellMargin", left=str(l), right=str(r), top=str(t), bottom=str(b))
    return tc


def _runs(n: int, join) -> list[tuple[int, int]]:
    """0..n-1 을 join(i-1, i)가 참인 동안 이어 붙인 최대 구간들 [(시작, 끝)]."""
    out, s = [], 0
    for i in range(1, n + 1):
        if i == n or not join(i - 1, i):
            out.append((s, i - 1))
            s = i
    return out


def _item_text(item: str) -> str:
    """시험항목이 칸에 한 줄로 안 들어가면 규격 괄호 앞에서 줄을 바꾼다: 레미콘(25-24-150) → 레미콘 / (25-24-150)."""
    if len(item) > ITEM_ONE_LINE_CHARS and "(" in item[1:]:
        i = item.index("(", 1)
        return item[:i].rstrip() + "\n" + item[i:]
    return item


def cell_texts(r: PlanRow) -> list[str]:
    """8.11 한 행의 칸 글(HEAD 순서). 시험방법은 PlanRow.method 가 있을 때만(없으면 빈칸)."""
    return [r.work or WORK_BY_MATERIAL.get(r.material, ""), _item_text(r.item), r.test_type,
            str(getattr(r, "method", "") or ""), _q(r.qty) if r.qty else "-",
            r.unit, r.frequency, r.calc_basis,
            str(r.count_site) if r.count_site else "", str(r.count_external) if r.count_external else "",
            r.count_ks, r.note]


_cell_texts = cell_texts


def merge_plan(rows: list[PlanRow]) -> dict[int, list[tuple[int, int]]]:
    """열 번호 → 세로 병합 구간 목록(본문 행 기준 0부터). 1행짜리 구간도 포함한다.

    - 공종(0): 공종이 같으면 병합.
    - 시험품목(1)·계획물량(4): 같은 공종 안에서 같은 자재·규격(시험품목)과 수량이면 병합.
    - 시험종목(2)·시험방법(3)·시험빈도(6)·산출근거(7): 같은 자재·같은 시험종목의 연속 행(철근 규격 묶음 등)이 글이 같으면 병합.
    - 단위(5): 같은 시험품목이거나 위 묶음이면 병합.
    - 비고(11): 비어 있지 않고 글이 같으며 같은 시험품목이거나 위 묶음이면 병합.
    - 계획시험횟수(8~10)는 행마다 따로 적는다(병합하지 않는다).
    """
    t = [_cell_texts(r) for r in rows]
    n = len(rows)

    def same_work(a, b):
        return t[a][0] == t[b][0]

    def same_item(a, b):
        return same_work(a, b) and rows[a].item == rows[b].item

    def same_test(a, b):
        return same_work(a, b) and rows[a].material == rows[b].material and rows[a].test_type == rows[b].test_type

    plan = {C_WORK: _runs(n, same_work)}
    for c in (C_ITEM, C_QTY):
        plan[c] = _runs(n, lambda a, b, c=c: same_item(a, b) and t[a][c] == t[b][c])
    for c in (C_TEST, C_METHOD, C_FREQ, C_BASIS):
        plan[c] = _runs(n, lambda a, b, c=c: same_test(a, b) and t[a][c] == t[b][c])
    plan[C_UNIT] = _runs(n, lambda a, b: t[a][C_UNIT] == t[b][C_UNIT] and (same_item(a, b) or same_test(a, b)))
    plan[C_NOTE] = _runs(n, lambda a, b: bool(t[a][C_NOTE]) and t[a][C_NOTE] == t[b][C_NOTE]
                         and (same_item(a, b) or same_test(a, b)))
    for c in (C_SITE, C_EXT, C_KS):
        plan[c] = [(i, i) for i in range(n)]
    return plan


def _text_height_mm(text: str, width_mm: float, pt: float, vertical: bool = False) -> float:
    """셀 글이 차지할 높이 추정(mm). 한글 1em, 영숫자·기호 0.55em, 낱말 단위 줄바꿈·대체 글꼴 여유 35%, 줄 높이 1.3em.

    선언 높이가 실제와 비슷해야 뷰어마다(한컴·rhwp) 쪽 나눔과 다음 문단 위치가 어긋나지 않는다.
    """
    em = pt * 25.4 / 72
    n = len(text.replace(" ", "")) if vertical else _line_count(text, width_mm, pt)
    return n * em * 1.3 + CELL_PAD_MM[2] + CELL_PAD_MM[3]


def _line_count(text: str, width_mm: float, pt: float, slack: float = 1.35) -> int:
    """칸 안 줄 수 추정(한글 1em, 영숫자·기호 0.55em, slack = 낱말 단위 줄바꿈·대체 글꼴 여유)."""
    em = pt * 25.4 / 72
    inner = width_mm - CELL_PAD_MM[0] - CELL_PAD_MM[1]
    n = 0
    for line in (text.split("\n") if text else [""]):
        w = slack * sum(em * (1.0 if ord(ch) > 0x2E80 else 0.55) for ch in line)
        n += max(1, -(-int(w * 100) // int(inner * 100)))
    return n


def _cell_pt(c: int, text: str, width_mm: float) -> float:
    """8.11 칸 글자 크기. 시험항목은 두 줄에 안 들어가면 줄여 쓴다(정본처럼 접는 대신 작게)."""
    if c in SMALL_COLS:
        return PT["small"]
    if c == 1:
        for pt in ITEM_PT_STEPS:
            if _line_count(text, width_mm, pt, slack=1.1) <= ITEM_MAX_LINES:
                return pt
        return ITEM_PT_STEPS[-1]
    return PT["body"]


def _row_heights(texts: list[list[str]], plan: dict[int, list[tuple[int, int]]],
                 widths: list[float]) -> tuple[list[int], set[int]]:
    """본문 행 높이(HWPUNIT)와 세로로 쌓을 공종 구간의 시작 행.

    1행 칸은 그 행을, 병합 칸은 모자라는 만큼 마지막 행을 늘린다. 공종은 다른 칸이 정한 높이 안에
    한 글자씩 쌓아 들어가면 세로로, 아니면 가로로 줄바꿈해 적는다(공종 때문에 행이 늘어나지 않게).
    """
    need = [BODY_ROW_MM] * len(texts)

    def grow(c, s, e, vertical=False):
        pt = _cell_pt(c, texts[s][c], widths[c])
        short = _text_height_mm(texts[s][c], widths[c], pt, vertical) - sum(need[s:e + 1])
        if short > 0:
            need[e] += short

    for c, s, e in sorted(((c, s, e) for c, runs in plan.items() if c for s, e in runs), key=lambda x: x[2] - x[1]):
        grow(c, s, e)
    vertical = set()
    for s, e in plan[0]:
        stacked = _text_height_mm(texts[s][0], widths[0], PT["body"], vertical=True)
        if e - s + 1 >= VERTICAL_WORK_MIN_ROWS and stacked <= sum(need[s:e + 1]):
            vertical.add(s)
        else:
            grow(0, s, e)
    return [_hu(x) for x in need], vertical


def _table_height_mm(rows: list[PlanRow], widths: list[float]) -> float:
    """표 한 개(머리 2행 + rows)의 선언 높이(mm). 병합은 rows 안에서만 계산한다."""
    heights, _ = _row_heights([_cell_texts(r) for r in rows], merge_plan(rows), widths)
    return 2 * HEAD_ROW_MM + sum(heights) / MM


def page_chunks(rows: list[PlanRow], widths: list[float], first_mm: float, page_mm: float) -> list[list[PlanRow]]:
    """rows 를 쪽마다 하나씩 들어갈 묶음으로 나눈다(첫 묶음은 first_mm, 나머지는 page_mm 높이 안).

    쪽마다 표를 따로 만들어 병합을 새로 시작한다 — 정본처럼 쪽이 넘어가도 공종·시험항목 이름이 그 쪽에 보인다
    (한 표의 병합 칸이 쪽을 넘으면 뷰어는 이어지는 쪽 칸을 비워 둔다). 한 행이 한 쪽보다 커도 최소 한 행은 싣는다.
    """
    out, i, budget = [], 0, first_mm
    while i < len(rows):
        j = i + 1
        while j < len(rows) and _table_height_mm(rows[i:j + 1], widths) <= budget:
            j += 1
        out.append(rows[i:j])
        i, budget = j, page_mm
    return out


def _table(st: _Styles, rows: list[PlanRow], widths: list[float]) -> etree._Element:
    ncol, n = len(HEAD), len(rows)
    nrow = n + 2
    w = [_hu(x) for x in widths]
    hh = _hu(HEAD_ROW_MM)

    def bdr(r0, c0, rs, cs):
        return st.border(LINE_OUTER if c0 == 0 else LINE_INNER,
                         LINE_OUTER if c0 + cs == ncol else LINE_INNER,
                         LINE_OUTER if r0 == 0 else LINE_INNER,
                         LINE_OUTER if r0 + rs == nrow else LINE_INNER)

    cells: dict[int, list[etree._Element]] = {i: [] for i in range(nrow)}

    def put(r0, c0, rs, cs, text, *, height, align, pt, bold=False, header=False, vertical=False):
        cells[r0].append(_cell(st, text, col=c0, row=r0, colspan=cs, rowspan=rs, width=sum(w[c0:c0 + cs]),
                               height=height, border=bdr(r0, c0, rs, cs), align=align, pt=pt, bold=bold,
                               header=header, vertical=vertical))

    hp = PT["head"]
    for r0, c0, rs, cs, h in HEAD_CELLS:
        put(r0, c0, rs, cs, h, height=rs * hh, align="CENTER", pt=hp, header=True)

    texts = [_cell_texts(r) for r in rows]
    plan = merge_plan(rows)
    heights, vertical_work = _row_heights(texts, plan, widths)
    for c in range(ncol):
        for s, e in plan[c]:
            span = e - s + 1
            vertical = c == 0 and s in vertical_work
            put(s + 2, c, span, 1, texts[s][c], height=sum(heights[s:e + 1]), align=ALIGN[c],
                pt=_cell_pt(c, texts[s][c], widths[c]), vertical=vertical)

    tbl = etree.Element(f"{HP}tbl", id=str(next(_ids)), zOrder="0", numberingType="TABLE", textWrap="TOP_AND_BOTTOM",
                        textFlow="BOTH_SIDES", lock="0", dropcapstyle="None", pageBreak="CELL", repeatHeader="1",
                        rowCnt=str(nrow), colCnt=str(ncol), cellSpacing="0", borderFillIDRef=st.border(None, None, None, None),
                        noAdjust="0")
    etree.SubElement(tbl, f"{HP}sz", width=str(sum(w)), widthRelTo="ABSOLUTE", height=str(2 * hh + sum(heights)),
                     heightRelTo="ABSOLUTE", protect="0")
    etree.SubElement(tbl, f"{HP}pos", treatAsChar="0", affectLSpacing="0", flowWithText="1", allowOverlap="0",
                     holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="COLUMN", vertAlign="TOP", horzAlign="LEFT",
                     vertOffset="0", horzOffset="0")
    etree.SubElement(tbl, f"{HP}outMargin", left="0", right="0", top="0", bottom=str(_hu(TABLE_GAP_MM)))
    l, r, t, b = (_hu(v) for v in CELL_PAD_MM)
    etree.SubElement(tbl, f"{HP}inMargin", left=str(l), right=str(r), top=str(t), bottom=str(b))
    for i in range(nrow):
        tr = etree.SubElement(tbl, f"{HP}tr")
        for tc in sorted(cells[i], key=lambda e: int(e.find(f"{HP}cellAddr").get("colAddr"))):
            tr.append(tc)
    return tbl


def grid_table(st: _Styles, widths_mm: list[float], heights_mm: list[float], cells: list[dict], *,
               repeat_header: int = 0, gap_mm: float = 0) -> etree._Element:
    """범용 표(계획서 앞쪽·절 개요 칸 등). cells: dict(r, c, text, rs=1, cs=1, align, pt, bold, valign,
    border=(좌, 우, 위, 아래) 굵기 또는 None, pad=(좌, 우, 위, 아래) mm, lines=[(글, 문단 id)]).
    덮인 칸은 쓰지 않는다(8.11 표와 같은 병합 방식). repeat_header 행 수만큼 머리행을 쪽마다 반복한다."""
    w = [_hu(x) for x in widths_mm]
    h = [_hu(x) for x in heights_mm]
    rows: dict[int, list[etree._Element]] = {i: [] for i in range(len(h))}
    for c in cells:
        r0, c0, rs, cs = c["r"], c["c"], c.get("rs", 1), c.get("cs", 1)
        tc = _cell(st, c.get("text", ""), col=c0, row=r0, colspan=cs, rowspan=rs, width=sum(w[c0:c0 + cs]),
                   height=sum(h[r0:r0 + rs]), border=st.border(*c.get("border", (None,) * 4)),
                   align=c.get("align", "CENTER"), pt=c.get("pt", PT["body"]), bold=c.get("bold", False),
                   header=r0 < repeat_header, valign=c.get("valign", "CENTER"), pad=c.get("pad"), lines=c.get("lines"))
        rows[r0].append(tc)
    tbl = etree.Element(f"{HP}tbl", id=str(next(_ids)), zOrder="0", numberingType="TABLE", textWrap="TOP_AND_BOTTOM",
                        textFlow="BOTH_SIDES", lock="0", dropcapstyle="None", pageBreak="CELL",
                        repeatHeader="1" if repeat_header else "0", rowCnt=str(len(h)), colCnt=str(len(w)),
                        cellSpacing="0", borderFillIDRef=st.border(None, None, None, None), noAdjust="0")
    etree.SubElement(tbl, f"{HP}sz", width=str(sum(w)), widthRelTo="ABSOLUTE", height=str(sum(h)),
                     heightRelTo="ABSOLUTE", protect="0")
    etree.SubElement(tbl, f"{HP}pos", treatAsChar="0", affectLSpacing="0", flowWithText="1", allowOverlap="0",
                     holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="COLUMN", vertAlign="TOP", horzAlign="LEFT",
                     vertOffset="0", horzOffset="0")
    etree.SubElement(tbl, f"{HP}outMargin", left="0", right="0", top="0", bottom=str(_hu(gap_mm)))
    l, r, t, b = (_hu(v) for v in CELL_PAD_MM)
    etree.SubElement(tbl, f"{HP}inMargin", left=str(l), right=str(r), top=str(t), bottom=str(b))
    for i in range(len(h)):
        tr = etree.SubElement(tbl, f"{HP}tr")
        for tc in sorted(rows[i], key=lambda e: int(e.find(f"{HP}cellAddr").get("colAddr"))):
            tr.append(tc)
    return tbl


def hold(tbl: etree._Element, para_id: str, char_id: str, *, page_break: bool = False) -> etree._Element:
    """표를 담은 문단(본문에 붙일 때)."""
    holder = _para("", para_id, char_id, page_break=page_break)
    run = holder.find(f"{HP}run")
    run.remove(run.find(f"{HP}t"))
    run.append(tbl)
    etree.SubElement(run, f"{HP}t")
    return holder


def unlisted_items(uncovered=(), owner_standard_needed=(), site_measurements=(), rule_miss=()) -> list[dict]:
    """CLI 요약(uncovered_materials·unmatched_in_covered·owner_standard_needed·site_measurements_to_confirm)을 add_unlisted_table 항목으로."""
    out = [{"kind": "uncovered", "label": u["label"], "basis": f"별표2 p.{u['page']}" if u.get("page") else "별표2",
            "lines": u.get("lines")} for u in uncovered]
    out += [{"kind": "rule_miss", "label": u["label"], "basis": f"별표2 p.{u['page']}" if u.get("page") else "별표2",
             "lines": u.get("lines")} for u in rule_miss]
    out += [{"kind": "owner_standard", "label": x["label"], "basis": "별표2 밖", "lines": x.get("lines")}
            for x in owner_standard_needed]
    out += [{"kind": "site_measurement", "label": m["label"], "basis": m.get("basis", "별표2 밖"), "lines": m.get("lines")}
            for m in site_measurements]
    return out


def _unlisted_texts(it: dict) -> list[str]:
    kind, action = UNLISTED_KINDS.get(it.get("kind", ""), (it.get("kind", ""), ""))
    lines = it.get("lines")
    return [kind, it.get("label", ""), it.get("basis", ""), f"{lines:,}" if isinstance(lines, int) else "-",
            it.get("action") or action]


def _unlisted_table(st: _Styles, items: list[dict], widths: list[float]) -> etree._Element:
    """머리 1행 + 항목 행. 선·글꼴·여백은 8.11 표와 같다(바깥 0.4mm·안 0.2mm, 함초롬돋움 8/7pt)."""
    ncol, nrow = len(UNLISTED_HEAD), len(items) + 1
    w = [_hu(x) for x in widths]
    texts = [UNLISTED_HEAD] + [_unlisted_texts(it) for it in items]
    heights = [_hu(HEAD_ROW_MM)]
    for t in texts[1:]:
        heights.append(_hu(max([BODY_ROW_MM] + [
            _text_height_mm(t[c], widths[c], PT["small"] if c in UNLISTED_SMALL_COLS else PT["body"]) for c in range(ncol)])))
    tbl = etree.Element(f"{HP}tbl", id=str(next(_ids)), zOrder="0", numberingType="TABLE", textWrap="TOP_AND_BOTTOM",
                        textFlow="BOTH_SIDES", lock="0", dropcapstyle="None", pageBreak="CELL", repeatHeader="1",
                        rowCnt=str(nrow), colCnt=str(ncol), cellSpacing="0", borderFillIDRef=st.border(None, None, None, None),
                        noAdjust="0")
    etree.SubElement(tbl, f"{HP}sz", width=str(sum(w)), widthRelTo="ABSOLUTE", height=str(sum(heights)),
                     heightRelTo="ABSOLUTE", protect="0")
    etree.SubElement(tbl, f"{HP}pos", treatAsChar="0", affectLSpacing="0", flowWithText="1", allowOverlap="0",
                     holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="COLUMN", vertAlign="TOP", horzAlign="LEFT",
                     vertOffset="0", horzOffset="0")
    etree.SubElement(tbl, f"{HP}outMargin", left="0", right="0", top="0", bottom=str(_hu(TABLE_GAP_MM)))
    l, r, t, b = (_hu(v) for v in CELL_PAD_MM)
    etree.SubElement(tbl, f"{HP}inMargin", left=str(l), right=str(r), top=str(t), bottom=str(b))
    for i, row in enumerate(texts):
        tr = etree.SubElement(tbl, f"{HP}tr")
        for c, text in enumerate(row):
            border = st.border(LINE_OUTER if c == 0 else LINE_INNER, LINE_OUTER if c == ncol - 1 else LINE_INNER,
                               LINE_OUTER if i == 0 else LINE_INNER, LINE_OUTER if i == nrow - 1 else LINE_INNER)
            head = i == 0
            tr.append(_cell(st, text, col=c, row=i, colspan=1, rowspan=1, width=w[c], height=heights[i],
                            border=border, align="CENTER" if head else UNLISTED_ALIGN[c],
                            pt=PT["head"] if head or c not in UNLISTED_SMALL_COLS else PT["small"], header=head))
    return tbl


def add_unlisted_table(doc: HwpxDocument, section, items: list[dict] | None, *, title: str = UNLISTED_TITLE,
                       body_w_mm: float | None = None) -> bool:
    """구역 끝에 "시험계획 미작성 자재" 제목과 작은 표를 붙인다. 항목이 없으면 아무것도 넣지 않고 False.

    항목(dict): kind(uncovered|owner_standard|site_measurement — 모르는 값은 그대로 구분 칸에), label(자재),
    basis(근거: "별표2 p.N"·"별표2 밖" 등), lines(내역 행 수, 없으면 "-"), action(생략 시 kind 기본 조치).
    CLI 요약에서 만들 때는 unlisted_items() 를 쓴다.
    """
    if not items:
        return False
    st = _Styles(doc)
    body_w = body_w_mm or sum(UNLISTED_WIDTHS_MM)
    widths = [x * body_w / sum(UNLISTED_WIDTHS_MM) for x in UNLISTED_WIDTHS_MM]
    left = st.para("LEFT", 130)
    body = section.element
    body.append(_para(f"[{title}]", left, st.char(PT["discipline"])))
    holder = _para("", left, st.char(PT["body"]))
    run = holder.find(f"{HP}run")
    run.remove(run.find(f"{HP}t"))
    run.append(_unlisted_table(st, items, widths))
    etree.SubElement(run, f"{HP}t")
    body.append(holder)
    section.mark_dirty()
    return True


def _image_size(data: bytes) -> tuple[int, int]:
    """PNG·JPEG 픽셀 크기(표준 라이브러리만). 모르는 형식이면 ValueError."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker, seg = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
            i += 2 + seg
    raise ValueError("로고는 PNG 또는 JPEG 파일이어야 합니다")


def _logo_run(doc: HwpxDocument, sec, logo: str | Path, box_mm: tuple[float, float]) -> etree._Element:
    """로고 파일을 BinData로 넣고, 상자 안에 비율을 지켜 맞춘 글자처럼 취급 그림 run 을 돌려준다."""
    path = Path(logo)
    data = path.read_bytes()
    px_w, px_h = _image_size(data)
    scale = min(box_mm[0] / px_w, box_mm[1] / px_h)
    fmt = "png" if data[:4] == b"\x89PNG" else "jpg"
    obj = doc.add_picture(data, fmt, section=sec, width=_hu(px_w * scale), height=_hu(px_h * scale))
    obj.element.set("textWrap", "TOP_AND_BOTTOM")   # 글자처럼 취급 그림: 줄 높이에 그림 높이를 넣게(SQUARE면 rhwp가 글과 겹쳐 그렸다)
    run = obj.element.getparent()
    temp_p = run.getparent()
    temp_p.remove(run)
    temp_p.getparent().remove(temp_p)          # add_picture 가 본문에 만든 임시 문단은 버린다
    return run


def page_header(doc: HwpxDocument, sec, *, doc_title: str = "품질관리계획서",
                title: str = "8.11 검사 및 시험, 모니터링", revision: str = "Rev.0", date: str = "",
                logo: str | Path | None = None, company: str = "", body_w_mm: float | None = None) -> None:
    """sec 의 머리말을 8.11 쪽 머리로 채운다(plan_doc 등 다른 구역에서도 쓸 수 있게 공개).

    3칸 2줄 표: 왼쪽 로고 칸(두 줄 병합, 선 없음) — 그림(logo, 사용자 로컬 PNG/JPG) + 그 아래 회사명(company).
    둘 다 없으면 칸은 비워 둔 채 크기를 유지한다(쪽 머리 선 위치가 로고 유무로 바뀌지 않는다).
    가운데·오른쪽: 1줄 문서명, 2줄 절 제목 / 개정일 [Rev.N] 쪽. 각 줄 아래 0.4mm 선.
    """
    if body_w_mm is None:
        pp = next(sec.element.iter(f"{HP}pagePr"))
        m = pp.find(f"{HP}margin")
        paper = int(pp.get("height" if pp.get("landscape") == "NARROWLY" else "width"))
        body_w_mm = (paper - int(m.get("left")) - int(m.get("right"))) / MM
    st = _Styles(doc)
    logo_run = None
    if logo is not None:
        box = (min(LOGO_BOX_MM[0], LOGO_COL_MM - CELL_PAD_MM[0] - CELL_PAD_MM[1]),
               LOGO_BOX_MM[1] - (company_fit(company)["height_mm"] if company else 0))
        logo_run = _logo_run(doc, sec, logo, box)
    doc.page.set_header(text=" ", section=sec)
    _fill_story(sec, "header", [_page_header(st, doc_title, title, _meta_text(date, revision), body_w_mm,
                                             logo_run=logo_run, company=company)])


def _text_w_mm(text: str, pt: float, ratio: int = 100) -> float:
    """한 줄 글 폭 추정(mm): 한글 1em, 빈칸 0.35em, 그 밖 0.55em(rhwp 렌더 실측보다 약 1.5% 넉넉하다) × 장평."""
    em = pt * 25.4 / 72 * ratio / 100
    return sum(em * (1.0 if ord(c) > 0x2E80 else 0.35 if c == " " else 0.55) for c in text)


def _fit_pt(text: str, width_mm: float, pt: float, min_pt: float = 9) -> float:
    """한 줄에 들어가게 글자 크기를 줄인다(쪽 머리 절 제목이 두 줄로 접히면 선과 겹친다). 0.5pt 단위."""
    while pt > min_pt and _text_w_mm(text, pt) > width_mm:
        pt -= 0.5
    return pt


def _two_lines(text: str, pt: float, ratio: int, by_word: bool) -> tuple[str, str]:
    """두 줄로 나눈 (윗줄, 아랫줄) 중 넓은 줄이 가장 좁은 것. 이어 붙이면 원래 글 그대로(빈칸은 윗줄 끝에 남긴다)."""
    if by_word:
        toks = re.findall(r"\S+\s*", text)
        cuts = [len("".join(toks[:i])) for i in range(1, len(toks))]
    else:
        cuts = [k for k in range(1, len(text)) if text[:k].strip() and text[k:].strip() and not text[k].isspace()]
    if not cuts:
        return text, ""
    k = min(cuts, key=lambda k: max(_text_w_mm(text[:k].rstrip(), pt, ratio), _text_w_mm(text[k:], pt, ratio)))
    return text[:k], text[k:]


def company_fit(company: str, width_mm: float | None = None) -> dict:
    """쪽 머리 로고 칸 회사명의 글자 크기·장평·줄(COMPANY_* 설명 순서). height_mm = 회사명 칸 높이.

    어느 단계에도 안 들어가면(아주 긴 이름) 하한(6pt·장평 70%·글자 경계 두 줄)으로 두고 fits=False.
    """
    width_mm = LOGO_COL_MM - CELL_PAD_MM[0] - CELL_PAD_MM[1] if width_mm is None else width_mm

    def ok(lines, pt, ratio):
        def w(x):
            han = "".join(c for c in x if ord(c) > 0x2E80)
            return _text_w_mm(han, pt, ratio) + (_text_w_mm(x, pt, ratio) - _text_w_mm(han, pt, ratio)) * COMPANY_SLACK
        return all(w(x.rstrip()) <= width_mm for x in lines)

    def result(lines, pt, ratio, fits=True):
        em = pt * 25.4 / 72
        h = max(COMPANY_LINE_MM, math.ceil((len(lines) * em * 1.2 + 0.1) * 10) / 10)   # 문단 줄 간격 120%
        return dict(pt=pt, ratio=ratio, lines=lines, height_mm=h, fits=fits)

    for pt in COMPANY_PT_STEPS:
        if ok([company], pt, 100):
            return result([company], pt, 100)
    steps = [(pt, 100) for pt in COMPANY_PT_STEPS] + [(COMPANY_PT_STEPS[-1], r) for r in COMPANY_RATIO_STEPS[1:]]
    for by_word in (True, False):
        for pt, ratio in steps:
            lines = [x for x in _two_lines(company, pt, ratio, by_word) if x]
            if ok(lines, pt, ratio):
                return result(lines, pt, ratio)
    pt, ratio = steps[-1]
    return result([x for x in _two_lines(company, pt, ratio, False) if x], pt, ratio, fits=False)


def _page_header(st: _Styles, doc_title: str, title: str, meta: str, body_w_mm: float, *,
                 logo_run: etree._Element | None = None, company: str = "") -> etree._Element:
    """쪽 머리 표(문단 하나에 담아 돌려준다). 모양은 page_header 설명."""
    width = _hu(body_w_mm)
    logo_w, right_w = _hu(LOGO_COL_MM), _hu(HEADER_META_MM)
    mid_w = width - logo_w - right_w
    tbl = etree.Element(f"{HP}tbl", id=str(next(_ids)), zOrder="0", numberingType="TABLE", textWrap="TOP_AND_BOTTOM",
                        textFlow="BOTH_SIDES", lock="0", dropcapstyle="None", pageBreak="NONE", repeatHeader="0",
                        rowCnt="2", colCnt="3", cellSpacing="0", borderFillIDRef=st.border(None, None, None, None),
                        noAdjust="0")
    h0, h1 = (_hu(x) for x in HEADER_ROWS_MM)
    etree.SubElement(tbl, f"{HP}sz", width=str(width), widthRelTo="ABSOLUTE", height=str(h0 + h1),
                     heightRelTo="ABSOLUTE", protect="0")
    etree.SubElement(tbl, f"{HP}pos", treatAsChar="1", affectLSpacing="0", flowWithText="1", allowOverlap="0",
                     holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="COLUMN", vertAlign="TOP", horzAlign="LEFT",
                     vertOffset="0", horzOffset="0")
    etree.SubElement(tbl, f"{HP}outMargin", left="0", right="0", top="0", bottom="0")
    etree.SubElement(tbl, f"{HP}inMargin", left="0", right="0", top="0", bottom="0")
    line, none = st.border(None, None, None, LINE_OUTER), st.border(None, None, None, None)

    logo_cell = _cell(st, "", col=0, row=0, colspan=1, rowspan=2, width=logo_w, height=h0 + h1, border=none,
                      align="CENTER", pt=PT["company"])
    if logo_run is not None or company:
        # 그림과 회사명은 로고 칸 안의 1열 표 두 줄에 따로 둔다(한 셀에 그림 문단+글 문단을 쌓으면 rhwp가 겹쳐 그렸다)
        inner_w = logo_w - _hu(CELL_PAD_MM[0] + CELL_PAD_MM[1])
        fit = company_fit(company) if company else None
        name_h = _hu(fit["height_mm"]) if fit else 0
        parts = []
        if logo_run is not None:
            parts.append(("pic", h0 + h1 - name_h - _hu(1.0)))
        if company:
            parts.append(("name", name_h))
        inner = etree.Element(f"{HP}tbl", id=str(next(_ids)), zOrder="0", numberingType="TABLE",
                              textWrap="TOP_AND_BOTTOM", textFlow="BOTH_SIDES", lock="0", dropcapstyle="None",
                              pageBreak="NONE", repeatHeader="0", rowCnt=str(len(parts)), colCnt="1", cellSpacing="0",
                              borderFillIDRef=none, noAdjust="0")
        etree.SubElement(inner, f"{HP}sz", width=str(inner_w), widthRelTo="ABSOLUTE",
                         height=str(sum(h for _, h in parts)), heightRelTo="ABSOLUTE", protect="0")
        etree.SubElement(inner, f"{HP}pos", treatAsChar="1", affectLSpacing="0", flowWithText="1", allowOverlap="0",
                         holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="COLUMN", vertAlign="TOP",
                         horzAlign="LEFT", vertOffset="0", horzOffset="0")
        etree.SubElement(inner, f"{HP}outMargin", left="0", right="0", top="0", bottom="0")
        etree.SubElement(inner, f"{HP}inMargin", left="0", right="0", top="0", bottom="0")
        for i, (kind, h) in enumerate(parts):
            name_lines = None
            if kind == "name":
                cid = st.char(fit["pt"], True, fit["ratio"])
                name_lines = [([(x, cid)], st.para("CENTER", 120)) for x in fit["lines"]]
            tc = _cell(st, "", col=0, row=i, colspan=1, rowspan=1, width=inner_w,
                       height=h, border=none, align="CENTER", pt=PT["company"], bold=True, lines=name_lines)
            for m in ("left", "right", "top", "bottom"):
                tc.find(f"{HP}cellMargin").set(m, "0")
            if kind == "pic":
                run = tc.find(f"{HP}subList/{HP}p/{HP}run")
                run.getparent().replace(run, logo_run)
            etree.SubElement(inner, f"{HP}tr").append(tc)
        run = logo_cell.find(f"{HP}subList/{HP}p/{HP}run")
        run.remove(run.find(f"{HP}t"))
        run.append(inner)
        etree.SubElement(run, f"{HP}t")
    tr0 = etree.SubElement(tbl, f"{HP}tr")
    tr0.append(logo_cell)
    tr0.append(_cell(st, doc_title, col=1, row=0, colspan=2, rowspan=1, width=mid_w + right_w, height=h0, border=line,
                     align="LEFT", pt=PT["doc_title"], bold=True, pad=HEADER_PAD_MM["doc"]))
    tr1 = etree.SubElement(tbl, f"{HP}tr")
    tr1.append(_cell(st, title, col=1, row=1, colspan=1, rowspan=1, width=mid_w, height=h1, border=line,
                     align="LEFT", pt=_fit_pt(title, mid_w / MM - sum(HEADER_PAD_MM["title"][:2]), PT["title"]),
                     pad=HEADER_PAD_MM["title"]))
    right = _cell(st, meta, col=2, row=1, colspan=1, rowspan=1, width=right_w, height=h1, border=line,
                  align="RIGHT", pt=PT["meta"], pad=HEADER_PAD_MM["meta"])
    p = right.find(f"{HP}subList/{HP}p")
    cid = st.char(PT["meta"])
    num_run = etree.SubElement(p, f"{HP}run", charPrIDRef=cid)
    ctrl = etree.SubElement(num_run, f"{HP}ctrl")
    auto = etree.SubElement(ctrl, f"{HP}autoNum", num="1", numType="PAGE")
    etree.SubElement(auto, f"{HP}autoNumFormat", type="DIGIT", userChar="", prefixChar="", suffixChar="",
                     supscript="0")
    tail = etree.SubElement(p, f"{HP}run", charPrIDRef=cid)
    etree.SubElement(tail, f"{HP}t").text = "p."
    tr1.append(right)
    for tc in tbl.iter(f"{HP}tc"):
        if tc.getparent().getparent() is tbl:
            tc.find(f"{HP}subList").set("vertAlign", "CENTER" if tc is logo_cell else "BOTTOM")
    holder = _para("", st.para("LEFT", 100), st.char(PT["meta"]))
    run = holder.find(f"{HP}run")
    run.remove(run.find(f"{HP}t"))
    run.append(tbl)
    etree.SubElement(run, f"{HP}t")
    return holder


def _fill_story(sec, tag: str, paragraphs: list[etree._Element]) -> None:
    """page.set_header/set_footer 로 만든 머리말·꼬리말(secPr 안 원본과 본문 ctrl 사본) 내용을 바꾼다."""
    for story in sec.element.iter(f"{HP}{tag}"):
        sub = story.find(f"{HP}subList")
        for ch in list(sub):
            sub.remove(ch)
        for p in paragraphs:
            q = deepcopy(p)
            for e in q.iter(f"{HP}p", f"{HP}tbl", f"{HP}pic"):
                e.set("id", str(next(_ids)))
                if e.get("instid") is not None:
                    e.set("instid", e.get("id"))
            sub.append(q)
    sec.mark_dirty()


def _set_orientation(sec, landscape: bool) -> None:
    """A4 방향을 한컴 방식으로 쓴다: width·height 는 늘 세로 용지 치수, 방향은 landscape 속성.

    OWPML pagePr@landscape 값은 WIDELY|NARROWLY 두 가지다(python-hwpx 는 세로에 스키마 밖 "PORTRAIT"를 쓴다).
    새 문서 기본값(한컴 실물 유래)이 세로 = WIDELY + 세로 치수이고, rhwp 0.8.6 렌더에서
    NARROWLY + 세로 치수 → 가로 쪽(841.89×595.28pt), WIDELY + 세로 치수 → 세로 쪽으로 나온다(L3-T1 실측).
    """
    pp = next(e for e in sec.element.iter(f"{HP}pagePr"))
    pp.set("landscape", "NARROWLY" if landscape else "WIDELY")
    pp.set("width", str(_hu(A4_MM[0])))
    pp.set("height", str(_hu(A4_MM[1])))
    sec.mark_dirty()


def add_811_tables(doc: HwpxDocument, rows: list[PlanRow], *, section=None, title: str = "8.11 검사 및 시험, 모니터링",
                   basis_version: str = "", generated_note: str = "", revision: str = "Rev.0", date: str = "",
                   doc_title: str = "품질관리계획서", section_title: str = "1. 품질시험 및 검사계획",
                   landscape: bool = False, logo: str | Path | None = None, company: str = "",
                   unlisted: list[dict] | None = None, new_page: bool = False, notice_footer: bool = False):
    """doc 의 한 구역(section, 기본 마지막 구역)에 8.11 쪽 설정·쪽 머리·꼬리말·분야별 표를 채운다.

    기본은 원본 계획서와 같은 A4 세로(명세). landscape=True 면 A4 가로로 두고 열 너비를 본문폭에 비례해 넓힌다.
    unlisted 가 있으면 분야별 표 뒤(근거 주석 앞)에 "시험계획 미작성 자재" 표를 붙인다(add_unlisted_table).
    new_page=True 면 절 번호 줄("1. 품질시험 및 검사계획")부터 새 쪽에서 시작한다(계획서 안 8.11, 정본과 같음).
    반환: 채운 구역.
    """
    sec = section if section is not None else doc.sections[-1]
    doc.page.setup(section=sec, **PAGE)
    _set_orientation(sec, landscape)
    paper_w = A4_MM[1] if landscape else A4_MM[0]
    body_w = paper_w - PAGE["margin_left_mm"] - PAGE["margin_right_mm"]
    widths = [x * body_w / sum(WIDTHS_MM) for x in WIDTHS_MM]
    st = _Styles(doc)

    page_header(doc, sec, doc_title=doc_title, title=title, revision=revision, date=date, logo=logo,
                company=company, body_w_mm=body_w)
    if notice_footer:
        doc.page.set_footer(text=" ", section=sec)
        _fill_story(sec, "footer", [_para(NOTICE, st.para("CENTER", 100), st.char(PT["footer"]))])

    body = sec.element
    left, left_c = st.para("LEFT", 130), st.char(PT["section"])
    head_p = _para(section_title, left, left_c, page_break=new_page)
    first = body.findall(f"{HP}p")
    if len(first) == 1 and not "".join(first[0].itertext()).strip():
        # 빈 구역(build_811): 구역 설정만 담은 첫 문단에 합친다 — 따로 두면 빈 줄 5.6mm 만큼 본문이 내려간다
        first[0].set("paraPrIDRef", left)
        for run in head_p.findall(f"{HP}run"):
            first[0].append(run)
    else:
        body.append(head_p)

    # 쪽 본문 높이와 표 앞 줄(10pt 130%) 높이로 쪽마다 들어갈 행을 정한다(page_chunks)
    paper_h = A4_MM[0] if landscape else A4_MM[1]
    page_mm = (paper_h - PAGE["margin_top_mm"] - PAGE["header_margin_mm"] - PAGE["margin_bottom_mm"]
               - PAGE["footer_margin_mm"] - TABLE_GAP_MM - PAGE_SAFETY_MM)
    line_mm = PT["section"] * 25.4 / 72 * 1.3
    disciplines = list(dict.fromkeys(r.discipline for r in rows))
    for k, disc in enumerate(disciplines):
        body.append(_para(f"[{disc}공사]", left, st.char(PT["discipline"]), page_break=k > 0))
        first_mm = page_mm - line_mm * (2 if k == 0 else 1)          # 첫 분야는 절 번호 줄도 같은 쪽
        for m, chunk in enumerate(page_chunks([r for r in rows if r.discipline == disc], widths, first_mm, page_mm)):
            body.append(hold(_table(st, chunk, widths), left, st.char(PT["body"]), page_break=m > 0))
    add_unlisted_table(doc, sec, unlisted, body_w_mm=body_w)

    note_c = st.char(PT["note"])
    if basis_version:
        body.append(_para(f"근거 기준: {basis_version}", left, note_c))
    if generated_note:
        body.append(_para(generated_note, left, note_c))
    sec.mark_dirty()
    return sec


def build_811(rows: list[PlanRow], out: str | Path, *, title: str = "8.11 검사 및 시험, 모니터링",
              basis_version: str = "", generated_note: str = "", revision: str = "Rev.0", date: str = "",
              doc_title: str = "품질관리계획서", section_title: str = "1. 품질시험 및 검사계획",
              landscape: bool = False, logo: str | Path | None = None, company: str = "",
              unlisted: list[dict] | None = None, notice_footer: bool = False) -> Path:
    """8.11 만 담은 HWPX(구역 1개)를 쓴다. 내용은 add_811_tables 가 채운다."""
    doc = HwpxDocument.new()
    add_811_tables(doc, rows, section=doc.sections[0], title=title, basis_version=basis_version,
                   generated_note=generated_note, revision=revision, date=date, doc_title=doc_title,
                   section_title=section_title, landscape=landscape, logo=logo, company=company,
                   unlisted=unlisted, notice_footer=notice_footer)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save_to_path(str(out))
    return out
