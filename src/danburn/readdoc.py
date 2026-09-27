"""Read HWP, HWPX, and PDF documents without sending their contents anywhere."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib


@dataclass
class DocText:
    """Text extracted from a supported document."""

    format: str
    text: str
    parts: list[str]
    warnings: list[str]


class UnreadableDocument(Exception):
    """The file is unsupported, damaged, encrypted, or has no readable text."""


_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_PDF_SIGNATURE = b"%PDF-"
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_HWP_SIGNATURE = b"HWP Document File"
_HWP_COMPRESSED = 0x01
_HWP_PASSWORD = 0x02
_HWP_DISTRIBUTION = 0x04
_PARA_TEXT_TAG = 67
_CONTROL_WITH_ARGUMENT = set(range(1, 10)) | {11, 12} | set(range(14, 24))
_SECTION_RE = re.compile(r"^Contents/section(\d+)\.xml$")


def read_document(path: str | Path) -> DocText:
    """Read a document based on its file signature, not merely its suffix."""

    document = Path(path)
    try:
        signature = document.read_bytes()[:8]
    except OSError as exc:
        raise UnreadableDocument(f"문서를 읽을 수 없습니다: {exc}") from exc
    if signature.startswith(_PDF_SIGNATURE):
        return _read_pdf(document)
    if signature.startswith(_OLE_SIGNATURE):
        return _read_hwp(document)
    if signature.startswith(_ZIP_SIGNATURES):
        return _read_hwpx(document)
    raise UnreadableDocument("지원하지 않거나 손상된 문서 형식입니다")


def _read_hwpx(path: Path) -> DocText:
    try:
        with zipfile.ZipFile(path) as archive:
            names = sorted(
                (name for name in archive.namelist() if _SECTION_RE.match(name)),
                key=lambda name: int(_SECTION_RE.match(name).group(1)),  # type: ignore[union-attr]
            )
            if not names:
                raise UnreadableDocument("HWPX에 본문 구역이 없습니다")
            parts = [_hwpx_section_text(archive.read(name)) for name in names]
    except UnreadableDocument:
        raise
    except (OSError, KeyError, UnicodeError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise UnreadableDocument("HWPX 본문을 읽을 수 없습니다") from exc

    warnings: list[str] = []
    if not any(part.strip() for part in parts):
        warnings.append("본문에서 글자를 찾지 못했습니다")
    return DocText("hwpx", "\n".join(parts), parts, warnings)


def _hwpx_section_text(xml_bytes: bytes) -> str:
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for element in root.iter():
        if _local_name(element.tag) != "p":
            continue
        # A table can be wrapped by an outer paragraph.  Its cell paragraphs
        # are visited separately; collecting their descendants here would
        # duplicate every cell and glue all cells into the wrapper paragraph.
        if any(
            descendant is not element and _local_name(descendant.tag) == "p"
            for descendant in element.iter()
        ):
            continue
        chunks: list[str] = []
        for descendant in element.iter():
            local = _local_name(descendant.tag)
            if local == "t" and descendant.text:
                chunks.append(descendant.text)
            elif local in {"lineBreak", "br"}:
                chunks.append("\n")
        paragraphs.append("".join(chunks))
    if paragraphs:
        return "\n".join(paragraphs)
    return "\n".join(element.text or "" for element in root.iter() if _local_name(element.tag) == "t")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_hwp(path: Path) -> DocText:
    try:
        import olefile
    except ImportError as exc:  # pragma: no cover - packaging error, not a document case
        raise UnreadableDocument("HWP를 읽으려면 olefile 의존성이 필요합니다") from exc

    try:
        with olefile.OleFileIO(path) as ole:
            if not ole.exists("FileHeader"):
                raise UnreadableDocument("HWP FileHeader가 없습니다")
            header = ole.openstream("FileHeader").read()
            _check_hwp_header(header)
            section_names = sorted(
                (name for name in ole.listdir(streams=True, storages=False) if len(name) == 2 and name[0] == "BodyText" and name[1].startswith("Section")),
                key=lambda name: int(name[1][len("Section") :]),
            )
            if not section_names:
                raise UnreadableDocument("HWP 본문 구역이 없습니다")
            compressed = bool(struct.unpack_from("<I", header, 36)[0] & _HWP_COMPRESSED)
            parts = []
            for name in section_names:
                data = ole.openstream(name).read()
                if compressed:
                    data = _decompress_hwp_section(data)
                parts.append("\n".join(_para_texts(data)))
    except UnreadableDocument:
        raise
    except Exception as exc:
        raise UnreadableDocument("HWP 본문을 읽을 수 없습니다") from exc

    warnings: list[str] = []
    if not any(part.strip() for part in parts):
        warnings.append("본문에서 글자를 찾지 못했습니다")
    return DocText("hwp", "\n".join(parts), parts, warnings)


def _decompress_hwp_section(data: bytes) -> bytes:
    try:
        return zlib.decompress(data, -15)
    except zlib.error as exc:
        raise UnreadableDocument("HWP 본문 압축을 풀 수 없습니다") from exc


def _check_hwp_header(header: bytes) -> None:
    if not header.startswith(_HWP_SIGNATURE):
        raise UnreadableDocument("HWP 파일 서명이 아닙니다")
    if len(header) < 40:
        raise UnreadableDocument("HWP FileHeader가 짧습니다")
    properties = struct.unpack_from("<I", header, 36)[0]
    if properties & (_HWP_PASSWORD | _HWP_DISTRIBUTION):
        raise UnreadableDocument("배포용/암호 문서는 읽을 수 없습니다 — 한글에서 PDF로 저장해 주세요")


def _para_texts(section_bytes: bytes) -> list[str]:
    """Return paragraph text records from one HWP BodyText/Section stream."""

    paragraphs: list[str] = []
    offset = 0
    length = len(section_bytes)
    while offset < length:
        if length - offset < 4:
            raise ValueError("HWP 레코드 머리가 잘렸습니다")
        header = struct.unpack_from("<I", section_bytes, offset)[0]
        offset += 4
        tag = header & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if length - offset < 4:
                raise ValueError("HWP 긴 레코드 길이가 잘렸습니다")
            size = struct.unpack_from("<I", section_bytes, offset)[0]
            offset += 4
        if size > length - offset:
            raise ValueError("HWP 레코드 본문이 잘렸습니다")
        payload = section_bytes[offset : offset + size]
        offset += size
        if tag == _PARA_TEXT_TAG:
            paragraphs.append(_decode_para_text(payload))
    return paragraphs


def _decode_para_text(payload: bytes) -> str:
    if len(payload) % 2:
        payload = payload[:-1]
    code_units = struct.unpack("<{}H".format(len(payload) // 2), payload)
    result: list[str] = []
    index = 0
    while index < len(code_units):
        code = code_units[index]
        if code in _CONTROL_WITH_ARGUMENT:
            index += 8
        elif code in (10, 13):
            result.append("\n")
            index += 1
        elif code < 32:
            index += 1
        else:
            result.append(chr(code))
            index += 1
    return "".join(result)


def _read_pdf(path: Path) -> DocText:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - packaging error, not a document case
        raise UnreadableDocument("PDF를 읽으려면 pypdf 의존성이 필요합니다") from exc

    try:
        reader = PdfReader(str(path))
        parts = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # pypdf has changed its concrete error classes across releases
        raise UnreadableDocument("PDF 본문을 읽을 수 없습니다") from exc
    if not any(part.strip() for part in parts):
        raise UnreadableDocument(
            "스캔 PDF(글자 없는 그림)는 읽을 수 없습니다 — 원본 한글 파일(hwp·hwpx)이나 한글에서 저장한 PDF 로 검사하세요"
        )
    warnings: list[str] = []
    if any(not part.strip() for part in parts):
        warnings.append("글자가 없는 쪽이 있습니다")
    return DocText("pdf", "\n".join(parts), parts, warnings)
