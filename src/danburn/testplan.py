"""품질시험계획서 단독본(HWPX)을 조립한다 — 관리계획서 8.11 과 같은 계산 결과(rows)를 그대로 쓴다.

구성은 「건설기술 진흥법 시행령」 별표9(품질시험계획의 내용) 4부를 따른다:
표지 → 목차·개정이력 → 1. 개요(가. 공사개요, 나. 공사수행 조직도) → 2. 품질시험 및 검사계획(A4 가로 8.11 표)
→ 3. 품질시험 시설(가. 시험·검사 장비, 나. 교정계획, 다. 시험실 — 평면도는 (스캔첨부)) → 4. 품질관리자 배치계획
(+ 경력·자격·재직 증빙 (스캔첨부)).

모양은 계획서(plan_doc)와 같은 부품을 쓴다: 쪽 머리·표지·공사개요 표·조직도·8.11 표(hwpx_out.add_811_tables).
스캔이 필요한 실물(평면도·증빙)은 파일을 넣지 않고 빈 칸만 둔다 — 개인정보 증빙은 사용자가 제출 때 붙인다.
엑셀 단독본은 testplan_xlsx 가 같은 rows 로 만든다(칸 정의 hwpx_out.HEAD 공유).
"""
from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument

from . import hwpx_out, plan_doc, plan_parts
from .hwpx_out import LINE_OUTER, add_811_tables, compact_date, grid_table
from .model import PlanRow
from .plan_doc import BODY_MM, BODY_TOP_MM, BODY_END_MM, _Writer, _cover, _overview_table, _revisions, _simple_table

DOC_TITLE = "품질시험계획서"
COVER_SUBTITLE = "Quality Test Plan"
SCAN = "(스캔첨부)"
TODO = "(작성 필요)"
# 별표9 4부. (번호, 제목, [소항목]) — 목차·쪽 머리·xlsx 표지가 같이 쓴다
PARTS = [
    ("1", "개요", ["가. 공사개요", "나. 공사수행 조직도"]),
    ("2", "품질시험 및 검사계획", ["가. 시험종목·시험방법·시험빈도·계획시험횟수와 산출근거"]),
    ("3", "품질시험 시설", ["가. 시험·검사 장비", "나. 시험·검사 장비 교정계획", "다. 시험실(배치평면도)"]),
    ("4", "품질관리자 배치계획", ["가. 품질관리 건설기술인 배치", "나. 경력·자격·재직 증빙"]),
]
PARTS_BASIS = "「건설기술 진흥법 시행령」 제91조·별표9 품질시험계획의 내용"
EQUIP_COLS = ["시험기구", "규격", "단위", "수량", "비고"]
CALIB_COLS = ["시험기구", "규격", "수량", "제작사", "기기번호", "교정주기", "비고"]
STAFF_COLS = ["직무", "성명", "등급", "배치기간", "비고"]
# 품질관리자 증빙(영 별표9 4. — 자격·경력 확인). 파일은 넣지 않는다(개인정보) → 빈 칸
STAFF_PROOFS = ["경력증명서(「건설기술 진흥법 시행규칙」 별지 제18호서식)", "국가기술자격증 사본", "재직증명서",
                "현장배치 확인서"]
EMPTY_ROWS = 5
# (스캔첨부) 빈칸 이름 전부(요약 JSON·스킬 안내가 쓴다)
SCAN_ITEMS = ["시험실 배치평면도"] + STAFF_PROOFS
SCAN_PT = 12
ROOM_BOX_MM = 150.0                               # 평면도 칸 높이
PROOF_BOX_MM = BODY_END_MM - BODY_TOP_MM - 20.0   # 증빙 한 쪽 칸 높이(제목 줄·여유 뺀 나머지)


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def _list(project: dict, key: str) -> list[dict]:
    v = project.get(key)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def table_rows(project: dict, key: str, columns: list[str], *, empty: int = EMPTY_ROWS) -> list[list[str]]:
    """project.<key> 목록 → 열 이름(=항목 키) 순서의 행. 없으면 빈 행 empty 줄(사용자가 채운다). xlsx 도 쓴다."""
    items = _list(project, key)
    if not items:
        return [[""] * len(columns) for _ in range(empty)]
    return [[_text(it.get(c)) for c in columns] for it in items]


