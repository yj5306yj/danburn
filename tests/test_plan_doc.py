"""품질관리계획서 전체(L3-T2·L3-T5): 합성 project + 합성 8.11 행 → HWPX 한 권, 전부 A4 세로."""
import re
import struct
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

import pytest
import yaml

from danburn.model import PlanRow
from danburn.plan_doc import PlaceholderError, build_plan, load_template, placeholders, toc_entries

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "src" / "danburn" / "data" / "templates" / "project.example.yaml"
VALIDATE = Path(sys.executable).parent / "hwpx-validate"


def _project(**kw):
    p = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    p.update(kw)
    return p


def _rows():
    return [
        PlanRow("건축", "콘크리트", "레미콘 25-24-150", "슬럼프", 1000, "m3", "120㎥마다", "1,000/120", 9),
        PlanRow("토목", "철근", "SD400 D13", "인장강도", 30, "ton", "50t마다", "30/50", 1),
    ]


def _png(path, w=60, h=20):
    """합성 단색 PNG(실제 로고 아님)."""
    raw = b"".join(b"\x00" + bytes([40, 90, 160]) * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return path


def _sections(path):
    with zipfile.ZipFile(path) as z:
        names = sorted((n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)),
                       key=lambda n: int(re.search(r"\d+", n).group()))
        return [z.read(n).decode("utf-8") for n in names]


def _text(xml):
    return "".join(re.findall(r"<hp:t(?:\s[^>]*)?>([^<]*)</hp:t>", xml))


REV1 = {"개정": 1, "일자": "2026. 06. 01.", "장": ["5.2", "8.11"], "사유": "합성 개정 사유"}


def _project_rev1(**kw):
    """예시(Rev.0만) + 테스트용 Rev.1 줄."""
    p = _project(**kw)
    p["개정이력"] = [*p["개정이력"], dict(REV1)]
    return p


def _build(tmp, **kw):
    out = tmp / "plan.hwpx"
    build_plan(_rows(), _project_rev1(**kw), out, basis_version="합성 기준판", revision=1, date="2026. 06. 01.")
    return out


