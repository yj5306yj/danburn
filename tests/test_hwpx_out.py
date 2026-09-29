"""8.11 HWPX 모양(L3-T1, docs/design/8.11-layout.md) — 합성 행만 쓴다."""
import re
import zipfile
from pathlib import Path

import pytest
from hwpx import HwpxDocument

from danburn.hwpx_out import (LOGO_COL_MM, UNLISTED_WIDTHS_MM, WIDTHS_MM, add_811_tables, add_unlisted_table, build_811, merge_plan,
                             unlisted_items)
from danburn.model import PlanRow
from conftest import VALIDATE, find_hwpx_validate, run_hwpx_validate

REBAR_TEST = "겉모양, 치수, 무게, 인장강도"
REBAR_FREQ = "KS제품: 제조회사 및 제품규격별"


def _concrete(disc, spec, qty, work=""):
    tests = [("슬럼프", "120㎥마다", 3), ("공기량", "120㎥마다", 3), ("압축강도", "360㎥마다", 4)]
    return [PlanRow(disc, work, f"레미콘({spec})", t, qty, "㎥", f, f"{qty:,}㎥/120㎥", n, material="ready_mixed_concrete",
                    spec=spec, note="합성 비고" if t == "압축강도" else "")
            for t, f, n in tests]


def _rebar(disc, spec, qty):
    return PlanRow(disc, "", f"철근({spec})", REBAR_TEST, qty, "ton", REBAR_FREQ, "KS자재 1회", 0, 1,
                   material="rebar", spec=spec)


def _rows():
    return (_concrete("건축", "25-24-150", 480) + _concrete("건축", "25-18-80", 240)
            + [_rebar("건축", "SD400 D13", 12.5), _rebar("건축", "SD500 D16", 8)]
            + _concrete("토목", "25-21-150", 360))


def _first_plan_table(x):
    """쪽 머리 표가 아닌 첫 8.11 표(repeatHeader=1) XML."""
    i = re.search(r'<hp:tbl [^>]*repeatHeader="1"', x).start()
    return x[i:x.index("</hp:tbl>", i)]


def _xml(path, part="Contents/section0.xml"):
    with zipfile.ZipFile(path) as z:
        return z.read(part).decode("utf-8")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return build_811(_rows(), tmp_path_factory.mktemp("h") / "o.hwpx", basis_version="합성 기준판",
                     generated_note="합성 주석", revision="Rev.2", date="2026-01-05")


def test_no_embedded_font_and_hamchorom_only(built):
    head = _xml(built, "Contents/header.xml")
    assert 'isEmbedded="1"' not in head
    faces = set(re.findall(r'<hh:font [^>]*face="([^"]+)"', head))
    assert faces and all(f.startswith("함초롬") for f in faces)


def test_portrait_a4_schema_orientation(built, tmp_path):
    pp = re.search(r'<hp:pagePr landscape="(\w+)" width="(\d+)" height="(\d+)"', _xml(built))
    assert pp.groups() == ("WIDELY", "59528", "84189")
    wide = build_811(_rows(), tmp_path / "l.hwpx", landscape=True)
    pp = re.search(r'<hp:pagePr landscape="(\w+)" width="(\d+)" height="(\d+)"', _xml(wide))
    assert pp.groups() == ("NARROWLY", "59528", "84189")          # 한컴 방식: 세로 치수 + 방향 속성


def test_page_header_title_revision_and_page_number(built):
    x = _xml(built)
    header = re.search(r"<hp:header .*?</hp:header>", x, re.S).group(0)
    text = "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", header))
    assert "품질관리계획서" in text and "8.11 검사 및 시험, 모니터링" in text
    assert "2026.01.05. [Rev.2] " in text and text.endswith("p.")
    assert 'numType="PAGE"' in header and "<hp:pageNum" not in header   # 쪽 번호는 머리말 안 한 곳에만
    assert "<hp:footer" not in x                                         # 고지 줄은 기본으로 넣지 않는다(L7-D6)