def staff_rows(project: dict) -> list[list[str]]:
    """품질관리자 배치 행. 문자열 한 개로 적었으면 성명 칸에만 넣는다."""
    v = project.get("품질관리자")
    if isinstance(v, str) and v.strip():
        return [["품질관리자", v.strip(), "", "", ""]]
    return table_rows(project, "품질관리자", STAFF_COLS)


def room_text(project: dict) -> str:
    """시험실 규모(판정 결과) — 최상위 키가 판정 블록보다 우선."""
    judged = project.get("판정") if isinstance(project.get("판정"), dict) else {}
    return _text(project.get("시험실") or judged.get("시험실")) or TODO


def overview_values(project: dict) -> dict:
    """공사개요에 쓸 값: 필수 칸이 비면 '(작성 필요)'(단독본은 판정 전 project 로도 만든다)."""
    out = dict(project)
    for k in plan_doc.OVERVIEW_REQUIRED:
        if not _text(out.get(k)):
            out[k] = TODO
    return out


def _scan_box(w: _Writer, label: str, height_mm: float, note: str = ""):
    """(스캔첨부) 빈 칸: 굵은 테두리 한 칸, 가운데 '(스캔첨부) 이름', 아래 작은 안내."""
    st = w.st
    lines = [([(f"{SCAN} {label}", st.char(SCAN_PT, bold=True))], st.para("CENTER", 150))]
    if note:
        lines.append(([(note, st.char(hwpx_out.PT["note"]))], st.para("CENTER", 150)))
    cell = dict(r=0, c=0, text="", lines=lines, pt=SCAN_PT, border=(LINE_OUTER,) * 4)
    w.table(grid_table(st, [BODY_MM], [height_mm], [cell], gap_mm=1.5))


def _heading(w: _Writer, text: str, *, page_break: bool = False):
    w.chapter(text, page_break=page_break)


def _toc(w: _Writer, revs: list[dict]):
    """목차(4부·소항목) + 개정이력(번호·일자·사유)."""
    rows = [["번호", "제    목", "내    용"]]
    for no, title, subs in PARTS:
        rows.append([no, title, "\n".join(subs)])
    _simple_table(w, rows, [15, 55, BODY_MM - 70], pt=10, row_mm=14.0, left_cols={1, 2})
    w.para(f"구성 근거: {PARTS_BASIS}", char=w.st.char(hwpx_out.PT["note"]), para=w.st.para("LEFT", 130))
    _heading(w, "개정 이력")
    hist = [["개정번호", "개정일자", "개정 사유"]]
    hist += [[str(r["개정"]), compact_date(r["일자"]), _text(r.get("사유"))] for r in revs]
    _simple_table(w, hist, [20, 30, BODY_MM - 50], pt=9, left_cols={2})


def _org(w: _Writer, project: dict):
    items = _list(project, "조직")
    if not items:
        w.body(f"{TODO} 현장 조직(project.yaml 의 조직 목록)을 적으면 조직도가 그려진다.")
        return
    plan_parts.add_org(w, items, lambda t: t)
    people = [r for r in items if _text(r.get("성명"))]
    if people:
        _simple_table(w, [["직무", "성명", "자격", "담당업무"]]
                      + [[_text(r.get("직무")), _text(r.get("성명")), _text(r.get("자격")), _text(r.get("담당"))]
                         for r in people], [30, 35, 40, BODY_MM - 105], left_cols={3})


