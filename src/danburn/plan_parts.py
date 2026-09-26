"""계획서 서식 부품: P2 업무 분장표 · P3 업무 흐름표 · P4 기록 양식.

모양 수치는 정본 계획서 실측(docs/design/plan-layout.md §11~13, 조사 L7-T1 §3)과 1:1로 맞춘다.
입력은 템플릿 절의 선택 필드 roles · flow · forms(인터페이스 L7-schema)이며, 문장은 템플릿이 정한다.
표는 hwpx_out.grid_table 로 만든다. 흐름표의 회색 테 상자와 화살표는 도형 대신 안쪽 표의 칸 선으로 그린다
(도형 개체는 뷰어마다 위치·줄 높이 처리가 달라 한컴 호환을 장담하기 어렵다).
"""
from __future__ import annotations

import re
from copy import deepcopy

from lxml import etree

from . import hwpx_out
from .hwpx_out import HH, HP, LINE_OUTER, LINE_THIN, PAGE, grid_table

BODY_W_MM = 210 - PAGE["margin_left_mm"] - PAGE["margin_right_mm"]                   # 181
LAND_W_MM = 297 - PAGE["margin_left_mm"] - PAGE["margin_right_mm"]                   # 268(가로 양식 쪽)
PAGE_BODY_MM = (297 - PAGE["margin_top_mm"] - PAGE["header_margin_mm"] - PAGE["margin_bottom_mm"]
                - PAGE["footer_margin_mm"])                                           # 240.3
LAND_BODY_MM = PAGE_BODY_MM - 87                                                      # 153.3(가로 쪽 본문 높이)
SAFETY_MM = 1.0                     # 쪽을 채우는 표의 여유(뷰어마다 선 두께만큼 다르다)

# ── P2 업무 분장표(§11) ────────────────────────────────────────────────
ROLE_LEGEND = "○ 작성/주관    ◎ 검토/협조    ● 승인/결정"
ROLE_MARKS = {"○", "◎", "●", ""}
ROLE_ITEM_PCT, ROLE_NOTE_PCT = 16.4, 22.3          # 나머지는 팀 칸이 똑같이 나눈다(정본 팀 5칸 각 12.3)
ROLE_HEAD_MM, ROLE_ROW_MM, ROLE_MIN_ROWS = 8.9, 9.0, 4
ROLE_HEAD_PT, ROLE_ITEM_PT, ROLE_MARK_PT, ROLE_LEGEND_PT = 9, 8.5, 9, 9
ROLE_LEGEND_BEFORE_MM, ROLE_LEGEND_AFTER_MM = 2.5, 1.5

# ── P3 업무 흐름표(§12) ────────────────────────────────────────────────
# 업무단계 · (이중선 간격) · 업무내용 · (이중선 간격) · 관련근거. 정본 38.8 · 1.1 · 113.1 · 1.1 · 26.3 (합 180.4)
# 정본 흐름표는 본문폭보다 좁다(x 16.0~196.4) → 폭을 늘리지 않고 그대로 쓴다(본문 왼끝 16.5 ~ 196.9)
FLOW_COLS_MM = [38.8, 1.1, 113.1, 1.1, 26.3]
FLOW_HEAD = ["업무단계", "", "업 무 내 용", "", "관련근거\n/사용양식"]
FLOW_HEAD_MM, FLOW_HEAD_PT = 10.1, 9.5
FLOW_PT, FLOW_LINE = 9, 140                         # 줄 간격 4.45(정본)
FLOW_BASIS_PT = 8.5
FLOW_PAD_MM = (1.8, 1.0, 1.5, 1.5)
FLOW_BULLET_HANG_MM, FLOW_DASH_LEFT_MM, FLOW_DASH_HANG_MM, FLOW_PAREN_LEFT_MM = 2.5, 2.8, 2.9, 4.2
STAGE_BOX_MM = (37.6, 10.0)                         # 회색 테 상자 폭·높이(정본: 표 왼쪽 선에 붙어 칸을 거의 채운다)
STAGE_LEFT_MM = 0.3                                 # 칸 왼쪽 선에서 상자까지
STAGE_BOX_LINE, STAGE_BOX_COLOR = "1.0 mm", "#A8A8A8"
STAGE_PT = 9.5                                      # 굵게(정본). 테 색은 정본 래스터 값 168(#A8A8A8)과 같다
STAGE_TOP_MM = 1.5                                  # 칸 윗선에서 상자까지
ARROW_MM, ARROW_HEAD_MM, ARROW_LINE = 8.6, 2.6, "0.3 mm"
ARROW_HEAD = "▼"

# ── P4 기록 양식(§13) ─────────────────────────────────────────────────
# 윗부분 31.5 → 윗줄 글 윗끝 약 44, 제목 가운데 약 60, 격자 윗선 69.0 (정본 관리대장형 44.0 · 58.2~ · 69.2)
FORM_TOP_MM = dict(space=6.5, label=5.0, gap=3.0, title=12.0, info=5.0)
FORM_TITLE_APPROVAL_MM = 17.0       # 결재란이 있으면 제목 줄을 결재란 높이로(격자가 5.0 내려간다)
FORM_LABEL_PT, FORM_TITLE_PT, FORM_INFO_PT, FORM_PT = 10, 14.5, 9, 9
FORM_GRID_W_MM = 180.0              # 정본 양식 격자 x 16.0~196.0(본문폭보다 좁다)
FORM_HEAD_MM, FORM_ROW_MM = 8.2, 10.4
APPROVAL = ["담 당", "팀 장", "현장대리인"]
APPROVAL_COL_MM, APPROVAL_HEAD_MM, APPROVAL_SIGN_MM, APPROVAL_PT = 15.0, 5.0, 12.0, 8
FORM_SIDE_MM = APPROVAL_COL_MM * len(APPROVAL) + 2.0   # 제목 양옆 칸(결재란 폭 + 2) → 제목은 쪽 가운데
FORM_FOOT_PT, FORM_FOOT_BEFORE_MM, FORM_FOOT_LINE = 10, 3.0, 160   # 격자 아래 줄(법정 서식 제43호 작성일시·작성자)

NONE4 = (None,) * 4


class PartError(ValueError):
    """서식 부품 입력(roles·flow·forms·팀)이 잘못됐다."""


# ── 공통 ──────────────────────────────────────────────────────────────

def _nest(tc: etree._Element, tbl: etree._Element) -> None:
    """칸 첫 문단에 표를 글자처럼 넣는다(칸 안 표)."""
    tbl.find(f"{HP}pos").set("treatAsChar", "1")
    run = tc.find(f"{HP}subList/{HP}p/{HP}run")
    t = run.find(f"{HP}t")
    if t is not None:
        run.remove(t)
    run.append(tbl)
    etree.SubElement(run, f"{HP}t")