def test_notice_footer_option(tmp_path):
    out = build_811(_rows(), tmp_path / "n.hwpx", notice_footer=True)
    footer = re.search(r"<hp:footer .*?</hp:footer>", _xml(out), re.S).group(0)
    assert "공개 문서를 참고하여 개발하였습니다" in footer
    m = re.search(r'<hp:margin header="\d+" footer="(\d+)"', _xml(out))
    assert m and int(m.group(1)) == round(9.2 * 7200 / 25.4)            # 꼬리말 여백은 고지 유무와 같다


def test_one_table_per_discipline_with_widths_and_header_rows(built):
    x = _xml(built)
    body = x.split("</hp:secPr>", 1)[1]
    assert "[건축공사]" in body and "[토목공사]" in body
    tbls = re.findall(r'<hp:tbl [^>]*repeatHeader="1"[^>]*rowCnt="(\d+)" colCnt="12"', body)
    assert [int(n) for n in tbls] == [2 + 8, 2 + 3]
    first = _first_plan_table(body)
    row0 = first.split("</hp:tr>", 1)[0]
    widths = [int(w) for w in re.findall(r'<hp:cellSz width="(\d+)"', row0)]
    assert widths[0] == round(WIDTHS_MM[0] * 7200 / 25.4)
    assert re.search(r'colAddr="6" rowAddr="0"/><hp:cellSpan colSpan="2" rowSpan="1"', row0)   # 시험빈도
    assert re.search(r'colAddr="8" rowAddr="0"/><hp:cellSpan colSpan="3" rowSpan="1"', row0)   # 계획시험횟수
    heads = "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", first.split("</hp:tr>", 2)[0] + first.split("</hp:tr>", 2)[1]))
    for h in ("시험품목", "시험종목", "시험방법", "계획물량", "계획시험횟수", "의뢰"):          # L14-E 칸 이름
        assert h in heads
    assert 'width="0.4 mm"' in _xml(built, "Contents/header.xml")                             # 바깥 굵은 선


def test_merge_plan_groups_work_item_and_rebar_bundle():
    rows = _rows()[:8]                       # 건축: 레미콘 2규격 × 3행 + 철근 2규격
    plan = merge_plan(rows)
    assert plan[0] == [(0, 7)]               # 공종: 비어 있으면 자재 기본 공종으로 한 칸
    assert plan[1] == [(0, 2), (3, 5), (6, 6), (7, 7)]   # 시험항목: 규격마다
    assert plan[4] == plan[1]                # 계획물량: 시험품목과 같이
    assert (6, 7) in plan[2] and (6, 7) in plan[6] and (6, 7) in plan[7]   # 철근 규격 묶음의 시험종목·빈도·근거
    assert (6, 7) in plan[3]                 # 시험방법도 같은 묶음이면 병합(빈칸이어도)
    assert plan[5] == [(0, 2), (3, 5), (6, 7)]
    assert plan[8] == [(i, i) for i in range(8)]   # 계획시험횟수는 병합하지 않는다


def test_merged_cells_are_omitted_and_work_is_stacked(built):
    body = _xml(built).split("</hp:secPr>", 1)[1]
    first = _first_plan_table(body)
    assert re.search(r'colAddr="0" rowAddr="2"/><hp:cellSpan colSpan="1" rowSpan="8"', first)
    assert not re.search(r'colAddr="0" rowAddr="3"', first)          # 덮인 셀은 쓰지 않는다
    cell0 = first[first.index('<hp:tc name="" header="0"'):]
    cell0 = cell0[:cell0.index("</hp:tc>")]
    assert re.findall(r"<hp:t>([^<]*)</hp:t>", cell0) == list("철근콘크리트공사")


def test_add_811_tables_fills_given_section(tmp_path):
    doc = HwpxDocument.new()
    doc.add_section()
    sec = add_811_tables(doc, _rows(), section=doc.sections[1], landscape=True)
    assert sec is doc.sections[1]
    out = tmp_path / "two.hwpx"
    doc.save_to_path(str(out))
    assert "<hp:tbl" in _xml(out, "Contents/section1.xml") and "<hp:tbl" not in _xml(out)


