"""서식 부품 P2 분장표 · P3 흐름표 · P4 양식(L7-D1): 합성 템플릿(qplan.yaml 에 의존하지 않음)."""
import re
import zipfile
from pathlib import Path

import pytest
import yaml

from danburn.model import PlanRow
from danburn.plan_doc import build_plan
from danburn.plan_parts import FLOW_COLS_MM, PAGE_BODY_MM, PartError, form_numbers, form_ref, form_rows
from conftest import VALIDATE, run_hwpx_validate

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "src" / "danburn" / "data" / "templates" / "project.example.yaml"
TEAMS = [{"key": "품질", "name": "품질팀"}, {"key": "안전", "name": "안전팀"}, {"key": "공사", "name": "공사팀"},
         {"key": "공무", "name": "공무팀"}, {"key": "대리인", "name": "현장대리인"}]


def _flow(n=4):
    return [{"stage": f"합성 단계 {i}",
             "content": [f"• 합성 담당은 합성 업무 {i}을 한다.", "- 합성 하위 항목", "(합성 보충)"],
             "basis": ["양식:syn_ledger", "8.11"] if i == 1 else ["4.2"]} for i in range(1, n + 1)]


def _template(**sec):
    s42 = {"id": "4.2", "title": "합성 절", "basis": "별표1 4.2", "purpose": "합성 목적.",
           "steps": ["합성 절차 하나"], "records": ["합성 기록", "합성 대장"]}
    s42.update(sec)
    return {
        "default_scope": "{공사명} 전체.",
        "chapters": [
            {"id": "1", "title": "일반사항", "body": ["1) 합성 문장."]},
            {"id": "4", "title": "조직 상황", "sections": [s42]},
            {"id": "8", "title": "운용", "sections": [
                {"id": "8.11", "title": "검사 및 시험, 모니터링", "purpose": "합성.", "steps": ["합성"],
                 "body_after": ["{8.11}"],
                 "forms": [{"key": "syn_summary", "title": "합성 총괄표", "columns": ["구분", "계획", "실적"],
                            "rows": 5}]}]},
        ],
    }


FULL = dict(
    roles=[{"task": "합성 업무 가", "marks": {"대리인": "●", "품질": "○", "공사": "◎"}},
           {"task": "합성 업무 나", "marks": {"품질": "○"}, "note": "합성 비고"}],
    flow=_flow(),
    forms=[{"key": "syn_ledger", "title": "합성 대장", "header": ["공사명", "현장명"],
            "columns": ["번호", "일자", "내용", "비고"], "widths": [10, 20, 55, 15], "approval": True, "rows": 0}],
)


def _project(**kw):
    p = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    p.update(kw)
    return p


def _rows():
    return [PlanRow("건축", "철근콘크리트공사", "레미콘 25-24-150", "슬럼프", 1000, "m3", "120㎥마다", "1,000/120", 9)]


def _build(tmp, template, **proj):
    out = tmp / "p.hwpx"
    build_plan(_rows(), _project(**proj), out, basis_version="합성", revision=0, date="2026. 01. 05.",
               template=template)
    return out


def _sections(path):
    with zipfile.ZipFile(path) as z:
        names = sorted((n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)),
                       key=lambda n: int(re.search(r"\d+", n).group()))
        return [z.read(n).decode("utf-8") for n in names]


def _text(xml):
    body = re.sub(r"<hp:header.*?</hp:header>|<hp:footer.*?</hp:footer>", "", xml, flags=re.S)
    return "".join(re.findall(r"<hp:t(?:\s[^>]*)?>([^<]*)</hp:t>", body))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("parts"), _template(**FULL), 팀=TEAMS)


def _sec42(built):
    return next(x for x in _sections(built) if "합성 목적." in _text(x))


def test_order_boxes_roles_flow_forms(built):
    t = _text(_sec42(built))
    marks = ["목 적", "○ 작성/주관", "항 목", "합성 업무 가", "업무단계", "합성 단계 1", "[양식 1] 합성 대장", "번호"]
    assert [t.index(m) for m in marks] == sorted(t.index(m) for m in marks)


def test_roles_table_columns_follow_teams(built):
    t = _text(_sec42(built))
    assert "항 목품질팀안전팀공사팀공무팀현장대리인비 고" in t
    assert "합성 업무 가○◎●" in t                                # 팀 순서대로 표시


def test_flow_basis_refers_to_form_number_and_new_page(built):
    x = _sec42(built)
    assert "- 양식 1" in _text(x) and "양식:" not in _text(x)
    assert _text(x).count("▼") == 3                               # 마지막 단계만 화살표 없음
    assert re.search(r'<hp:p [^>]*pageBreak="1"[^>]*>(?:(?!</hp:p>).)*?업무단계', x, re.S)