def _cell_at(tbl: etree._Element, r: int, c: int) -> etree._Element:
    for tc in tbl.iter(f"{HP}tc"):
        a = tc.find(f"{HP}cellAddr")
        if tc.getparent().getparent() is tbl and a.get("rowAddr") == str(r) and a.get("colAddr") == str(c):
            return tc
    raise KeyError((r, c))


def _gray_box(st: hwpx_out._Styles) -> str:
    """네 변 회색 굵은 선 borderFill(흐름표 업무단계 상자)."""
    key = ("graybox", STAGE_BOX_LINE, STAGE_BOX_COLOR)
    if key not in st._cache:
        el = etree.Element(f"{HH}borderFill", threeD="0", shadow="0", centerLine="NONE", breakCellSeparateLine="0")
        etree.SubElement(el, f"{HH}slash", type="NONE", Crooked="0", isCounter="0")
        etree.SubElement(el, f"{HH}backSlash", type="NONE", Crooked="0", isCounter="0")
        for side in ("left", "right", "top", "bottom"):
            etree.SubElement(el, f"{HH}{side}Border", type="SOLID", width=STAGE_BOX_LINE, color=STAGE_BOX_COLOR)
        etree.SubElement(el, f"{HH}diagonal", type="NONE", width="0.1 mm", color="#000000")
        st._cache[key] = st._add("borderFills", "borderFill", el)
    return st._cache[key]


def _lines_mm(text: str, width_mm: float, pt: float, line_pct: float) -> float:
    """글 한 문단이 차지할 높이(줄 수 추정 × 줄 간격)."""
    return hwpx_out._line_count(text, width_mm + hwpx_out.CELL_PAD_MM[0] + hwpx_out.CELL_PAD_MM[1], pt) \
        * pt * 25.4 / 72 * line_pct / 100


def form_numbers(sections: list[dict]) -> dict[str, int]:
    """양식 key → 문서 전체 순서 번호(1부터). key 가 겹치면 PartError."""
    nums: dict[str, int] = {}
    for s in sections:
        for f in s.get("forms") or []:
            key = str(f.get("key") or "").strip()
            if not key or not f.get("title"):
                raise PartError(f"{s.get('id')} forms: key·title 이 필요합니다")
            if key in nums:
                raise PartError(f"양식 key 가 겹칩니다: {key}")
            nums[key] = len(nums) + 1
    return nums


def form_ref(text: str, nums: dict[str, int]) -> str:
    """'양식:<key>' → '양식 N'. 모르는 key 는 PartError(빈 참조를 내지 않는다)."""
    def sub(m):
        key = m.group(1)
        if key not in nums:
            raise PartError(f"없는 양식을 가리킵니다: 양식:{key}")
        return f"양식 {nums[key]}"
    return re.sub(r"양식:([A-Za-z0-9_\-]+)", sub, text)


def teams_of(project: dict, tpl: dict) -> list[dict]:
    """분장표 팀 목록 [{key, name}] — project.팀 이 우선, 없으면 template.default_teams."""
    teams = project.get("팀") or tpl.get("default_teams") or []
    out = []
    for t in teams:
        if isinstance(t, str):
            t = {"key": t, "name": t}
        if not t.get("key"):
            raise PartError(f"팀 항목에 key 가 없습니다: {t}")
        out.append({"key": str(t["key"]), "name": str(t.get("name") or t["key"])})
    return out


# ── P2 ───────────────────────────────────────────────────────────────

def add_roles(w, roles: list[dict], teams: list[dict], fill) -> None:
    """개요 칸 아래 업무 분장표: 범례 줄(오른쪽) + 표(항목 · 팀들 · 비고). 최소 4줄(빈 줄로 채움)."""
    if not teams:
        raise PartError("roles 를 그리려면 팀 목록이 필요합니다(project.팀 또는 template.default_teams)")
    keys = {t["key"] for t in teams}
    for r in roles:
        bad = set((r.get("marks") or {})) - keys
        if bad:
            raise PartError(f"분장표 '{r.get('task')}': 팀 목록에 없는 키 {sorted(bad)}")
        badm = {str(v) for v in (r.get("marks") or {}).values()} - ROLE_MARKS
        if badm:
            raise PartError(f"분장표 '{r.get('task')}': 표시는 ○·◎·● 만 씁니다 {sorted(badm)}")
    st = w.st
    n_team = len(teams)
    team_pct = (100 - ROLE_ITEM_PCT - ROLE_NOTE_PCT) / n_team
    widths = [x * BODY_W_MM / 100 for x in [ROLE_ITEM_PCT] + [team_pct] * n_team + [ROLE_NOTE_PCT]]
    m = len(widths)
    rows = [["항 목"] + [t["name"] for t in teams] + ["비 고"]]
    for r in roles:
        marks = r.get("marks") or {}
        rows.append([fill(str(r.get("task", "")))] + [str(marks.get(t["key"], "")) for t in teams]
                    + [fill(str(r.get("note") or ""))])
    rows += [[""] * m for _ in range(ROLE_MIN_ROWS - len(roles))]
    n = len(rows)
    heights = [ROLE_HEAD_MM] + [max(ROLE_ROW_MM, max(_lines_mm(v, widths[c], ROLE_ITEM_PT, 120) + 1.0
                                                     for c, v in enumerate(row))) for row in rows[1:]]
    cells = []
    for i, row in enumerate(rows):
        for c, v in enumerate(row):
            head = i == 0
            cells.append(dict(r=i, c=c, text=v, pt=ROLE_HEAD_PT if head else ROLE_MARK_PT if 0 < c < m - 1 else ROLE_ITEM_PT,
                              align="CENTER" if head or 0 < c < m - 1 else "LEFT" if c == m - 1 else "CENTER",
                              pad=(0.8, 0.8, 0.3, 0.3),
                              border=(LINE_OUTER if c == 0 else LINE_THIN, LINE_OUTER if c == m - 1 else LINE_THIN,
                                      LINE_OUTER if i <= 1 else LINE_THIN, LINE_OUTER if i in (0, n - 1) else LINE_THIN)))
    w.para(ROLE_LEGEND, char=st.char(ROLE_LEGEND_PT),
           para=st.para("RIGHT", 100, before=ROLE_LEGEND_BEFORE_MM, after=ROLE_LEGEND_AFTER_MM))
    w.table(grid_table(st, widths, heights, cells, repeat_header=1))


# ── P3 ───────────────────────────────────────────────────────────────

