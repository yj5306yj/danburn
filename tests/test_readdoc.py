from __future__ import annotations

from pathlib import Path
import struct
import zlib
import zipfile

import pytest

from danburn.readdoc import (
    DocText,
    UnreadableDocument,
    _check_hwp_header,
    _decompress_hwp_section,
    _para_texts,
    read_document,
)


def _record(tag: int, payload: bytes) -> bytes:
    if len(payload) < 0xFFF:
        return struct.pack("<I", tag | (len(payload) << 20)) + payload
    return struct.pack("<I", tag | (0xFFF << 20)) + struct.pack("<I", len(payload)) + payload


def _utf16(text: str) -> bytes:
    return text.encode("utf-16le")


def _write_hwpx(path: Path, *paragraphs: str) -> None:
    xml = (
        '<hs:sec xmlns:hs="urn:section" xmlns:hp="urn:paragraph">'
        + "".join(f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>' for text in paragraphs)
        + '<hp:tbl><hp:tr><hp:tc><hp:p><hp:t>표 칸</hp:t></hp:p></hp:tc></hp:tr></hp:tbl>'
        + "</hs:sec>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", xml)


def _write_wrapped_2x2_table(path: Path) -> None:
    xml = (
        '<hs:sec xmlns:hs="urn:section" xmlns:hp="urn:paragraph">'
        '<hp:p><hp:run><hp:tbl><hp:tr>'
        '<hp:tc><hp:p><hp:run><hp:t>2025. 03. 02.</hp:t></hp:run></hp:p></hp:tc>'
        '<hp:tc><hp:p><hp:run><hp:t>15</hp:t></hp:run></hp:p></hp:tc>'
        '</hp:tr><hp:tr>'
        '<hp:tc><hp:p><hp:run><hp:t>슬럼프</hp:t></hp:run></hp:p></hp:tc>'
        '<hp:tc><hp:p><hp:run><hp:t>4</hp:t></hp:run></hp:p></hp:tc>'
        '</hp:tr></hp:tbl></hp:run></hp:p>'
        '</hs:sec>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", xml)


def _pdf_with_text(text: str) -> bytes:
    content = f"BT /F1 12 Tf 36 760 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def test_hwpx_reads_paragraphs_and_table_cells(tmp_path: Path):
    path = tmp_path / "synthetic.hwpx"
    _write_hwpx(path, "첫 문장", "두 문장")

    result = read_document(path)

    assert isinstance(result, DocText)
    assert result.format == "hwpx"
    assert result.parts == ["첫 문장\n두 문장\n표 칸"]
    assert "표 칸" in result.text
    assert result.warnings == []


def test_hwpx_wrapped_table_cells_are_not_duplicated_or_glued(tmp_path: Path):
    path = tmp_path / "wrapped-table.hwpx"
    _write_wrapped_2x2_table(path)

    result = read_document(path)

    assert result.text == "2025. 03. 02.\n15\n슬럼프\n4"
    assert result.text.count("2025. 03. 02.") == 1
    assert result.text.count("15") == 1
    assert result.text.count("슬럼프") == 1
    assert "2025. 03. 02.15" not in result.text


@pytest.mark.parametrize("compressed", [False, True])
def test_hwp_record_parser_reads_compressed_fixture_and_controls(compressed: bool):
    control = bytes(struct.pack("<H", 1) + b"\0" * 14)
    payload = _utf16("앞") + control + _utf16("뒤\n끝")
    record = _record(67, payload) + _record(67, _utf16("긴 레코드"))
    if compressed:
        record = _decompress_hwp_section(zlib.compress(record, level=9, wbits=-15))

    assert _para_texts(record) == ["앞뒤\n끝", "긴 레코드"]


def test_hwp_record_parser_supports_extended_length_record():
    payload = _utf16("가" * 2048)
    assert _para_texts(_record(67, payload)) == ["가" * 2048]


def test_pdf_reads_page_text(tmp_path: Path):
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(_pdf_with_text("KCS 14 20 10 : 2024"))

    result = read_document(path)

    assert result.format == "pdf"
    assert "KCS 14 20 10" in result.text
    assert result.parts and result.warnings == []


def test_blank_pdf_is_unreadable(tmp_path: Path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(_pdf_with_text(""))

    with pytest.raises(UnreadableDocument, match=r"스캔 PDF\(글자 없는 그림\)는 읽을 수 없습니다"):
        read_document(path)


def test_bad_signature_is_unreadable(tmp_path: Path):
    path = tmp_path / "not-a-document.hwpx"
    path.write_bytes(b"not a document")

    with pytest.raises(UnreadableDocument):
        read_document(path)


@pytest.mark.parametrize("flag", [0x02, 0x04])
def test_hwp_password_or_distribution_header_is_unreadable(flag: int):
    header = bytearray(256)
    header[: len(b"HWP Document File")] = b"HWP Document File"
    struct.pack_into("<I", header, 36, flag)

    with pytest.raises(UnreadableDocument, match="배포용/암호"):
        _check_hwp_header(bytes(header))


def test_ole_signature_with_invalid_container_is_unreadable(tmp_path: Path):
    path = tmp_path / "broken.hwp"
    path.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"not an ole file")

    with pytest.raises(UnreadableDocument):
        read_document(path)
