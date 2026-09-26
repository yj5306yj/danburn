"""scripts/dev/design_diff.py — 합성 PDF 로 측정·대조를 확인한다(실자료 없음)."""
from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (shutil.which("pdftoppm") and shutil.which("pdftotext")),
                                reason="poppler(pdftoppm·pdftotext) 없음")

spec = importlib.util.spec_from_file_location("design_diff", ROOT / "scripts/dev/design_diff.py")
dd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dd)

PW, PH = 595.28, 841.89
MM = 72 / 25.4


def _pdf(path: Path, ops: list[str]) -> Path:
    """Helvetica 한 글꼴·한 쪽짜리 최소 PDF. ops 는 PDF 내용 연산(pt, 원점 왼쪽 아래)."""
    stream = "\n".join(ops).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PW} {PH}] /Contents 4 0 R "
        f"/Resources << /Font << /F1 5 0 R >> >> >>".encode(),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(bytes(out))
    return path


def _hline(x0, x1, y, w):  # mm, 위에서 잰 y
    return f"{w * MM:.3f} w {x0 * MM:.2f} {PH - y * MM:.2f} m {x1 * MM:.2f} {PH - y * MM:.2f} l S"


def _vline(x, y0, y1, w):
    return f"{w * MM:.3f} w {x * MM:.2f} {PH - y0 * MM:.2f} m {x * MM:.2f} {PH - y1 * MM:.2f} l S"


def _text(x, y_base, size, s):
    return f"BT /F1 {size} Tf {x * MM:.2f} {PH - y_base * MM:.2f} Td ({s}) Tj ET"


def _page(tmp: Path, name: str, head_y=(23.45, 31.45), cols=(16, 40, 100, 150, 197), body_pt=10) -> Path:
    ops = [_text(36, 21.5, 15, "DOCNAME"), _text(36, 30.0, 13, "TITLE"), _text(170, 30.0, 9, "2026.01.05. Rev.0 1p.")]
    ops += [_hline(33.6, 197, y, 0.4) for y in head_y]
    top, bot = 40, 100
    ops += [_hline(cols[0], cols[-1], top, 0.4), _hline(cols[0], cols[-1], bot, 0.4)]
    ops += [_hline(cols[0], cols[-1], y, 0.2) for y in (50, 60, 70, 80, 90)]
    ops += [_vline(cols[0], top, bot, 0.4), _vline(cols[-1], top, bot, 0.4)]
    ops += [_vline(x, top, bot, 0.2) for x in cols[1:-1]]
    ops += [_text(20, 120, body_pt, "BODY TEXT LINE"), _text(20, 126, body_pt, "BODY TEXT AGAIN"),
            _text(80, 288, 7, "NOTICE")]
    return _pdf(tmp / name, ops)


def test_measure_reads_synthetic_layout(tmp_path):
    m = dd.measure(str(_page(tmp_path, "a.pdf")), 1)
    assert m["paper"] == {"w": 210.0, "h": 297.0, "orient": "세로"}
    ys = [ln["y"] for ln in m["head_lines"]]
    assert ys == pytest.approx([23.45, 31.45], abs=0.2)
    assert all(dd.grade(ln["thick"]) == "중간선" for ln in m["head_lines"])
    assert m["head_lines"][0]["x0"] == pytest.approx(33.6, abs=0.3)
    t = m["table"]
    assert t["col_ratio"] == pytest.approx([100 * w / 181 for w in (24, 60, 50, 47)], abs=0.3)
    assert dd.grade(t["outer_thick"]) == "중간선" and dd.grade(t["inner_thick"]) == "가는선"
    assert t["row_height_min"] == pytest.approx(10, abs=0.3)
    assert t["y0"] == pytest.approx(40, abs=0.4)
    assert m["text"]["body_size"] == pytest.approx(10, abs=0.6)
    assert m["text"]["line_pitch"] == pytest.approx(6, abs=0.3)
    assert m["head_text"]["title"]["size"] == pytest.approx(13, abs=0.8)
    assert m["head_text"]["title"]["x0"] == pytest.approx(36, abs=0.8)
    assert m["head_doc"]["size"] == pytest.approx(15 * 0.72 / 0.88, abs=0.8)  # 대문자 잉크 ÷ 0.88
    assert m["foot_text"]["size"] == pytest.approx(7, abs=0.6)


def test_same_layout_passes(tmp_path):
    a = dd.measure(str(_page(tmp_path, "a.pdf")), 1)
    b = dd.measure(str(_page(tmp_path, "b.pdf")), 1)
    checks = dd.compare(a, b)
    assert checks and all(c["status"] == dd.OK for c in checks), [c for c in checks if c["status"] != dd.OK]


def test_shifted_layout_fails_with_cause(tmp_path):
    a = dd.measure(str(_page(tmp_path, "a.pdf")), 1)
    b = dd.measure(str(_page(tmp_path, "b.pdf", head_y=(23.45, 33.45), cols=(16, 40, 110, 150, 197), body_pt=12)), 1)
    got = {c["item"]: c for c in dd.compare(a, b)}
    assert got["head_lines[1].y"]["status"] == dd.FAIL
    assert got["head_lines[1].y"]["diff"] == pytest.approx(2.0, abs=0.2)
    assert got["head_lines[0].y"]["status"] == dd.OK
    assert got["table.col_ratio"]["status"] == dd.FAIL and "%p" in got["table.col_ratio"]["note"]
    assert got["text.body_size"]["status"] == dd.FAIL


def test_missing_items_and_notice_exception():
    c = {"margin": {"bottom": 20.0}, "text": {"body_size": 10.0}, "table": {"x0": 16.0}}
    o = {"margin": {"bottom": 10.0}, "foot_text": {"y_bottom": 287.0}, "table": {}}
    got = {k["item"]: k for k in dd.compare(c, o)}
    assert got["margin.bottom"]["status"] == dd.EXEMPT
    assert got["foot_text.y_bottom"]["status"] == dd.EXEMPT
    assert got["text.body_size"]["status"] == dd.NA
    assert got["table.x0"]["status"] == dd.FAIL and got["table.x0"]["note"] == "정본에만 있음"


def test_cli_writes_json_table_and_images(tmp_path, capsys):
    a, b = _page(tmp_path, "a.pdf"), _page(tmp_path, "b.pdf")
    out = tmp_path / "r.json"
    assert dd.main([str(a), str(b), "--pages", "본문=1:1", "1:1", "--json", str(out),
                    "--images", str(tmp_path / "img"), "--table", "--dpi", "150"]) == 0
    res = json.loads(out.read_text(encoding="utf-8"))
    assert [p["type"] for p in res["pairs"]] == ["본문", "p1-1"]
    assert Path(res["pairs"][0]["image"]).exists()
    assert "| 항목 | 정본 | 우리 |" in capsys.readouterr().out


def test_parse_pair():
    assert dd.parse_pair("표지=1:3") == ("표지", 1, 3)
    assert dd.parse_pair("2:5") == ("p2-5", 2, 5)