@pytest.mark.skipif(VALIDATE is None, reason="hwpx-validate 없음")
def test_hwpx_validate_passes(built):
    run_hwpx_validate(built)


def test_validator_is_found_when_python_hwpx_installed():
    """python-hwpx 는 런타임 의존성이라 검사기가 설치돼 있다 — 못 찾으면 건너뛰지 말고 실패(W08)."""
    pytest.importorskip("hwpx.tools.validator")
    assert VALIDATE is not None, "python-hwpx 는 있는데 hwpx-validate 실행 파일을 못 찾음"


@pytest.mark.parametrize("name", ["hwpx-validate", "hwpx-validate.exe"])
def test_find_validator_in_venv_scripts(tmp_path, monkeypatch, name):
    """맥·리눅스 bin/hwpx-validate, Windows Scripts\\hwpx-validate.exe 모두 찾는다."""
    monkeypatch.setenv("PATH", "")
    (tmp_path / name).write_text("")
    assert find_hwpx_validate(tmp_path) == tmp_path / name
    assert find_hwpx_validate(tmp_path / "없음") is None


# ── L3-T4 로고·회사명 칸 ─────────────────────────────────────────────
def _header(path):
    return re.search(r"<hp:header .*?</hp:header>", _xml(path), re.S).group(0)


def _header_rule_rows(path):
    """쪽 머리 표의 칸 배치(열 주소·폭·병합) — 로고 유무로 바뀌면 안 된다."""
    h = _header(path)
    outer = h[h.index("<hp:tbl "):]
    cells = re.findall(r'<hp:cellAddr colAddr="(\d)" rowAddr="(\d)"/><hp:cellSpan colSpan="(\d)" '
                       r'rowSpan="(\d)"/><hp:cellSz width="(\d+)" height="(\d+)"', outer)
    return cells[-4:]   # 로고 칸 안쪽 표의 칸은 로고 칸 주소보다 먼저 나온다 → 마지막 넷이 바깥 표(로고·문서명·절 제목·개정)