def test_form_page_and_attachment_box(built):
    x = _sec42(built)
    t = _text(x)
    assert "양식 1 합성 대장" in t and "- 합성 기록" in t          # 첨부(양식) 칸: 양식 + 나머지 기록
    assert "공사명 :  가상시 예시지구 공동주택 신축공사" in t        # 머리 정보 줄 치환
    assert "담 당팀 장현장대리인" in t                              # 결재란
    sec811 = next(x for x in _sections(built) if "합성 총괄표" in _text(x))
    assert "[양식 2] 합성 총괄표" in _text(sec811)                  # 번호는 문서 전체 순서


def test_form_fills_page_with_empty_rows():
    rows = form_rows({"rows": 0})
    assert rows >= 10 and form_rows({"rows": 5}) == 5
    assert 31.5 + 8.2 + rows * 10.4 <= PAGE_BODY_MM
    assert form_rows({"rows": 0, "approval": True}) <= rows


def test_flow_columns_match_canonical_ratio():
    assert abs(sum(FLOW_COLS_MM) - 180.4) < 1e-6                   # 정본 흐름표 폭(본문폭보다 좁다)
    assert FLOW_COLS_MM == [38.8, 1.1, 113.1, 1.1, 26.3]


def test_long_flow_splits_into_page_tables(tmp_path):
    out = _build(tmp_path, _template(flow=_flow(14), forms=FULL["forms"]))
    x = _sec42(out)
    heads = len(re.findall(r"<hp:t>업무단계</hp:t>", x))
    assert heads >= 2                                              # 쪽마다 머리행 있는 표


def test_errors_are_loud(tmp_path):
    with pytest.raises(PartError, match="팀 목록"):
        _build(tmp_path, _template(roles=FULL["roles"]))            # 팀 없음
    with pytest.raises(PartError, match="없는 양식"):
        _build(tmp_path, _template(flow=_flow()))                   # 양식:syn_ledger 가 없다
    with pytest.raises(PartError, match="겹칩니다"):
        form_numbers([{"forms": [{"key": "a", "title": "x"}]}, {"forms": [{"key": "a", "title": "y"}]}])
    assert form_ref("양식:a, 8.1", {"a": 3}) == "양식 3, 8.1"


def test_default_teams_from_template(tmp_path):
    tpl = _template(roles=FULL["roles"])
    tpl["default_teams"] = TEAMS
    assert "현장대리인" in _text(_sec42(_build(tmp_path, tpl)))


@pytest.mark.skipif(VALIDATE is None, reason="hwpx-validate 없음")
def test_hwpx_validate(built):
    run_hwpx_validate(built)


# ── L7-D2: P5 부표 · P7 공사개요 · 품질관리자 목록 ───────────────────────

TABLES = [
    {"key": "t_a", "title": "합성 기준표", "subtitle": "1. 합성 가", "columns": ["등급", "구분", "기준"],
     "widths": [15, 20, 65], "rows": [["1", "낮음", "합성 기준 {공사명}"], ["2", "높음", "합성"]], "indent": True},
    {"key": "t_b", "title": "합성 기준표", "subtitle": "2. 합성 나", "columns": ["등급", "기준"],
     "rows": [["1", "합성"]], "indent": True},
    {"key": "t_c", "title": "합성 장비", "columns": ["시험기구", "규격", "단위", "수량", "비고"],
     "widths": [19.7, 32.2, 7.0, 7.0, 25.0], "source": "project.시험장비"},
    {"key": "t_d", "title": "합성 배치", "columns": ["직무", "등급", "배치기간", "비고"],
     "widths": [25.6, 25.5, 35.3, 13.6], "source": "project.없는목록"},
]


def test_tables_numbered_per_section_and_grouped(tmp_path):
    out = _build(tmp_path, _template(tables=TABLES), 시험장비=[{"시험기구": "합성 시험기", "규격": "합성 규격",
                                                              "단위": "대", "수량": "1"}])
    x = _sec42(out)
    t = _text(x)
    assert "[부표 1] 합성 기준표" in t and t.count("[부표 1]") == 1        # 같은 제목 두 표 = 부표 1 하나
    assert "[부표 2] 합성 장비" in t and "[부표 3] 합성 배치" in t
    assert "합성 기준 가상시 예시지구 공동주택 신축공사" in t                # 칸 값 치환
    assert "합성 시험기합성 규격대1" in t                                    # source 목록 → 행(열 이름 = 키)
    tbl = re.findall(r'<hp:tbl [^>]*>.*?</hp:tbl>', x, re.S)
    assert any('horzOffset="4706"' in b for b in tbl)                      # 안쪽 표: 본문 왼끝 + 16.6
    assert len(re.findall(r'<hp:p [^>]*pageBreak="1"[^>]*>(?:(?!</hp:p>).)*?\[부표', x, re.S)) == 3