def _validate(path):
    r = subprocess.run([str(VALIDATE), str(path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("plan"))


def test_all_chapter_and_section_titles_present(built):
    text = "".join(_text(x) for x in _sections(built))
    for no, title, _ in toc_entries(load_template()):
        assert title in text, f"{no} {title} 없음"
    for front in ("품질관리계획서", "A. 목차", "B. 승인 및 개정이력"):
        assert front in text


def test_no_unfilled_placeholders(built):
    text = "".join(_text(x) for x in _sections(built))
    assert not re.findall(r"\{[^{}]+\}", text)
    assert "가상시 예시지구 공동주택 신축공사" in text     # 자리표시가 실제로 채워졌다


def test_every_section_is_a4_portrait(built):
    for x in _sections(built):
        m = re.search(r'<hp:pagePr landscape="(\w+)" width="(\d+)" height="(\d+)"', x)
        assert int(m.group(2)) < int(m.group(3))                   # A4 치수는 늘 세로값, 방향은 landscape 값으로
        if m.group(1) == "NARROWLY":                                # 가로는 landscape 양식 구역에만
            assert "[양식" in _text(x).replace(" ", "")
        else:
            assert m.group(1) == "WIDELY"                           # 스키마 값 세로("PORTRAIT" 금지)


def test_811_table_inside_its_section_after_procedure(built):
    hit = [x for x in _sections(built) if "레미콘 25-24-150" in _text(x)]
    assert len(hit) == 1                                         # 8.11 표는 8.11 절 구역 한 곳에만
    t = _text(hit[0])
    assert t.index("공정 단계별 검사 및 시험 계획") < t.index("품질시험 및 검사계획") < t.index("레미콘 25-24-150")
    assert "SD400 D13" in t and "<hp:tbl" in hit[0]


def test_page_header_per_unit_restarts_page_numbers(built):
    secs = _sections(built)
    assert all("<hp:header" in x for x in secs[1:])              # 표지 말고 모든 구역에 쪽 머리
    assert all('numType="PAGE"' in x for x in secs[1:])
    wide = lambda x: 'landscape="NARROWLY"' in x
    # 가로 양식 구역과 그 뒤 세로로 돌아오는 구역은 앞 단위 쪽 번호에 이어진다
    units = [x for i, x in enumerate(secs) if i >= 1 and not wide(x) and not wide(secs[i - 1])]
    assert all("<hp:newNum" in x for x in units)
    unit = next(x for x in secs if "공사 개요" in _text(x))
    assert "4.1 건설공사의 정보" in _text(unit)


def test_revision_history_and_toc_revision(built):
    text = "".join(_text(x) for x in _sections(built)[:3])
    assert "최초 제정" in text and "합성 개정 사유" in text


def _meta(xml):
    """쪽 머리의 (일자, 개정 번호)."""
    m = re.search(r"([\d. ]+?)\s*\[Rev\.(\d+)\]", _text(xml))
    return (m.group(1).strip(), int(m.group(2))) if m else None


def test_cover_toc_headers_history_agree_on_current_revision(built):
    secs = _sections(built)
    cover = _text(secs[0])
    assert "개정번호 :  Rev.1개정일자 :  2026. 06. 01." in cover   # 표지 = revision 인자
    assert _meta(secs[1]) == ("2026.06.01.", 1)                  # A. 목차 쪽 머리(정본 표기 YYYY.MM.DD.)
    assert _meta(secs[2]) == ("2026.06.01.", 1)                  # B. 이력 쪽 머리
    toc = _text(secs[1])
    assert "A목차12026.06.01" in toc and "B승인 및 개정이력12026.06.01" in toc
    hist = _text(secs[2])
    # 마지막 줄 = 현재 개정. 개정 장 번호는 절 제목까지 적는다(정본과 같음)
    assert hist.index("최초 제정") < hist.index("12026.06.01.5.2 책임 및 권한8.11 검사 및 시험, 모니터링합성 개정 사유")
    metas = [_meta(x) for x in secs[1:]]
    assert all(m is not None for m in metas)
    assert max(n for _, n in metas) == 1                          # 어떤 쪽 머리도 현재 개정을 넘지 않는다
    by_title = {t: _meta(x) for x in secs[1:] for t in ("5.2 책임 및 권한", "8.11 검사 및 시험, 모니터링",
                                                          "4.1 건설공사의 정보") if t in _text(x)[:200]}
    assert by_title["5.2 책임 및 권한"] == ("2026.06.01.", 1)
    assert by_title["8.11 검사 및 시험, 모니터링"] == ("2026.06.01.", 1)
    assert by_title["4.1 건설공사의 정보"] == ("2026.01.05.", 0)    # 안 바뀐 절은 제정 개정


def test_history_newer_than_revision_is_rejected(tmp_path):
    out = tmp_path / "x.hwpx"
    with pytest.raises(ValueError, match="Rev.1"):
        build_plan(_rows(), _project_rev1(), out, basis_version="합성", revision=0, date="2026. 01. 05.")
    assert not out.exists()


def test_same_revision_with_different_date_is_rejected(tmp_path):
    out = tmp_path / "x.hwpx"
    with pytest.raises(ValueError, match="일자"):
        build_plan(_rows(), _project_rev1(), out, basis_version="합성", revision=1, date="2026. 09. 26.")
    assert not out.exists()


def test_same_revision_date_in_other_format_uses_history_text(tmp_path):
    out = tmp_path / "x.hwpx"
    build_plan(_rows(), _project_rev1(), out, basis_version="합성", revision=1, date="2026-06-01")
    secs = _sections(out)
    assert "개정일자 :  2026. 06. 01." in _text(secs[0]) and _meta(secs[1]) == ("2026.06.01.", 1)


def test_missing_current_revision_is_appended(tmp_path):
    out = tmp_path / "x.hwpx"
    build_plan(_rows(), _project(), out, basis_version="합성", revision=2, date="2026. 09. 26.")
    secs = _sections(out)
    assert "개정번호 :  Rev.2" in _text(secs[0]) and _meta(secs[2]) == ("2026.09.26.", 2)


def test_example_project_builds_as_rev0(tmp_path):
    out = tmp_path / "x.hwpx"
    build_plan(_rows(), _project(), out, basis_version="합성", revision=0, date="2026. 01. 05.")
    secs = _sections(out)
    assert "개정번호 :  Rev.0" in _text(secs[0])
    assert {_meta(x) for x in secs[1:]} == {("2026.01.05.", 0)}


def test_company_name_without_logo_keeps_slot(built):
    with zipfile.ZipFile(built) as z:
        assert not [n for n in z.namelist() if n.startswith("BinData/")]
    secs = _sections(built)
    assert "샘플건설 주식회사" in _text(secs[0])                   # 표지
    assert "샘플건설 주식회사" in _text(secs[1])                   # 쪽 머리 로고 칸 아래 회사명


def test_with_synthetic_logo(tmp_path):
    out = _build(tmp_path, 로고=str(_png(tmp_path / "logo.png")))
    with zipfile.ZipFile(out) as z:
        bins = [n for n in z.namelist() if n.startswith("BinData/")]
        hpf = z.read("Contents/content.hpf").decode("utf-8")
        assert z.namelist()[0] == "mimetype"
    assert bins and all(f'href="{n}"' in hpf for n in bins)     # 로고 그림마다 매니페스트 등록(python-hwpx 누락 보정)
    secs = _sections(out)
    assert "<hp:pic" in secs[0]                                  # 표지
    assert all("<hp:pic" in x for x in secs[1:])                 # 모든 쪽 머리 로고 칸
    if VALIDATE.exists():
        _validate(out)


def test_missing_logo_file_fails_loudly(tmp_path):
    out = tmp_path / "x.hwpx"
    with pytest.raises(FileNotFoundError):
        build_plan(_rows(), _project(로고=str(tmp_path / "none.png")), out, basis_version="합성",
                   revision=1, date="2026. 06. 01.")
    assert not out.exists()


@pytest.mark.skipif(not VALIDATE.exists(), reason="hwpx-validate 없음")
def test_hwpx_validate_passes(built):
    _validate(built)


def test_missing_project_key_fails_loudly(tmp_path):
    p = _project()
    del p["품질관리자"]
    out = tmp_path / "x.hwpx"
    with pytest.raises(PlaceholderError, match="품질관리자"):
        build_plan(_rows(), p, out, basis_version="합성", revision=0, date="2026. 01. 05.")
    assert not out.exists()


def test_example_covers_every_template_placeholder():
    need = placeholders(load_template()) - {"기준", "개정", "일자"}
    assert need <= set(_project())


# ── 정본 모양(docs/design/plan-layout.md) ─────────────────────────────

def _widths(xml, tbl_index):
    """본문(쪽 머리 제외) tbl_index 번째 표의 첫 행 열 폭(mm)."""
    body = re.sub(r"<hp:header.*?</hp:header>|<hp:footer.*?</hp:footer>", "", xml, flags=re.S)
    tbl = re.findall(r"<hp:tbl .*?</hp:tbl>", body, re.S)[tbl_index]
    row = re.search(r"<hp:tr>(.*?)</hp:tr>", tbl, re.S).group(1)
    return [round(int(w) * 25.4 / 7200, 1) for w in re.findall(r'<hp:cellSz width="(\d+)"', row)]


def test_body_starts_at_canonical_line(built):
    m = re.search(r'<hp:margin header="(\d+)" footer="(\d+)" gutter="\d+" left="(\d+)" right="(\d+)" '
                  r'top="(\d+)" bottom="(\d+)"', _sections(built)[1])
    header, footer, left, right, top, bottom = (int(x) * 25.4 / 7200 for x in m.groups())
    assert abs(top + header - 37.5) < 0.05                       # 본문 시작(정본 37.3~37.5)
    assert abs(297 - bottom - footer - 277.8) < 0.05             # 본문 아래 한계(정본 목차 끝 277.6)
    assert abs(left - 16.5) < 0.05 and abs(210 - right - 197.5) < 0.05


def test_toc_is_one_table_without_body_title(built):
    toc = _sections(built)[1]
    body = re.sub(r"<hp:header.*?</hp:header>", "", toc, flags=re.S)
    assert "A. 목차" not in _text(body)                           # 제목은 쪽 머리에만(정본)
    assert _widths(toc, 0) == [14.9, 117.1, 22.5, 26.5]
    assert "4.1 건설공사의 정보" in _text(body)


def test_history_table_columns_and_sign_block(built):
    hist = _sections(built)[2]
    assert _widths(hist, 0) == [15.7, 19.7, 51.9, 74.1, 19.7]    # 정본 15.6:19.6:51.6:73.7:19.6 을 본문폭 181 로
    t = _text(hist)
    assert "비 고" in t and "서     명" in t and "품질관리자 을" in t


def test_section_starts_with_canonical_overview_boxes(built):
    sec = next(x for x in _sections(built)[3:] if "4.2 이해관계자의 요구와 기대관리" in _text(x))   # 목차 다음
    t = _text(re.sub(r"<hp:header.*?</hp:header>", "", sec, flags=re.S))
    labels = ["목 적", "적용범위", "적용기준", "관련문서", "첨부(양식)"]
    assert [t.index(x) for x in labels] == sorted(t.index(x) for x in labels)
    assert "1. 이해관계자 파악" in t and "별표1 4.2" in t
    assert "가. 목적" not in t                                    # 옛 가/나/다 항목 대신 개요 칸
    assert _widths(sec, 0)[0] == 29.3


def test_chapter_unit_header_joins_titles_with_slash(built):
    unit = next(x for x in _sections(built)[3:] if "1. 일반사항" in _text(x))
    assert "1. 일반사항 / 2. 적용범위 및 인용표준 / 3. 용어 정의" in _text(unit)


def test_811_starts_on_new_page_after_boxes(built):
    sec = next(x for x in _sections(built) if "레미콘 25-24-150" in _text(x))
    assert re.search(r'<hp:p [^>]*pageBreak="1"[^>]*><hp:run[^>]*><hp:t>\d\. 품질시험 및 검사계획', sec)