def build_testplan(rows: list[PlanRow], project: dict, out: str | Path, *, basis_version: str = "",
                   revision: int | str = 0, date: str = "", unlisted: list[dict] | None = None,
                   generated_note: str = "", notice_footer: bool = False) -> Path:
    """품질시험계획서 단독본을 out 에 쓴다. rows 는 관리계획서 8.11 과 같은 계산 결과(cli 가 한 번 계산해 넘긴다).

    project 는 danburn start 가 쓴 project.yaml(dict). 개정이력은 plan_doc 과 같은 규칙으로 검사한다
    (revision·date 가 이력과 어긋나면 ValueError — 파일을 만들지 않는다). 로고 파일이 없으면 FileNotFoundError.
    """
    project = dict(project or {})
    date = date or _text(project.get("제정일자"))
    revs = _revisions(project, revision, date)
    current = revs[-1]
    rev_text, rev_date = f"Rev.{current['개정']}", current["일자"]
    logo = plan_doc._logo(project)
    logo_path = str(Path(_text(project["로고"])).expanduser()) if logo else None
    brand = {"logo": logo_path, "company": _text(project.get("회사명"))}
    cover_project = {**project, "공사명": _text(project.get("공사명")) or TODO}

    doc = HwpxDocument.new()
    w = _Writer(doc, notice_footer)

    def frame(title: str):
        w.frame(doc_title=DOC_TITLE, title=title, revision=rev_text, date=rev_date, **brand)

    # 표지 — 계획서 표지와 같은 배치, 문서명·영문 부제만 바꾼다
    w.new_unit(first=True)
    w.frame(doc_title=DOC_TITLE, title="", revision="", date="", header=False)
    _cover(w, cover_project, current["개정"], rev_date, logo_path, title=DOC_TITLE, subtitle=COVER_SUBTITLE)

    w.new_unit()
    frame("목차 및 개정이력")
    _toc(w, revs)

    # 1. 개요
    w.new_unit()
    frame("1. 개요")
    _heading(w, "가. 공사개요")
    _overview_table(w, overview_values(project))
    _heading(w, "나. 공사수행 조직도", page_break=True)
    _org(w, project)

    # 2. 품질시험 및 검사계획 — 관리계획서 8.11 과 같은 표(가로 A4: 시험방법 칸까지 넉넉히)
    w.new_unit()
    add_811_tables(doc, rows, section=w.sec, title="2. 품질시험 및 검사계획", basis_version=basis_version,
                   generated_note=generated_note, revision=rev_text, date=rev_date, doc_title=DOC_TITLE,
                   section_title="2. 품질시험 및 검사계획", landscape=True, unlisted=unlisted,
                   notice_footer=notice_footer, **brand)

    # 3. 품질시험 시설
    w.new_unit()
    frame("3. 품질시험 시설")
    _heading(w, "가. 시험·검사 장비")
    _simple_table(w, [EQUIP_COLS] + table_rows(project, "시험장비", EQUIP_COLS), [20, 32, 7, 7, 34], left_cols={0, 1, 4})
    _heading(w, "나. 시험·검사 장비 교정계획")
    _simple_table(w, [CALIB_COLS] + table_rows(project, "시험장비", CALIB_COLS), [20, 20, 8, 14, 14, 10, 14],
                  left_cols={0, 1, 6})
    w.para("교정은 정해진 주기 또는 사용 전에 받고 교정성적서를 보관한다(품질관리계획서 7.2).",
           char=w.st.char(hwpx_out.PT["note"]), para=w.st.para("LEFT", 130))
    _heading(w, "다. 시험실", page_break=True)
    _simple_table(w, [["항목", "내용"], ["시험실 규모(기준)", room_text(project)],
                      ["시험실 면적(실제)", "가로      m × 세로      m =        ㎡"]], [25, 75], left_cols={1})
    _scan_box(w, "시험실 배치평면도", ROOM_BOX_MM, "시험실·양생 수조·시험기구 배치와 치수를 표시한 평면도를 붙인다")

    # 4. 품질관리자 배치계획
    w.new_unit()
    frame("4. 품질관리자 배치계획")
    _heading(w, "가. 품질관리 건설기술인 배치")
    _simple_table(w, [STAFF_COLS] + staff_rows(project), [18, 18, 18, 32, 14], left_cols={3, 4})
    w.para("등급·배치 기준: 「건설기술 진흥법 시행규칙」 제50조제4항·별표5. 증빙은 아래 쪽에 사람마다 붙인다.",
           char=w.st.char(hwpx_out.PT["note"]), para=w.st.para("LEFT", 130))
    for proof in STAFF_PROOFS:
        _heading(w, f"나. 증빙 — {proof}", page_break=True)
        _scan_box(w, proof, PROOF_BOX_MM, "주민등록번호 뒷자리 등 개인정보는 가린 사본을 붙인다")

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save_to_path(str(out))
    plan_doc._register_bin_items(out)
    return out


__all__ = ["DOC_TITLE", "PARTS", "SCAN", "SCAN_ITEMS", "build_testplan", "overview_values", "room_text", "staff_rows", "table_rows"]