def test_tables_order_after_flow_before_forms(tmp_path):
    out = _build(tmp_path, _template(**FULL, tables=TABLES[:1]), 팀=TEAMS)
    t = _text(_sec42(out))
    assert t.index("업무단계") < t.index("[부표 1]") < t.index("[양식 1]")


def test_table_errors(tmp_path):
    bad = [{"key": "x", "title": "합성", "columns": ["a", "b"], "widths": [100]}]
    with pytest.raises(PartError, match="widths"):
        _build(tmp_path, _template(tables=bad))
    with pytest.raises(PartError, match="project"):
        _build(tmp_path, _template(tables=[{"key": "x", "title": "합성", "columns": ["a"], "source": "시험장비"}]))


def test_overview_table_canonical_rows(tmp_path):
    tpl = _template(body_label="공사 개요", body=["{표:공사개요}"])
    out = _build(tmp_path, tpl, 대지면적="합성 면적", 규모="합성 규모", 설계자="", 건축면적="")
    t = _text(_sec42(out))
    assert "공 사 명가상시 예시지구 공동주택 신축공사" in t                 # 짧은 항목은 자간을 벌린다
    assert "대지면적합성 면적" in t and "공사규모합성 규모" in t
    assert "설 계 자" not in t and "건축면적" not in t                      # 값 없는 확장 키는 줄을 뺀다
    assert "구분내용" not in t                                              # 머리행 없음(정본)
    assert t.index("공사위치") < t.index("대지면적") < t.index("공사기간")   # 정본 순서


def test_quality_manager_list_fills_placeholder(tmp_path):
    tpl = _template(purpose="{품질관리자}가 합성 목적을 맡는다.")
    out = _build(tmp_path, tpl, 품질관리자=[{"직무": "품질관리자", "성명": "합성 성명", "등급": "고급"}])
    assert "합성 성명가 합성 목적을 맡는다." in "".join(_text(x) for x in _sections(out))


def test_flow_stage_bold_and_box_width(built):
    from danburn.plan_parts import STAGE_BOX_MM
    x = _sec42(built)
    assert STAGE_BOX_MM == (37.6, 10.0)
    w = round(37.6 / 2 * 7200 / 25.4)
    assert f'<hp:cellSz width="{2 * w}"' in x or f'width="{2 * w - 1}"' in x or f'width="{2 * w + 1}"' in x


# ── L7-D3: P6 조직도 ──────────────────────────────────────────────────

ORG = [{"직무": "합성회사", "상위": ""}, {"직무": "합성총괄", "성명": "합성 갑", "상위": "합성회사"},
       {"직무": "공사", "상위": "합성총괄"}, {"직무": "공무", "상위": "합성총괄"}, {"직무": "토목", "상위": "합성총괄"},
       {"직무": "책임", "성명": "합성 을", "상위": "공사"}, {"직무": "선임", "성명": "합성 병", "상위": "공사"},
       {"직무": "책임", "성명": "합성 정", "상위": "공무"}]


def _org_build(tmp, org):
    tpl = _template(body_label="현장 조직", body=["{표:조직}"])
    return _sec42(_build(tmp, tpl, 조직=org))


def test_org_tree_parsing():
    from danburn.plan_parts import org_tree
    assert org_tree([{"직무": "가", "성명": "x"}]) is None                     # 상위가 없으면 조직도 없음
    roots, kids = org_tree(ORG)
    assert roots == [0] and kids[1] == [2, 3, 4] and kids[2] == [5, 6]
    with pytest.raises(PartError, match="없습니다"):
        org_tree([{"직무": "가", "상위": "없는 직무"}])
    with pytest.raises(PartError, match="순환"):
        org_tree([{"직무": "가", "상위": "나"}, {"직무": "나", "상위": "가"}])


def test_org_chart_above_people_table(tmp_path):
    x = _org_build(tmp_path, ORG)
    t = _text(x)
    order = ["합성회사", "합성총괄", "합성 갑", "공      사", "공      무", "토      목", "책임합성 을", "직무성명자격담당업무"]
    assert [t.index(m) for m in order] == sorted(t.index(m) for m in order)
    table = t[t.index("직무성명자격담당업무"):]
    assert "합성회사" not in table and "합성 을" in table                   # 성명 없는 조직 단위는 표에서 빠짐
    with zipfile.ZipFile(tmp_path / "p.hwpx") as z:
        head = z.read("Contents/header.xml").decode("utf-8")
    assert 'faceColor="#DFE6F7"' in head                                    # 상자 머리칸 바탕


