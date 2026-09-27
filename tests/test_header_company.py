"""쪽 머리 로고 칸의 긴 회사명(L13-H1) — 합성 회사명만 쓴다.

회사명은 글을 바꾸거나 자르지 않고 글자 크기·장평·줄 수(≤2)만 바꾸며, 로고 칸·쪽 머리 표 높이와 선 위치는 그대로다.
"""
import re

import pytest

from danburn.hwpx_out import (COMPANY_LINE_MM, COMPANY_PT_STEPS, COMPANY_RATIO_STEPS, LOGO_BOX_MM, MM, build_811,
                             company_fit)
from conftest import VALIDATE, run_hwpx_validate
from test_hwpx_out import _header, _header_rule_rows, _rows, logo_png  # noqa: F401 (fixture)

SHORT, MID, LONG = "합성건설", "샘플건설 주식회사", "가상 종합건설 엔지니어링 주식회사 품질관리팀"
EXPECT = {  # 회사명 → (글자 크기, 장평, 줄 수)
    SHORT: (8, 100, 1),              # 그대로 한 줄
    MID: (8, 100, 2),                # 6pt 한 줄로도 넘친다 → 어절 경계 두 줄(8pt 로 들어간다)
    LONG: (6, 70, 2),                # 하한 6pt·장평 70% 에서 글자 경계 두 줄
}


@pytest.mark.parametrize("company", [SHORT, MID, LONG])
def test_company_fit_steps(company):
    fit = company_fit(company)
    assert (fit["pt"], fit["ratio"], len(fit["lines"])) == EXPECT[company]
    assert fit["fits"] and fit["pt"] in COMPANY_PT_STEPS and fit["ratio"] in COMPANY_RATIO_STEPS
    assert "".join(fit["lines"]) == company                      # 한 글자도 바꾸거나 자르지 않는다
    assert fit["height_mm"] == COMPANY_LINE_MM if len(fit["lines"]) == 1 else fit["height_mm"] > COMPANY_LINE_MM


def test_one_line_shrinks_before_two_lines():
    fit = company_fit("합성종합건설")                            # 8pt 로는 칸보다 넓다
    assert len(fit["lines"]) == 1 and COMPANY_PT_STEPS[-1] <= fit["pt"] < COMPANY_PT_STEPS[0]
    assert company_fit("가" * 60)["fits"] is False               # 하한에서도 안 들어가면 표시만(글은 그대로)
    assert "".join(company_fit("가" * 60)["lines"]) == "가" * 60


def _name_cell(h):
    """로고 칸 안쪽 표의 회사명 칸: (높이, 문단 글들, 글자 모양 id)."""
    inner = h[re.search(r'<hp:tbl [^>]*colCnt="1"', h).start():]
    cells = re.findall(r"<hp:tc [^>]*>.*?</hp:tc>", inner[:inner.index("</hp:tbl>")], re.S)
    name = cells[-1]                                              # 안쪽 표 마지막 줄 = 회사명
    height = int(re.search(r'<hp:cellSz width="\d+" height="(\d+)"', name).group(1))
    return height, re.findall(r"<hp:t>([^<]*)</hp:t>", name), set(re.findall(r'<hp:run charPrIDRef="(\d+)"', name))


@pytest.mark.parametrize("company", [SHORT, MID, LONG])
def test_header_keeps_slot_and_lines(tmp_path, logo_png, company):  # noqa: F811
    base = build_811(_rows(), tmp_path / "base.hwpx", logo=logo_png)
    out = build_811(_rows(), tmp_path / "name.hwpx", logo=logo_png, company=company)
    assert _header_rule_rows(out) == _header_rule_rows(base)      # 쪽 머리 칸 높이·폭·선 위치 그대로
    h = _header(out)
    fit = company_fit(company)
    height, texts, _ = _name_cell(h)
    assert texts == fit["lines"] and len(texts) <= 2 and "".join(texts) == company
    assert height == round(fit["height_mm"] * MM)
    pic_h = int(re.search(r'<hp:curSz width="\d+" height="(\d+)"', h).group(1))
    assert pic_h <= round((LOGO_BOX_MM[1] - fit["height_mm"]) * MM) + 1   # 두 줄이면 그림 상자를 그만큼 줄인다
    inner = re.search(r'<hp:tbl [^>]*rowCnt="2" colCnt="1"[^>]*><hp:sz width="\d+" widthRelTo="ABSOLUTE" '
                      r'height="(\d+)"', h)
    assert int(inner.group(1)) <= round(sum((7.0, 8.0)) * MM)     # 안쪽 표가 로고 칸(15mm) 안
    if VALIDATE is not None:
        run_hwpx_validate(out)


def test_ratio_written_to_char_shape(tmp_path):
    import zipfile
    out = build_811(_rows(), tmp_path / "long.hwpx", company=LONG)
    _, _, cids = _name_cell(_header(out))
    with zipfile.ZipFile(out) as z:
        head = z.read("Contents/header.xml").decode("utf-8")
    for cid in cids:
        pr = re.search(rf'<hh:charPr id="{cid}" height="(\d+)".*?<hh:ratio hangul="(\d+)"', head, re.S)
        assert (int(pr.group(1)), int(pr.group(2))) == (600, 70)