@pytest.fixture(scope="module")
def logo_png(tmp_path_factory):
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    img = Image.new("RGB", (200, 160), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse((40, 10, 160, 110), fill=(30, 120, 200))
    draw.rectangle((50, 120, 150, 150), fill=(200, 60, 40))
    path = tmp_path_factory.mktemp("logo") / "synthetic-logo.png"
    img.save(path)
    return path


def test_no_logo_keeps_empty_logo_cell(built):
    h = _header(built)
    assert "<hp:pic " not in h
    w = round(LOGO_COL_MM * 7200 / 25.4)
    assert re.search(rf'colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="2"/><hp:cellSz width="{w}"', h)
    with zipfile.ZipFile(built) as z:
        assert not [n for n in z.namelist() if n.startswith("BinData/")]


def test_logo_and_company_are_placed(tmp_path, logo_png, built):
    out = build_811(_rows(), tmp_path / "logo.hwpx", logo=logo_png, company="샘플건설", revision="Rev.2",
                    date="2026-01-05", basis_version="합성 기준판", generated_note="합성 주석")
    h = _header(out)
    assert h.count("<hp:pic ") == 1
    w, hgt = (int(x) for x in re.search(r'<hp:curSz width="(\d+)" height="(\d+)"', h).groups())
    assert abs(w / hgt - 200 / 160) < 0.01                       # 비율 유지
    assert w <= round(13.2 * 7200 / 25.4) and hgt <= round((12.1 - 3.5) * 7200 / 25.4) + 1   # 상자 안
    assert "샘플건설" in re.findall(r"<hp:t>([^<]*)</hp:t>", h)
    with zipfile.ZipFile(out) as z:
        assert [n for n in z.namelist() if n.startswith("BinData/")] == ["BinData/BIN0001.png"]
    assert _header_rule_rows(out) == _header_rule_rows(built)    # 로고가 있어도 쪽 머리 칸·선 위치 그대로
    if VALIDATE is not None:
        run_hwpx_validate(out)


def test_company_without_logo(tmp_path):
    out = build_811(_rows(), tmp_path / "name.hwpx", company="샘플건설")
    h = _header(out)
    assert "<hp:pic " not in h and "샘플건설" in h


def test_logo_must_be_png_or_jpeg(tmp_path):
    bad = tmp_path / "logo.gif"
    bad.write_bytes(b"GIF89a" + b"\0" * 20)
    with pytest.raises(ValueError, match="PNG 또는 JPEG"):
        build_811(_rows(), tmp_path / "x.hwpx", logo=bad)


def test_jpeg_logo_size_is_read(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    jpg = tmp_path / "synthetic-logo.jpg"
    Image.new("RGB", (120, 240), (20, 90, 160)).save(jpg, "JPEG")
    out = build_811(_rows(), tmp_path / "j.hwpx", logo=jpg)
    w, hgt = (int(x) for x in re.search(r'<hp:curSz width="(\d+)" height="(\d+)"', _header(out)).groups())
    assert abs(w / hgt - 0.5) < 0.01 and hgt <= round(12.1 * 7200 / 25.4) + 1


# ── L4-D1 시험계획 미작성 자재 표 ─────────────────────────────────────
def _unlisted():
    return unlisted_items(
        uncovered=[{"key": "synthetic_a", "label": "합성자재가", "page": 12, "lines": 7, "examples": ["합성 품명"]}],
        owner_standard_needed=[{"key": "synthetic_b", "label": "합성자재나", "lines": 3, "examples": []}],
        site_measurements=[{"key": "synthetic_c", "label": "합성 현장측정", "basis": "합성 고시 — 넣을지 확인"}])


def _unlisted_tables(body):
    return re.findall(r'<hp:tbl [^>]*repeatHeader="1"[^>]*rowCnt="(\d+)" colCnt="5".*?</hp:tbl>', body, re.S)


def test_unlisted_items_from_summary():
    items = _unlisted()
    assert [i["kind"] for i in items] == ["uncovered", "owner_standard", "site_measurement"]
    assert [i["basis"] for i in items[:2]] == ["별표2 p.12", "별표2 밖"]


def test_unlisted_table_after_811_tables(tmp_path):
    out = build_811(_rows(), tmp_path / "u.hwpx", basis_version="합성 기준판", unlisted=_unlisted())
    body = _xml(out).split("</hp:secPr>", 1)[1]
    assert re.findall(r'<hp:tbl [^>]*rowCnt="(\d+)" colCnt="5"', body) == ["4"]     # 머리 1 + 항목 3
    i = body.index("[시험계획 미작성 자재 (확인 필요)]")
    assert body.rindex('colCnt="12"') < i < body.index("근거 기준: 합성 기준판")          # 8.11 표 뒤, 주석 앞
    tbl = body[i:body.index("</hp:tbl>", i)]
    texts = re.findall(r"<hp:t>([^<]*)</hp:t>", tbl)
    for t in ("구분", "내역 행 수", "규칙 없음", "발주처 기준 필요", "현장측정 확인", "별표2 p.12", "별표2 밖", "7", "-",
              "시험계획 작성 후 8.11에 추가"):
        assert t in texts
    widths = [int(w) for w in re.findall(r'<hp:cellSz width="(\d+)"', tbl.split("</hp:tr>", 1)[0])]
    assert widths == [round(x * 7200 / 25.4) for x in UNLISTED_WIDTHS_MM]
    if VALIDATE is not None:
        run_hwpx_validate(out)


def test_no_unlisted_items_no_table(tmp_path, built):
    out = build_811(_rows(), tmp_path / "n.hwpx", unlisted=[])
    for path in (out, built):
        x = _xml(path)
        assert 'colCnt="5"' not in x and "시험계획 미작성 자재" not in x
    doc = HwpxDocument.new()
    assert add_unlisted_table(doc, doc.sections[0], None) is False


def test_unlisted_custom_action_and_title(tmp_path):
    doc = HwpxDocument.new()
    items = [{"kind": "uncovered", "label": "합성자재", "basis": "별표2 p.1", "lines": 1200, "action": "합성 조치"}]
    assert add_unlisted_table(doc, doc.sections[0], items, title="합성 제목") is True
    out = tmp_path / "c.hwpx"
    doc.save_to_path(str(out))
    texts = re.findall(r"<hp:t>([^<]*)</hp:t>", _xml(out))
    assert "[합성 제목]" in texts and "합성 조치" in texts and "1,200" in texts


def test_compact_date_and_header_title_fit():
    from danburn.hwpx_out import _fit_pt, compact_date
    assert compact_date("2026. 1. 5.") == "2026.01.05." and compact_date("2026-01-05", dot=False) == "2026.01.05"
    assert compact_date("미정") == "미정"
    assert _fit_pt("8.11 검사 및 시험, 모니터링", 116, 13.5) == 13.5
    assert _fit_pt("긴 제목 " * 20, 116, 13.5) == 9                 # 한 줄에 안 들어가면 줄인다(최소 9)


def test_811_columns_follow_canonical_widths():
    assert abs(sum(WIDTHS_MM) - 181.0) < 1e-6
    assert WIDTHS_MM[2] == 30.1 and WIDTHS_MM[3] == 18.0 and WIDTHS_MM[7] == 26.3 and WIDTHS_MM[11] == 7.6   # L14-E 시험방법 칸


def _many_rows(n_specs=30):
    """한 공종(철근콘크리트공사)에 레미콘 규격 n_specs 개 → 표가 여러 쪽으로 넘어간다(합성)."""
    return [r for i in range(n_specs) for r in _concrete("건축", f"25-{18 + i}-150", 100 + i, work="철근콘크리트공사")]


def test_page_chunks_restart_merges_so_every_page_names_the_work(tmp_path):
    from danburn.hwpx_out import _table_height_mm, page_chunks
    rows = _many_rows()
    widths = list(WIDTHS_MM)
    chunks = page_chunks(rows, widths, 200, 230)
    assert len(chunks) > 1 and [r for c in chunks for r in c] == rows
    assert _table_height_mm(chunks[0], widths) <= 200
    assert all(_table_height_mm(c, widths) <= 230 for c in chunks[1:])
    out = build_811(rows, tmp_path / "p.hwpx")
    x = re.sub(r"<hp:header.*?</hp:header>", "", _xml(out), flags=re.S)
    tables = re.findall(r'<hp:tbl [^>]*repeatHeader="1".*?</hp:tbl>', x, re.S)
    assert len(tables) > 1                                       # 쪽마다 표 하나
    for t in tables:                                             # 쪽마다 공종 칸(0열 본문 첫 칸)에 이름이 있다
        cell = re.search(r'<hp:tc [^>]*>(?:(?!</hp:tc>).)*?colAddr="0" rowAddr="2"', t, re.S).group(0)
        assert "철" in "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", cell))
    assert len(re.findall(r'<hp:p [^>]*pageBreak="1"', x)) >= len(tables) - 1   # 이어지는 표는 새 쪽에서


def test_long_test_item_is_set_smaller_instead_of_wrapping():
    from danburn.hwpx_out import ITEM_PT_STEPS, _cell_pt
    assert _cell_pt(1, "레미콘\n(25-24-150)", WIDTHS_MM[1]) == 8
    long = "시멘트계 액체형 방수제\n(건조모르타르 조적벽 h=0~200 MM구간)"
    assert ITEM_PT_STEPS[-1] <= _cell_pt(1, long, WIDTHS_MM[1]) < 8
    assert _cell_pt(2, "아무 글", WIDTHS_MM[2]) == 6.5 and _cell_pt(4, "1,000", WIDTHS_MM[4]) == 8
    assert _cell_pt(3, "KS F 2402", WIDTHS_MM[3]) == 6.5                   # 시험방법은 작은 글