def test_org_without_parent_keeps_table_only(tmp_path):
    x = _org_build(tmp_path, [{"직무": "합성", "성명": "합성 갑"}])
    assert "합성 갑" in _text(x) and "faceColor" not in x


def test_org_many_children_wrap_into_tiers(tmp_path):
    org = [{"직무": "합성총괄", "성명": "합성 갑", "상위": ""}] + [
        {"직무": f"부서{i}", "성명": f"합성 {i}", "상위": "합성총괄"} for i in range(8)]
    t = _text(_org_build(tmp_path, org))
    assert all(f"부서{i}" in t for i in range(8))


# ── L7-D4: 가로 양식 · 2단 머리 · 아래 줄 · 옆 상자 · 본사/현장 구분 ─────────────

LAND = {"key": "syn_land", "title": "합성 가로 대장", "columns": [f"열{i}" for i in range(1, 16)], "landscape": True,
        "groups": [{"title": "합성 묶음", "span": 2, "start": 10}]}
SUM = {"key": "syn_sum2", "title": "합성 총괄", "columns": ["공종", "계획", "실시", "비고"],
       "groups": [{"title": "시험·검사 횟수", "span": 2, "start": 1}],
       "footer": ["작성일시 :   년  월  일", "작성자 :   (서명 또는 인)"]}


def _pagepr(xml):
    m = re.search(r'<hp:pagePr landscape="(\w+)" width="(\d+)" height="(\d+)"', xml)
    return m.group(1)


def test_landscape_form_gets_own_section_and_continues_numbers(tmp_path):
    forms = FULL["forms"] + [LAND, SUM]
    out = _build(tmp_path, _template(**dict(FULL, forms=forms)), 팀=TEAMS)
    secs = _sections(out)
    land = [x for x in secs if "] 합성 가로 대장" in _text(x)]
    assert len(land) == 1 and _pagepr(land[0]) == "NARROWLY"               # 가로(A4, OWPML 값)
    assert '<hp:startNum pageStartsOn="BOTH" page="0"' in land[0] and "<hp:newNum" not in land[0]   # 번호 이어짐
    assert "4.2 합성 절" in "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", re.search(r"<hp:header.*?</hp:header>", land[0], re.S).group(0)))
    back = secs[secs.index(land[0]) + 1]
    assert "합성 총괄" in _text(back) and _pagepr(back) == "WIDELY"          # 다음 양식은 다시 세로
    assert "<hp:newNum" not in back


def test_group_header_and_footer_lines(tmp_path):
    out = _build(tmp_path, _template(**dict(FULL, forms=FULL["forms"] + [SUM])), 팀=TEAMS)
    x = next(s for s in _sections(out) if "합성 총괄" in _text(s))
    t = _text(x)
    assert "공종시험·검사 횟수비고계획실시" in t                            # 윗줄 묶음 + 아랫줄 열
    assert t.index("작성일시") > t.index("계획") and "(서명 또는 인)" in t
    assert re.search(r'colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="2"', x)


def test_group_errors(tmp_path):
    bad = dict(SUM, key="bad", groups=[{"title": "x", "span": 3, "start": 3}])
    with pytest.raises(PartError, match="groups"):
        _build(tmp_path, _template(**dict(FULL, forms=FULL["forms"] + [bad])), 팀=TEAMS)
    bad = dict(SUM, key="bad", groups=[{"title": "x", "span": 2, "start": 0}, {"title": "y", "span": 2, "start": 1}])
    with pytest.raises(PartError, match="겹칩니다"):
        _build(tmp_path, _template(**dict(FULL, forms=FULL["forms"] + [bad])), 팀=TEAMS)


def test_landscape_form_rows_fit_shorter_page():
    assert form_rows(dict(LAND, rows=0)) < form_rows({"rows": 0})
    assert form_rows(dict(SUM, rows=0)) < form_rows({"rows": 0})             # 2단 머리·아래 줄만큼 줄 수가 준다