def _stage_cell_table(st, text: str, arrow: bool) -> etree._Element:
    """업무단계 칸 안: 회색 테 상자(글 가운데) + 아래 화살표(가운데 세로선 + ▼)."""
    bw, bh = STAGE_BOX_MM
    heights = [bh]
    cells = [dict(r=0, c=0, cs=2, text=text, pt=STAGE_PT, bold=True, pad=(0.8, 0.8, 0.3, 0.3), border=NONE4)]
    if arrow:
        heights += [ARROW_MM - ARROW_HEAD_MM, ARROW_HEAD_MM]
        cells += [dict(r=1, c=0, text="", pt=2, border=(None, ARROW_LINE, None, None), pad=(0, 0, 0, 0)),
                  dict(r=1, c=1, text="", pt=2, border=NONE4, pad=(0, 0, 0, 0)),
                  dict(r=2, c=0, cs=2, text=ARROW_HEAD, pt=7, border=NONE4, pad=(0, 0, 0, 0), valign="TOP")]
    tbl = grid_table(st, [bw / 2, bw / 2], heights, cells)
    _cell_at(tbl, 0, 0).set("borderFillIDRef", _gray_box(st))
    for tc in tbl.iter(f"{HP}tc"):                       # 화살촉 줄은 줄 간격 없이 붙인다
        tc.find(f"{HP}cellMargin").set("top", "0")
    return tbl


def _content_lines(st, content: list[str]) -> list[tuple[str, str]]:
    """업무내용 줄 → (글, 문단 모양). '• ' 주 문장(내어쓰기), '- ' 하위(들여씀), '(' 보충(더 들여씀)."""
    p_bullet = st.para("JUSTIFY", FLOW_LINE, indent=-FLOW_BULLET_HANG_MM)
    p_dash = st.para("JUSTIFY", FLOW_LINE, left=FLOW_DASH_LEFT_MM, indent=-FLOW_DASH_HANG_MM)
    p_paren = st.para("JUSTIFY", FLOW_LINE, left=FLOW_PAREN_LEFT_MM)
    p_plain = st.para("JUSTIFY", FLOW_LINE)
    out = []
    for t in content:
        t = str(t)
        s = t.lstrip()
        if s.startswith("•"):
            out.append(("•" + s[1:].lstrip(), p_bullet))
        elif s.startswith("-"):
            out.append(("- " + s[1:].lstrip(), p_dash))
        elif s.startswith("("):
            out.append((s, p_paren))
        else:
            out.append((s, p_plain))
    return out


def _flow_row_mm(stage_arrow: bool, lines: list[tuple[str, str]], basis: list[str]) -> float:
    inner = FLOW_COLS_MM[2] - FLOW_PAD_MM[0] - FLOW_PAD_MM[1]
    text_mm = sum(_lines_mm(t, inner, FLOW_PT, FLOW_LINE) for t, _ in lines) + FLOW_PAD_MM[2] + FLOW_PAD_MM[3]
    basis_mm = sum(_lines_mm(b, FLOW_COLS_MM[4] - 2, FLOW_BASIS_PT, 130) for b in basis) + 3.0
    stage_mm = STAGE_TOP_MM + STAGE_BOX_MM[1] + (ARROW_MM if stage_arrow else 0) + 1.5
    return max(text_mm, basis_mm, stage_mm)


def _flow_chunks(heights: list[float], budget: float) -> list[list[int]]:
    """행 번호를 쪽마다 들어갈 묶음으로(한 행이 쪽보다 커도 최소 한 행)."""
    out, cur, used = [], [], 0.0
    for i, h in enumerate(heights):
        if cur and used + h > budget:
            out.append(cur)
            cur, used = [], 0.0
        cur.append(i)
        used += h
    if cur:
        out.append(cur)
    return out


def add_flow(w, flow: list[dict], nums: dict[str, int], fill) -> None:
    """업무 흐름표. 새 쪽에서 시작하고, 쪽마다 표를 하나씩(머리행 포함) 쪽 끝까지 채운다(정본처럼 마지막 행을 늘림)."""
    st = w.st
    steps = []
    for k, f in enumerate(flow):
        if not f.get("stage"):
            raise PartError(f"flow {k + 1}번째 단계에 stage 가 없습니다")
        lines = _content_lines(st, [fill(x) for x in f.get("content") or []])
        basis = [form_ref(fill(str(b)), nums) for b in f.get("basis") or []]
        steps.append((fill(str(f["stage"])), lines, basis, k < len(flow) - 1))
    heights = [_flow_row_mm(arrow, lines, basis) for _, lines, basis, arrow in steps]
    budget = PAGE_BODY_MM - FLOW_HEAD_MM - SAFETY_MM
    p_basis = st.para("LEFT", 130)
    for m, chunk in enumerate(_flow_chunks(heights, budget)):
        hs = [heights[i] for i in chunk]
        room = budget - sum(hs)
        if room > 0:
            hs[-1] += room                                # 쪽 끝까지(정본 흐름표 쪽)
        n = len(chunk) + 1
        cells = []
        for c, h in enumerate(FLOW_HEAD):
            cells.append(dict(r=0, c=c, text=h, pt=FLOW_HEAD_PT, bold=True, pad=(0.5, 0.5, 0.3, 0.3),
                              border=(LINE_OUTER if c == 0 else LINE_THIN, LINE_OUTER if c == 4 else LINE_THIN,
                                      LINE_OUTER, LINE_THIN)))
        for j, i in enumerate(chunk, 1):
            stage, lines, basis, arrow = steps[i]
            bottom = LINE_OUTER if j == n - 1 else LINE_THIN

            def bd(c):
                return (LINE_OUTER if c == 0 else LINE_THIN, LINE_OUTER if c == 4 else LINE_THIN, LINE_THIN, bottom)
            cells += [
                dict(r=j, c=0, text="", pt=2, valign="TOP", pad=(STAGE_LEFT_MM, 0, STAGE_TOP_MM, 0), border=bd(0)),
                dict(r=j, c=1, text="", pt=2, pad=(0, 0, 0, 0), border=bd(1)),
                dict(r=j, c=2, text="", lines=lines or None, pt=FLOW_PT, align="LEFT", valign="TOP",
                     pad=FLOW_PAD_MM, border=bd(2)),
                dict(r=j, c=3, text="", pt=2, pad=(0, 0, 0, 0), border=bd(3)),
                dict(r=j, c=4, text="", lines=[(f"- {b}", p_basis) for b in basis] or None, pt=FLOW_BASIS_PT,
                     align="LEFT", valign="TOP", pad=(1.0, 0.5, FLOW_PAD_MM[2], 0.5), border=bd(4)),
            ]
        tbl = grid_table(st, FLOW_COLS_MM, [FLOW_HEAD_MM] + hs, cells, repeat_header=1)
        for j, i in enumerate(chunk, 1):
            stage, _, _, arrow = steps[i]
            tc = _cell_at(tbl, j, 0)
            tc.find(f"{HP}subList/{HP}p").set("paraPrIDRef", st.para("LEFT", 100))
            _nest(tc, _stage_cell_table(st, stage, arrow))
        w.table(tbl, page_break=True)


