"""품질시험계획서 한글 단독본(L14-E) — 합성 행만 쓴다. 열리는 hwpx·4부 제목·(스캔첨부)·가로 8.11 표."""
import re
import zipfile

import pytest
from hwpx import HwpxDocument

from danburn.model import PlanRow
from danburn.testplan import PARTS, SCAN, STAFF_PROOFS, build_testplan
from conftest import VALIDATE, run_hwpx_validate

DATE = "2026. 01. 05."


def _rows():
    rows = [PlanRow("건축", "철근콘크리트공사", "레미콘(25-24-150)", t, 480, "㎥", "120㎥마다", "480㎥/120㎥", 4,
                    material="ready_mixed_concrete") for t in ("슬럼프", "공기량")]
    rows[0].method = "KS F 2402"
    rows.append(PlanRow("토목", "토공사", "합성 성토재", "다짐", 3000, "㎥", "합성 빈도", "합성 근거", 2, material="x"))
    return rows


def _project():
    return {"공사명": "가상 합성 공동주택 신축공사", "회사명": "합성건설", "제정일자": DATE,
            "개정이력": [{"개정": 0, "일자": DATE, "장": ["전체"], "사유": "최초 제정"}],
            "조직": [{"직무": "현장대리인", "성명": "합성 갑", "상위": ""},
                   {"직무": "품질관리자", "성명": "합성 을", "상위": "현장대리인"}],
            "품질관리자": [{"직무": "품질관리자", "성명": "합성 을", "등급": "고급", "배치기간": "착공~준공"}],
            "시험장비": [{"시험기구": "합성 시험기", "규격": "합성", "단위": "대", "수량": "1"}]}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("tp") / "품질시험계획서.hwpx"
    return build_testplan(_rows(), _project(), out, basis_version="합성 기준판", revision=0, date=DATE)


def _xml(path):
    with zipfile.ZipFile(path) as z:
        return "".join(z.read(n).decode("utf-8") for n in sorted(z.namelist()) if re.match(r"Contents/section\d+\.xml", n))


def _text(path):
    return "".join(re.findall(r"<hp:t>([^<]*)</hp:t>", _xml(path)))


def test_opens_and_has_four_parts(built):
    doc = HwpxDocument.open(str(built))
    assert len(doc.sections) >= 6                                     # 표지·목차·1·2·3·4
    t = _text(built)
    assert "품질시험계획서" in t and "Quality Test Plan" in t and "Quality Management Plan" not in t
    for no, title, subs in PARTS:
        assert f"{no}. {title}" in t
        for s in subs:
            assert s in t


def test_scan_placeholders(built):
    t = _text(built)
    assert f"{SCAN} 시험실 배치평면도" in t
    for proof in STAFF_PROOFS:
        assert f"{SCAN} {proof}" in t


def test_plan_table_is_landscape_with_method_column(built):
    x = _xml(built)
    assert 'landscape="NARROWLY"' in x                                  # 2부(시험계획표)는 가로
    assert re.search(r'<hp:tbl [^>]*repeatHeader="1"[^>]*colCnt="12"', x)
    t = _text(built)
    assert "시험방법" in t and "KS F 2402" in t and "계획시험횟수" in t and "[토목공사]" in t
    assert "합성 을" in t and "합성 시험기" in t                            # 배치계획·장비 표는 project 에서


@pytest.mark.skipif(VALIDATE is None, reason="hwpx-validate 없음")
def test_schema_valid(built):
    run_hwpx_validate(built)


def test_revision_mismatch_raises(tmp_path):
    with pytest.raises(ValueError):
        build_testplan(_rows(), _project(), tmp_path / "x.hwpx", revision=0, date="2026. 02. 01.")
    assert not (tmp_path / "x.hwpx").exists()


def test_minimal_project(tmp_path):
    out = build_testplan(_rows(), {}, tmp_path / "m.hwpx", date=DATE)
    assert "(작성 필요)" in _text(out)