ORG_SIDE = [{"직무": "합성회사", "상위": "", "구분": "본사"}, {"직무": "합성총괄", "성명": "합성 갑", "상위": "합성회사"},
            {"직무": "품질관리자", "성명": "합성 을", "등급": "고급", "상위": "합성총괄", "배치": "옆"},
            {"직무": "품질관리자", "성명": "합성 병", "등급": "중급", "상위": "합성총괄", "배치": "옆"},
            {"직무": "안전관리자", "성명": "합성 정", "등급": "선임", "상위": "합성총괄", "배치": "옆"},
            {"직무": "공사", "상위": "합성총괄"}, {"직무": "공무", "상위": "합성총괄"}]


def test_org_side_boxes_and_split_line(tmp_path):
    x = _org_build(tmp_path, ORG_SIDE)
    t = _text(x)
    assert "↑  본사" in t and "↓  현장" in t
    assert t.index("합성회사") < t.index("↑  본사") < t.index("합성총괄")
    assert "품 질 관 리 자" in t and "고급합성 을" in t and "중급합성 병" in t   # 같은 직무 = 한 상자
    assert t.index("안 전 관 리 자") < t.index("공      사")                  # 옆 상자 띠가 부서 가로선보다 위
    with zipfile.ZipFile(tmp_path / "p.hwpx") as z:
        head = z.read("Contents/header.xml").decode("utf-8")
    assert 'type="DASH"' in head                                             # 점선 구분선


# ── L7-D5: 가로 양식 빈 줄 채움 · 조직도 구성원 칸 ────────────────────────

def test_landscape_rows_fill_to_page_end():
    from danburn.plan_parts import FORM_HEAD_MM, FORM_ROW_MM, FORM_TOP_MM, LAND_BODY_MM, SAFETY_MM
    for f in (dict(LAND, rows=0), dict(LAND, rows=0, groups=[])):
        heads = 2 if f.get("groups") else 1
        used = sum(FORM_TOP_MM.values()) + heads * FORM_HEAD_MM + form_rows(f) * FORM_ROW_MM
        assert used <= LAND_BODY_MM - SAFETY_MM < used + FORM_ROW_MM          # 한 줄 더 넣으면 넘친다 = 끝까지 참


def _member_cells(x, name):
    """이름이 든 칸과 같은 행의 구성원 칸들(colSpan·cellSz·글자 모양)."""
    tc = re.findall(r"<hp:tc .*?</hp:tc>", x, re.S)
    row = next(t for t in tc if f">{name}<" in t)
    r = re.search(r'rowAddr="(\d+)"', row).group(1)
    return [t for t in tc if f'rowAddr="{r}"' in t and "<hp:t>" in t and re.search(r"<hp:t>[^<]+</hp:t>", t)]


def test_org_member_row_one_line_even_split(tmp_path):
    org = [{"직무": "합성총괄", "성명": "합성 갑", "상위": ""}, {"직무": "공사", "상위": "합성총괄"},
           {"직무": "공무", "상위": "합성총괄"},
           {"직무": "합성 공사 담당", "성명": "합성 담당 기", "상위": "공사"},      # 직급 없음 → 왼칸 넓게
           {"직무": "책임", "직급": "책임", "성명": "합성 을", "상위": "공무"}]
    x = _org_build(tmp_path, org)
    cells = _member_cells(x, "합성 담당 기")
    mine = [c for c in cells if ">합성 공사 담당<" in c or ">합성 담당 기<" in c]
    widths = [int(re.search(r'<hp:cellSz width="(\d+)"', c).group(1)) for c in mine]
    assert len(widths) == 2 and abs(widths[0] - widths[1]) <= 2                    # 직무를 쓰면 반반
    assert all("\n" not in re.search(r"<hp:t>([^<]*)</hp:t>", c).group(1) for c in cells)
    ids = {re.search(r'charPrIDRef="(\d+)"', c).group(1) for c in mine}
    assert len(ids) == 1                                                            # 한 표 안 같은 글자 크기
    t = _text(x)
    assert "책임합성 을" in t                                                      # 직급이 있으면 직급 | 성명


# ── L7-D6: 고지 꼬리말 기본 끔 ─────────────────────────────────────────

def test_notice_footer_off_by_default_on_with_option(tmp_path):
    tpl = _template(**FULL)
    off = _build(tmp_path, tpl, 팀=TEAMS)
    assert not any("<hp:footer" in x for x in _sections(off))
    on = tmp_path / "on.hwpx"
    build_plan(_rows(), _project(팀=TEAMS), on, basis_version="합성", revision=0, date="2026. 01. 05.",
               template=tpl, notice_footer=True)
    secs = _sections(on)
    assert all("공개 문서를 참고하여 개발하였습니다" in re.search(r"<hp:footer .*?</hp:footer>", x, re.S).group(0)
               for x in secs)                                              # 켜면 모든 구역(표지·8.11·양식 포함)