# ── P4 ───────────────────────────────────────────────────────────────

def form_rows(form: dict) -> int:
    """격자 빈 줄 수: rows 가 있으면 그대로, 0·없음이면 쪽 끝까지(가로 쪽·2단 머리·아래 줄만큼 뺀다)."""
    rows = int(form.get("rows") or 0)
    if rows > 0:
        return rows
    top = sum(FORM_TOP_MM.values()) + (FORM_TITLE_APPROVAL_MM - FORM_TOP_MM["title"] if form.get("approval") else 0)
    foot = len(form.get("footer") or [])
    foot_mm = FORM_FOOT_BEFORE_MM + foot * FORM_FOOT_PT * 25.4 / 72 * FORM_FOOT_LINE / 100 if foot else 0
    page = LAND_BODY_MM if form.get("landscape") else PAGE_BODY_MM
    room = page - top - FORM_HEAD_MM * (2 if form.get("groups") else 1) - foot_mm - SAFETY_MM
    return max(1, int(room // FORM_ROW_MM))


def add_form(w, form: dict, number: int, values: dict, fill) -> None:
    """기록 양식 한 쪽(새 쪽): [양식 N] 이름 · 가운데 제목(+ 결재란) · 머리 정보 줄 · 격자(머리행 + 빈 줄)."""
    st = w.st
    cols = [fill(str(c)) for c in form.get("columns") or []]
    if not cols:
        raise PartError(f"양식 {form.get('key')}: columns 가 없습니다")
    pct = form.get("widths") or [100 / len(cols)] * len(cols)
    if len(pct) != len(cols):
        raise PartError(f"양식 {form.get('key')}: widths 개수({len(pct)})가 columns({len(cols)})와 다릅니다")
    title = fill(str(form["title"]))
    approval = bool(form.get("approval"))
    info = "     ".join(f"{h} :  {values.get(h, '')}" for h in form.get("header") or [])

    landscape = bool(form.get("landscape"))
    body_w = LAND_W_MM if landscape else BODY_W_MM
    grid_w = body_w - (BODY_W_MM - FORM_GRID_W_MM)          # 정본 격자는 본문폭보다 1 좁다
    groups = _form_groups(form, len(cols))

    # 윗부분: 선 없는 3칸 표로 자리를 고정한다(윗줄 · 띄움 · 제목(+결재란) · 머리 정보)
    T = FORM_TOP_MM
    side = FORM_SIDE_MM
    top_w = [side, body_w - 2 * side, side]
    top_cells = [
        dict(r=0, c=0, cs=3, text="", pt=2, border=NONE4),
        dict(r=1, c=0, cs=3, text=f"[양식 {number}] {title}", pt=FORM_LABEL_PT, align="LEFT", border=NONE4,
             pad=(0, 0, 0, 0), valign="TOP"),
        dict(r=2, c=0, cs=3, text="", pt=2, border=NONE4),
        dict(r=3, c=0, text="", pt=2, border=NONE4),
        dict(r=3, c=1, text=title, pt=FORM_TITLE_PT, bold=True, border=NONE4),
        dict(r=3, c=2, text="", pt=2, border=NONE4, pad=(0, 0, 0, 0)),
        dict(r=4, c=0, cs=3, text=info, pt=FORM_INFO_PT, align="LEFT", border=NONE4, pad=(0, 0, 0, 0)),
    ]
    title_h = FORM_TITLE_APPROVAL_MM if approval else T["title"]
    top = grid_table(st, top_w, [T["space"], T["label"], T["gap"], title_h, T["info"]], top_cells)
    if approval:
        k = len(APPROVAL)
        ac = [dict(r=r, c=c, text=APPROVAL[c] if r == 0 else "", pt=APPROVAL_PT, pad=(0.3, 0.3, 0.2, 0.2),
                   border=(LINE_OUTER if c == 0 else LINE_THIN, LINE_OUTER if c == k - 1 else LINE_THIN,
                           LINE_OUTER if r == 0 else LINE_THIN, LINE_OUTER if r == 1 else LINE_THIN))
              for r in range(2) for c in range(k)]
        tc = _cell_at(top, 3, 2)
        tc.find(f"{HP}subList/{HP}p").set("paraPrIDRef", st.para("RIGHT", 100))
        _nest(tc, grid_table(st, [APPROVAL_COL_MM] * k, [APPROVAL_HEAD_MM, APPROVAL_SIGN_MM], ac))
    w.table(top, page_break=not getattr(w, "fresh", False))   # 가로 구역 첫 쪽이면 이미 새 쪽

    widths = [x * grid_w / sum(pct) for x in pct]
    m, hr = len(cols), 2 if groups else 1                    # hr = 머리 줄 수
    n = form_rows(form) + hr
    heights = [FORM_HEAD_MM] * hr + [FORM_ROW_MM] * (n - hr)

    def bd(r0, c0, rs, cs):
        return (LINE_OUTER if c0 == 0 else LINE_THIN, LINE_OUTER if c0 + cs == m else LINE_THIN,
                LINE_OUTER if r0 == 0 or r0 == hr else LINE_THIN,
                LINE_OUTER if r0 + rs in (hr, n) else LINE_THIN)
    cells = []
    grouped = {c: g for g in groups for c in range(g["start"], g["start"] + g["span"])}
    for g in groups:                                          # 2단 머리: 윗줄 묶음 이름 + 아랫줄 열 이름
        cells.append(dict(r=0, c=g["start"], cs=g["span"], text=fill(str(g["title"])), pt=FORM_PT,
                          pad=(0.5, 0.5, 0.3, 0.3), border=bd(0, g["start"], 1, g["span"])))
    for c in range(m):
        if c in grouped:
            cells.append(dict(r=1, c=c, text=cols[c], pt=FORM_PT, pad=(0.5, 0.5, 0.3, 0.3), border=bd(1, c, 1, 1)))
        else:
            cells.append(dict(r=0, c=c, rs=hr, text=cols[c], pt=FORM_PT, pad=(0.5, 0.5, 0.3, 0.3), border=bd(0, c, hr, 1)))
    cells += [dict(r=r, c=c, text="", pt=FORM_PT, pad=(0.5, 0.5, 0.3, 0.3), border=bd(r, c, 1, 1))
              for r in range(hr, n) for c in range(m)]
    w.table(grid_table(st, widths, heights, cells, repeat_header=hr))
    for k, line in enumerate(form.get("footer") or []):        # 격자 아래 줄(작성일시·작성자 등), 오른쪽
        w.para(fill(str(line)), char=st.char(FORM_FOOT_PT),
               para=st.para("RIGHT", FORM_FOOT_LINE, before=FORM_FOOT_BEFORE_MM if k == 0 else 0))


def _form_groups(form: dict, ncols: int) -> list[dict]:
    """groups 검사: start(0부터)·span 이 열 안이고 겹치지 않아야 한다."""
    out, used = [], set()
    for g in form.get("groups") or []:
        start, span = int(g.get("start", -1)), int(g.get("span", 0))
        if not g.get("title") or span < 1 or start < 0 or start + span > ncols:
            raise PartError(f"양식 {form.get('key')}: groups 범위가 열 밖입니다 {g}")
        cols = set(range(start, start + span))
        if cols & used:
            raise PartError(f"양식 {form.get('key')}: groups 가 겹칩니다 {g}")
        used |= cols
        out.append({"title": g["title"], "start": start, "span": span})
    return out


# ── P5 부표(§15) ──────────────────────────────────────────────────────
TABLE_LABEL_PT, TABLE_SUB_PT, TABLE_PT = 10, 10, 9
TABLE_HEAD_MM, TABLE_ROW_MM, TABLE_EMPTY_ROWS = 5.2, 5.2, 5
TABLE_INDENT_MM = (16.6, 151.6)        # 안쪽 들어간 폭: 본문 왼끝에서 16.6, 폭 151.6 (정본 x 33.1 ~ 184.7)
TABLE_SUB_LEFT_MM = 11.5               # 안쪽 표의 소제목 들여쓰기(정본 x 28.0)
TABLE_GAP_MM = 3.0                     # 같은 부표 안 표 사이
TABLE_LABEL_AFTER_MM, TABLE_SUB_AFTER_MM = 0.4, 0.3   # 윗줄 37.5 → (소제목 42.5 →) 표 42.5 / 47.4 (정본 42.1 / 47.4)
TABLE_SHORT = 8                        # 열의 모든 값이 이 글자 수 이하면 가운데 정렬


def offset(tbl: etree._Element, mm: float) -> etree._Element:
    """표를 본문 왼끝에서 mm 만큼 오른쪽으로(정본의 안쪽 들어간 표)."""
    tbl.find(f"{HP}pos").set("horzOffset", str(hwpx_out._hu(mm)))
    return tbl


def source_rows(src: str, columns: list[str], project: dict) -> list[list[str]] | None:
    """'project.<키>' → project 목록에서 행(열 이름 = 항목 키). 목록이 없으면 None."""
    m = re.fullmatch(r"project\.(.+)", src.strip())
    if not m:
        raise PartError(f"source 는 'project.<키>' 여야 합니다: {src}")
    items = project.get(m.group(1))
    if not isinstance(items, list) or not items:
        return None
    return [[str((it or {}).get(c, "")) if isinstance(it, dict) else "" for c in columns] for it in items]


def add_tables(w, tables: list[dict], project: dict, fill) -> None:
    """부표: 부표마다 새 쪽 윗줄 `[부표 N] 제목`(절마다 1부터). 제목이 같은 항목이 이어지면 같은 부표의 소표로
    같은 쪽에 잇는다(소제목 + 표). source 목록이 비면 머리행 + 빈 줄 5줄(사용자가 채운다)."""
    st = w.st
    number, prev = 0, None
    for t in tables:
        title = fill(str(t.get("title") or ""))
        cols = [fill(str(c)) for c in t.get("columns") or []]
        if not title or not cols:
            raise PartError(f"부표 {t.get('key')}: title·columns 가 필요합니다")
        pct = t.get("widths") or [100 / len(cols)] * len(cols)
        if len(pct) != len(cols):
            raise PartError(f"부표 {t.get('key')}: widths 개수({len(pct)})가 columns({len(cols)})와 다릅니다")
        if t.get("source"):
            rows = source_rows(str(t["source"]), [str(c) for c in t.get("columns")], project)
        else:
            rows = [[fill(str(v)) for v in r] for r in t.get("rows") or []]
        rows = rows or [[""] * len(cols) for _ in range(TABLE_EMPTY_ROWS)]
        if any(len(r) != len(cols) for r in rows):
            raise PartError(f"부표 {t.get('key')}: 행의 칸 수가 columns 와 다릅니다")
        indent = bool(t.get("indent"))
        if title != prev:
            number += 1
            w.para(f"[부표 {number}] {title}", char=st.char(TABLE_LABEL_PT),
                   para=st.para("LEFT", 130, after=TABLE_LABEL_AFTER_MM), page_break=True)
        prev = title
        if t.get("subtitle"):
            w.para(fill(str(t["subtitle"])), char=st.char(TABLE_SUB_PT),
                   para=st.para("LEFT", 130, left=TABLE_SUB_LEFT_MM if indent else 0, after=TABLE_SUB_AFTER_MM))
        width = TABLE_INDENT_MM[1] if indent else BODY_W_MM
        widths = [x * width / sum(pct) for x in pct]
        center = [all(len(r[c]) <= TABLE_SHORT for r in rows) for c in range(len(cols))]
        data = [cols] + rows
        n, m = len(data), len(cols)
        heights = [TABLE_HEAD_MM] + [max(TABLE_ROW_MM, max(_lines_mm(v, widths[c], TABLE_PT, 120) + 0.8
                                                           for c, v in enumerate(r))) for r in rows]
        cells = [dict(r=i, c=c, text=v, pt=TABLE_PT, align="CENTER" if i == 0 or center[c] else "LEFT",
                      pad=(0.8, 0.8, 0.2, 0.2),
                      border=(LINE_OUTER if c == 0 else LINE_THIN, LINE_OUTER if c == m - 1 else LINE_THIN,
                              LINE_OUTER if i <= 1 else LINE_THIN, LINE_OUTER if i in (0, n - 1) else LINE_THIN))
                 for i, r in enumerate(data) for c, v in enumerate(r)]
        tbl = grid_table(st, widths, heights, cells, repeat_header=1, gap_mm=TABLE_GAP_MM)
        w.table(offset(tbl, TABLE_INDENT_MM[0]) if indent else tbl)


# ── P6 조직도(§17) ─────────────────────────────────────────────────────
# 정본 5.2 부표1(22쪽) 실측. 도형 대신 한 표의 칸 테두리로 상자·연결선을 그린다(흐름표와 같은 방식).
ORG_FILL = "#DFE6F7"                  # 상자 머리칸 바탕(정본 RGB 223·230·247)
ORG_CHAIN_W_MM = 56.8                 # 줄기 상자 폭(정본 x 79.6~136.4)
ORG_HEAD_MM, ORG_NAME_MM = 9.2, 9.4   # 줄기 상자 머리·성명 줄
ORG_LINK_MM = 5.2                     # 줄기 상자 사이 세로선
ORG_TRUNK_MM, ORG_DROP_MM = 8.0, 6.4  # 줄기 → 가로선, 가로선 → 부서 상자
ORG_NODE_GAP_MM, ORG_NODE_MAX_MM = 7.6, 45.0   # 부서 상자 사이 · 최대 폭(정본 4개일 때 약 39)
ORG_NODE_HEAD_MM, ORG_NODE_NAME_MM = 10.6, 8.4
ORG_MEMBER_LINK_MM, ORG_MEMBER_ROW_MM, ORG_MEMBER_MIN_ROWS = 6.2, 8.4, 3
ORG_MEMBER_LEFT = 0.4                 # 구성원 표 왼칸(직급) 비율(정본 15.8 / 39)
ORG_MEMBER_LEFT_WIDE = 0.5            # 직급·등급이 없어 직무를 쓰면 왼칸을 넓힌다
ORG_TIER_MAX = 6                      # 한 단 부서 상자 수(넘치면 다음 단)
ORG_HEAD_PT, ORG_TEXT_PT = 12, 12       # 정본 조직도 글 약 12.5pt(표 글 중앙값)
ORG_W_MM = 180.0                      # 정본 조직도 폭 x 16.3 ~ 196.6
ORG_LINE = LINE_OUTER
ORG_MIN_PT = 7                        # 칸에 한 줄로 안 들어가는 글은 이 크기까지 줄인다(두 줄로 접으면 칸이 어긋나 보인다)
# 옆 상자(배치: 옆, 정본 품질관리자·안전/보건관리자): 폭 46.6, 머리·줄 8.5, 왼칸(등급) 34 %, 줄기에서 10.4 아래
ORG_SIDE_W_MM, ORG_SIDE_ROW_MM, ORG_SIDE_LEFT, ORG_SIDE_TRUNK_MM = 46.6, 8.5, 0.34, 10.4
ORG_SIDE_AFTER_MM = 14.2              # 옆 상자 띠 끝 → 부서 가로선(정본 176.8 → 191.0)
# 본사/현장 구분(구분: 본사): 줄기 상자 사이 7.6 + 7.6, 가운데 점선, 오른쪽 ↑ 본사 / ↓ 현장
ORG_SPLIT_MM, ORG_SPLIT_LABEL_W_MM, ORG_SPLIT_LINE = 7.6, 22.0, ("DASH", "0.3 mm")
ORG_AFTER_PCT = 115                   # 조직도 아래 빈 줄(12pt 115% ≈ 4.9) — 뷰어가 표 바깥 여백을 버려서 문단으로 띄운다


def _fill_border(st: hwpx_out._Styles, sides: tuple, color: str) -> str:
    """선 + 바탕색 borderFill(조직도 상자 머리칸)."""
    key = ("fill", sides, color)
    if key not in st._cache:
        base = st._container("borderFills").find(f"{HH}borderFill[@id='{st.border(*sides)}']")
        el = deepcopy(base)
        hc = "{http://www.hancom.co.kr/hwpml/2011/core}"
        brush = etree.SubElement(el, f"{HH}fillBrush")
        etree.SubElement(brush, f"{hc}winBrush", faceColor=color, hatchColor="#000000", alpha="0")
        st._cache[key] = st._add("borderFills", "borderFill", el)
    return st._cache[key]


def org_tree(items: list[dict]) -> tuple[list[int], dict[int, list[int]]] | None:
    """조직 목록 → (뿌리 번호들, 번호 → 아래 번호들). `상위` 키가 하나도 없으면 None(조직도 없음).

    `상위` 는 윗사람의 직무 이름(같은 직무가 여럿이면 처음 것). 없는 이름·순환은 PartError."""
    if not any("상위" in (it or {}) for it in items):
        return None
    first = {}
    for i, it in enumerate(items):
        first.setdefault(str(it.get("직무", "")), i)
    kids: dict[int, list[int]] = {i: [] for i in range(len(items))}
    roots = []
    for i, it in enumerate(items):
        up = str(it.get("상위") or "").strip()
        if not up:
            roots.append(i)
            continue
        if up not in first:
            raise PartError(f"조직 '{it.get('직무')}': 상위 '{up}' 가 조직 목록에 없습니다")
        if first[up] == i:
            raise PartError(f"조직 '{up}': 자기 자신을 상위로 둘 수 없습니다")
        kids[first[up]].append(i)
    seen, stack = set(), list(roots)
    while stack:
        i = stack.pop()
        seen.add(i)
        stack.extend(kids[i])
    if len(seen) != len(items):
        raise PartError("조직 상위 관계에 순환이 있습니다")
    return roots, kids


def _descendants(i: int, kids: dict[int, list[int]]) -> list[int]:
    out = []
    for k in kids[i]:
        out.append(k)
        out.extend(_descendants(k, kids))
    return out


def add_org(w, items: list[dict], fill) -> bool:
    """조직도: 줄기(아래가 하나뿐인 윗사람들을 세로로) → 가로선 → 부서 상자들 → 각 아래 사람 구성원 표.
    `상위` 가 없으면 아무것도 그리지 않고 False."""
    tree = org_tree(items)
    if tree is None:
        return False
    roots, kids = tree
    st = w.st
    W, C = ORG_W_MM, ORG_W_MM / 2
    L = ORG_LINE
    rows: list[tuple[float, list[dict]]] = []      # (높이, [칸: x0·x1·글·선·바탕·굵게·pt])

    def box(x0, x1, text, *, head, top=True, bottom=True):
        return dict(x0=x0, x1=x1, text=text, border=(L, L, L if top else LINE_THIN, L if bottom else LINE_THIN),
                    fill=head, bold=head, pt=ORG_HEAD_PT if head else ORG_TEXT_PT)

    def vline(x, extra=()):
        return [dict(x0=x - 1.0, x1=x, text="", border=(None, L, None, None))] + list(extra)

    def side(i):
        return str(items[i].get("배치") or "").strip() == "옆"

    main = {i: [k for k in ks if not side(k)] for i, ks in kids.items()}
    chain, top = [], [r for r in roots if not side(r)]
    while len(top) == 1:
        chain.append(top[0])
        top = main[top[0]]
    split = max((n for n, i in enumerate(chain) if str(items[i].get("구분") or "").strip() == "본사"), default=None)

    def divider():
        dash = (None, None, None, ORG_SPLIT_LINE)
        lx = W - ORG_SPLIT_LABEL_W_MM
        rows.append((ORG_SPLIT_MM, [dict(x0=0, x1=C - 1.0, text="", border=NONE4, bf=dash),
                                    dict(x0=C - 1.0, x1=C, text="", border=NONE4,
                                         bf=(None, ("SOLID", L), None, ORG_SPLIT_LINE)),
                                    dict(x0=C, x1=lx, text="", border=NONE4, bf=dash),
                                    dict(x0=lx, x1=W, text="↑  본사", border=NONE4, bf=dash, bold=True,
                                         pt=ORG_TEXT_PT - 2, align="RIGHT")]))
        rows.append((ORG_SPLIT_MM, vline(C, [dict(x0=lx, x1=W, text="↓  현장", border=NONE4, bold=True,
                                                   pt=ORG_TEXT_PT - 2, align="RIGHT")])))

    for n, i in enumerate(chain):
        it = items[i]
        if n:
            if split == n - 1:
                divider()
            else:
                rows.append((ORG_LINK_MM, vline(C)))
        name = str(it.get("성명") or "")
        rows.append((ORG_HEAD_MM, [box(C - ORG_CHAIN_W_MM / 2, C + ORG_CHAIN_W_MM / 2, fill(str(it.get("직무", ""))),
                                       head=True, bottom=not name)]))
        if name:
            rows.append((ORG_NAME_MM, [box(C - ORG_CHAIN_W_MM / 2, C + ORG_CHAIN_W_MM / 2, fill(name), head=False,
                                           top=False)]))
    if split is not None and split == len(chain) - 1:
        divider()
    sides = [k for i in chain for k in kids[i] if side(k)]
    if sides:
        _side_band(rows, items, kids, sides, fill, W, C, L, box, vline)
    tiers = [top[k:k + ORG_TIER_MAX] for k in range(0, len(top), ORG_TIER_MAX)]
    for t, tier in enumerate(tiers):
        k = len(tier)
        nw = min(ORG_NODE_MAX_MM, (W - (k - 1) * ORG_NODE_GAP_MM) / k)
        total = k * nw + (k - 1) * ORG_NODE_GAP_MM
        xs = [C - total / 2 + j * (nw + ORG_NODE_GAP_MM) for j in range(k)]
        cs = [x + nw / 2 for x in xs]
        through = t < len(tiers) - 1 and k % 2 == 0     # 다음 단으로 줄기가 부서 사이(가운데 빈칸)로 지나간다
        if chain or t or sides:
            rows.append((ORG_SIDE_AFTER_MM if sides and t == 0 else ORG_TRUNK_MM, vline(C)))
        if k > 1:
            bus = [dict(x0=cs[j], x1=cs[j + 1], text="", border=(L, L if j == k - 2 else None, L, None))
                   for j in range(k - 1)]
            if through:
                bus = [dict(b, border=(b["border"][0], b["border"][1], L, None)) for b in bus]
            rows.append((ORG_DROP_MM, bus))
        extra = [] if not through else [dict(x0=C - 1.0, x1=C, text="", border=(None, L, None, None))]
        names = [str(items[i].get("성명") or "") for i in tier]
        rows.append((ORG_NODE_HEAD_MM, [box(xs[j], xs[j] + nw, _spaced_head(fill(str(items[i].get("직무", "")))),
                                            head=True, bottom=not names[j]) for j, i in enumerate(tier)] + extra))
        if any(names):
            rows.append((ORG_NODE_NAME_MM, [box(xs[j], xs[j] + nw, fill(names[j]), head=False, top=False)
                                            for j in range(k) if names[j]] + extra))
        members = [_descendants(i, kids) for i in tier]
        if any(members):
            rows.append((ORG_MEMBER_LINK_MM, [dict(x0=cs[j] - 1.0, x1=cs[j], text="", border=(None, L, None, None))
                                              for j in range(k) if members[j]] + extra))
            m = max(ORG_MEMBER_MIN_ROWS, max(len(x) for x in members))

            def rank(p):                                           # 정본: 직급 | 성명(없으면 직무)
                return str(p.get("직급") or p.get("등급") or p.get("직무", ""))
            left, mpt = [], []
            for j in range(k):                                     # 부서마다 왼칸 비율과 한 가지 글자 크기
                ps = [items[x] for x in members[j]]
                ratio = ORG_MEMBER_LEFT if ps and all(p.get("직급") or p.get("등급") for p in ps) else ORG_MEMBER_LEFT_WIDE
                left.append(ratio)
                mpt.append(min([ORG_TEXT_PT] + [hwpx_out._fit_pt(fill(t), wd - 1.6, ORG_TEXT_PT, min_pt=ORG_MIN_PT)
                                                for p in ps for t, wd in ((rank(p), nw * ratio),
                                                                          (str(p.get("성명", "")), nw * (1 - ratio)))]))
            for r in range(m):
                segs = list(extra)
                for j in range(k):
                    if not members[j]:
                        continue
                    who = items[members[j][r]] if r < len(members[j]) else {}
                    split = xs[j] + nw * left[j]
                    tb = (L if r == 0 else LINE_THIN, L if r == m - 1 else LINE_THIN)
                    segs.append(dict(x0=xs[j], x1=split, text=fill(rank(who)) if who else "",
                                     border=(L, LINE_THIN) + tb, pt=mpt[j]))
                    segs.append(dict(x0=split, x1=xs[j] + nw, text=fill(str(who.get("성명", ""))),
                                     border=(LINE_THIN, L) + tb, pt=mpt[j]))
                rows.append((ORG_MEMBER_ROW_MM, segs))
    _grid_from_rows(w, rows, W)
    w.para("", char=st.char(ORG_TEXT_PT), para=st.para("LEFT", ORG_AFTER_PCT))   # 아래 조직 표와 띄움(약 5)
    return True


def _side_band(rows, items, kids, sides, fill, W, C, L, box, vline) -> None:
    """옆 상자 띠: 같은 직무가 이어지면 한 상자(머리 + 사람마다 등급 | 성명 줄). 첫 상자는 왼쪽, 다음부터는 줄이
    적은 쪽(같으면 오른쪽)에 위에서부터 쌓는다(정본: 왼쪽 품질관리자, 오른쪽 안전·보건관리자).
    첫 줄(머리) 아래 높이로 줄기에서 좌우로 가로선을 뻗는다."""
    groups: list[list[int]] = []
    for i in sides:
        if groups and str(items[groups[-1][0]].get("직무")) == str(items[i].get("직무")):
            groups[-1].append(i)
        else:
            groups.append([i])
    stacks = {"L": [], "R": []}
    for g_no, g in enumerate(groups):
        lines = [("head", fill(str(items[g[0]].get("직무", ""))))]
        for i in g:
            for p in [i] + _descendants(i, kids):
                lines.append(("person", items[p]))
        size = {k: sum(len(b) for b in v) for k, v in stacks.items()}
        stacks["L" if g_no == 0 or size["L"] < size["R"] else "R"].append(lines)
    cols = {"L": (0.0, ORG_SIDE_W_MM), "R": (W - ORG_SIDE_W_MM, W)}
    flat = {k: [(j, b[j], j == len(b) - 1) for b in v for j in range(len(b))] for k, v in stacks.items()}
    rows.append((ORG_SIDE_TRUNK_MM, vline(C)))
    for r in range(max(len(flat["L"]), len(flat["R"]))):
        segs = []
        for k in ("L", "R"):
            if r >= len(flat[k]):
                continue
            _, (kind, val), last = flat[k][r]
            x0, x1 = cols[k]
            if kind == "head":
                segs.append(box(x0, x1, _spaced_side(val), head=True))
            else:
                cut = x0 + (x1 - x0) * ORG_SIDE_LEFT
                tb = (LINE_THIN, L if last else LINE_THIN)
                grade = str(val.get("등급") or val.get("직급") or "")
                segs.append(dict(x0=x0, x1=cut, text=fill(grade), border=(L, LINE_THIN) + tb, pt=ORG_TEXT_PT))
                segs.append(dict(x0=cut, x1=x1, text=fill(str(val.get("성명", ""))), border=(LINE_THIN, L) + tb,
                                 pt=ORG_TEXT_PT))
        if r == 0:                                             # 첫 머리 아래 높이로 줄기에서 좌우 가로선
            lx = cols["L"][1] if flat["L"] else C - 1.0
            segs.append(dict(x0=lx, x1=C, text="", border=(None, L, None, L if flat["L"] else None)))
            if flat["R"]:
                segs.append(dict(x0=C, x1=cols["R"][0], text="", border=(None, None, None, L)))
        else:
            segs += vline(C)
        rows.append((ORG_SIDE_ROW_MM, segs))


def _spaced_side(text: str) -> str:
    """옆 상자 머리: 글자마다 벌린다(정본 '품 질 관 리 자')."""
    return " ".join(text.replace(" ", "")) if len(text) <= 6 else text


def _custom_border(st: hwpx_out._Styles, sides: tuple) -> str:
    """변마다 (선 종류, 굵기) 또는 None 인 borderFill(점선 구분선 등)."""
    key = ("custom", sides)
    if key not in st._cache:
        el = etree.Element(f"{HH}borderFill", threeD="0", shadow="0", centerLine="NONE", breakCellSeparateLine="0")
        etree.SubElement(el, f"{HH}slash", type="NONE", Crooked="0", isCounter="0")
        etree.SubElement(el, f"{HH}backSlash", type="NONE", Crooked="0", isCounter="0")
        for name, spec in zip(("left", "right", "top", "bottom"), sides):
            kind, width = spec if spec else ("NONE", "0.1 mm")
            etree.SubElement(el, f"{HH}{name}Border", type=kind, width=width, color="#000000")
        etree.SubElement(el, f"{HH}diagonal", type="NONE", width="0.1 mm", color="#000000")
        st._cache[key] = st._add("borderFills", "borderFill", el)
    return st._cache[key]


def _spaced_head(text: str) -> str:
    """부서 상자 머리 글: 두 글자는 자간을 크게(정본 '공    사')."""
    return f"{text[0]}      {text[1]}" if len(text) == 2 else text


def _grid_from_rows(w, rows: list[tuple[float, list[dict]]], width: float) -> None:
    """(높이, 칸 목록) 행들 → 모든 칸 가장자리를 열 경계로 모은 표 하나(빈 곳은 선 없는 칸)."""
    st = w.st
    edges = sorted({0.0, round(width, 2)} | {round(v, 2) for _, segs in rows for s in segs for v in (s["x0"], s["x1"])})
    col = {x: n for n, x in enumerate(edges)}
    widths = [b - a for a, b in zip(edges, edges[1:])]
    cells, fills, customs = [], [], []
    for r, (_, segs) in enumerate(rows):
        segs = sorted(segs, key=lambda s: s["x0"])
        pos = 0.0
        for s in segs + [dict(x0=width, x1=width, sentinel=True)]:
            a, b = round(s["x0"], 2), round(s["x1"], 2)
            if a > round(pos, 2):
                cells.append(dict(r=r, c=col[round(pos, 2)], cs=col[a] - col[round(pos, 2)], text="", pt=2,
                                  border=NONE4, pad=(0, 0, 0, 0)))
            if s.get("sentinel"):
                break
            text, pt = s.get("text", ""), s.get("pt", 2)
            if text and "\n" not in text:
                pt = hwpx_out._fit_pt(text, b - a - 1.0 - 0.6, pt, min_pt=ORG_MIN_PT)   # 안여백 0.5×2 + 여유
            cells.append(dict(r=r, c=col[a], cs=col[b] - col[a], text=text, pt=pt,
                              bold=s.get("bold", False), border=s["border"], pad=(0.5, 0.5, 0.2, 0.2),
                              align=s.get("align", "CENTER")))
            if s.get("fill"):
                fills.append((r, col[a], s["border"]))
            if s.get("bf"):
                customs.append((r, col[a], s["bf"]))
            pos = b
    tbl = grid_table(st, widths, [h for h, _ in rows], cells, gap_mm=3.0)
    for r, c, sides in fills:
        _cell_at(tbl, r, c).set("borderFillIDRef", _fill_border(st, sides, ORG_FILL))
    for r, c, spec in customs:
        spec = tuple(("SOLID", x) if isinstance(x, str) else x for x in spec)
        _cell_at(tbl, r, c).set("borderFillIDRef", _custom_border(st, spec))
    w.table(tbl)


def records_lines(s: dict, nums: dict[str, int], fill) -> list[str] | None:
    """첨부(양식) 칸: 이 절의 양식을 '양식 N 이름'으로, 이어서 양식이 아닌 기록은 '- 이름'. 양식이 없으면 None(기존 방식)."""
    forms = s.get("forms") or []
    if not forms:
        return None
    titles = {fill(str(f["title"])) for f in forms}
    out = [f"양식 {nums[f['key']]} {fill(str(f['title']))}" for f in forms]
    out += [f"- {fill(str(r))}" for r in s.get("records") or [] if fill(str(r)) not in titles]
    return out

