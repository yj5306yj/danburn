#!/usr/bin/env python3
"""디자인 대조 측정 — 정본 PDF 와 우리 PDF 의 쪽 모양을 수치로 잰다.

사용: design_diff.py <정본.pdf> <우리.pdf> --pages [유형=]정본쪽:우리쪽 ... [--table]
      [--json 출력.json] [--images 폴더] [--dpi 300]

쪽 짝마다 `pdftotext -bbox-layout`(글자 상자)와 `pdftoppm` 래스터(흑백, 계단 보정 끔)로 잰다.
  용지·방향 / 잉크 여백 4변 / 본문 영역(쪽 머리 선과 꼬리 사이의 잉크 상자)
  쪽 머리·꼬리 선(세로선이 닿지 않는 긴 가로선) y·굵기·시작/끝 x
  쪽 머리 글(문서명 줄·절 제목 줄·개정 표기)과 꼬리 글의 위치·크기
  본문 글자 크기·줄 간격·가장 큰 제목 글자 크기, 표 안 글자 크기
  표 세로선 위치 → 열 폭·열 비율, 선 굵기(바깥·안쪽), 행 높이
글자 크기: 한글 낱말의 잉크 높이 ÷ 0.88 (docs/design/8.11-layout.md §9 와 같은 환산).
한글이 없으면 대문자 낱말 잉크 높이 ÷ 0.72.

기준(PLAN 루프 6): 위치·여백 차 ≤ 1.0mm, 글자 크기 차 ≤ 0.5pt, 열 비율 차 ≤ 2%p, 선 굵기 같은 등급.
출력은 수치만 담는다(원문 글은 싣지 않는다). 결과·이미지는 로컬 전용 폴더에 둔다.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageChops
except ImportError as e:  # 개발 전용 도구 — Pillow 는 런타임 의존성이 아니다
    raise ImportError("design_diff 는 Pillow 가 필요합니다(개발 전용): pip install pillow") from e

PT_MM = 25.4 / 72
TOL_MM = 1.0
TOL_PT = 0.5
TOL_RATIO = 2.0
HANGUL = re.compile(r"[가-힣]")
REV = re.compile(r"Rev|^\d+p\.?$|\dp\.$")


# ── 추출 ─────────────────────────────────────────────────────────────


def render(pdf: str, page: int, dpi: int) -> Image.Image:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "p"
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-gray", "-aa", "no", "-aaVector", "no",
             "-f", str(page), "-l", str(page), "-singlefile", pdf, str(out)],
            check=True, capture_output=True)
        return Image.open(f"{out}.pgm").convert("L").copy()


def words_of(pdf: str, page: int) -> tuple[float, float, list[dict]]:
    """(쪽 폭 pt, 쪽 높이 pt, 줄 목록). 줄 = {box, words:[{box, text}]} (pt)."""
    out = subprocess.run(
        ["pdftotext", "-bbox-layout", "-f", str(page), "-l", str(page), pdf, "-"],
        check=True, capture_output=True).stdout.decode("utf-8", "replace")
    m = re.search(r'<page width="([\d.]+)" height="([\d.]+)"', out)
    pw, ph = float(m.group(1)), float(m.group(2))
    num = r'"([\d.]+)"'
    box = rf"xMin={num} yMin={num} xMax={num} yMax={num}"
    lines = []
    for lm in re.finditer(rf"<line {box}>(.*?)</line>", out, re.S):
        ws = [{"box": tuple(float(wm.group(i)) for i in range(1, 5)), "text": html.unescape(wm.group(5))}
              for wm in re.finditer(rf"<word {box}>(.*?)</word>", lm.group(5), re.S)]
        if ws:
            lines.append({"box": tuple(float(lm.group(i)) for i in range(1, 5)), "words": ws})
    return pw, ph, lines


def ink_mask(img: Image.Image) -> Image.Image:
    return img.point(lambda v: 255 if v < 128 else 0)


def segments(mask: Image.Image, min_len: int, max_thick: int) -> list[list[int]]:
    """가로 선분 [y0, y1, x0, x1] (px). 줄마다 긴 잉크 연속을 찾아 이웃 줄과 잇는다."""
    w, h = mask.size
    data = mask.tobytes()
    pat = re.compile(rb"\xff{%d,}" % min_len)
    active: list[list[int]] = []
    done: list[list[int]] = []
    for y in range(h):
        row = data[y * w:(y + 1) * w]
        runs = [(m.start(), m.end() - 1) for m in pat.finditer(row)]
        nxt = []
        for x0, x1 in runs:
            hit = None
            for s in active:
                ov = min(x1, s[3]) - max(x0, s[2])
                if ov >= 0.8 * min(x1 - x0, s[3] - s[2]):
                    hit = s
                    break
            if hit:
                active.remove(hit)
                hit[1], hit[2], hit[3] = y, min(hit[2], x0), max(hit[3], x1)
                nxt.append(hit)
            else:
                nxt.append([y, y, x0, x1])
        done.extend(active)
        active = nxt
    done.extend(active)
    return [s for s in done if s[1] - s[0] + 1 <= max_thick]


def word_size_pt(mask: Image.Image, wbox, sx: float) -> float | None:
    """낱말 상자 안 잉크 높이로 글자 크기(pt) 추정. 한글 0.88em, 대문자 0.72em."""
    text = wbox["text"]
    hangul = len(HANGUL.findall(text))
    if hangul >= 1:
        ratio = 0.88
    elif re.fullmatch(r"[A-Z]{2,}", text):
        ratio = 0.72
    else:
        return None
    x0, y0, x1, y1 = wbox["box"]
    pad = (y1 - y0) * 0.1
    crop = mask.crop((round(x0 * sx) + 1, round((y0 - pad) * sx), round(x1 * sx) - 1, round((y1 + pad) * sx)))
    cw, ch = crop.size
    if cw < 2 or ch < 2:
        return None
    data = crop.tobytes()
    cols_full = {x for x, n in enumerate(_col_counts(crop)) if n > 0.85 * ch}
    rows = []
    for y in range(ch):
        row = data[y * cw:(y + 1) * cw]
        n = row.count(255)
        if n > 0.85 * cw:  # 칸 선
            continue
        n -= sum(1 for x in cols_full if row[x] == 255)
        if n > 0:
            rows.append(y)
    if not rows:
        return None
    ink_pt = (rows[-1] - rows[0] + 1) / sx
    return ink_pt / ratio


def _col_counts(img: Image.Image) -> list[int]:
    t = img.transpose(Image.Transpose.TRANSPOSE)
    w, h = t.size
    d = t.tobytes()
    return [d[y * w:(y + 1) * w].count(255) for y in range(h)]


# ── 한 쪽 측정 ─────────────────────────────────────────────────────


def _r(v, n=2):
    return None if v is None else round(v, n)


def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def grade(mm: float | None) -> str | None:
    if mm is None:
        return None
    return "가는선" if mm < 0.25 else ("중간선" if mm <= 0.45 else "굵은선")


def measure(pdf: str, page: int, dpi: int = 300) -> dict:
    img = render(pdf, page, dpi)
    pw, ph, lines = words_of(pdf, page)
    mask = ink_mask(img)
    W, H = mask.size
    sx = W / pw  # px per pt
    mm = lambda px: px / sx * PT_MM  # noqa: E731
    pmm = lambda pt: pt * PT_MM  # noqa: E731

    m: dict = {"paper": {"w": _r(pmm(pw), 1), "h": _r(pmm(ph), 1), "orient": "세로" if ph >= pw else "가로"}}
    bb = mask.getbbox()
    if bb:
        m["margin"] = {"top": _r(mm(bb[1])), "bottom": _r(mm(H - bb[3])), "left": _r(mm(bb[0])), "right": _r(mm(W - bb[2]))}

    px_mm = sx / PT_MM
    hs = segments(mask, int(10 * px_mm), int(2 * px_mm))  # 가로선 ≥ 10mm
    vt = segments(mask.transpose(Image.Transpose.TRANSPOSE), int(3 * px_mm), int(2 * px_mm))
    vs = [[s[2], s[3], s[0], s[1]] for s in vt]  # 세로선 [y0, y1, x0, x1]

    def touched(s):
        # 표 테두리처럼 6mm 넘는 세로선이 닿으면 쪽 머리·꼬리 선이 아니다(글자 획은 그보다 짧다)
        y0, y1 = s[0] - px_mm, s[1] + px_mm
        return any(v[1] - v[0] >= 6 * px_mm and v[2] >= s[2] - 2 and v[3] <= s[3] + 2 and v[0] <= y1 and v[1] >= y0
                   for v in vs)

    free = [s for s in hs if s[3] - s[2] >= 0.3 * W and not touched(s)]
    head_lines = sorted([s for s in free if s[1] < 0.25 * H], key=lambda s: s[0])
    foot_lines = sorted([s for s in free if s[0] > 0.85 * H], key=lambda s: s[0])

    def line_info(s):
        return {"y": _r(mm((s[0] + s[1]) / 2)), "thick": _r(mm(s[1] - s[0] + 1)), "x0": _r(mm(s[2])), "x1": _r(mm(s[3] + 1))}

    # 모든 낱말에 크기(pt)
    for ln in lines:
        for w in ln["words"]:
            w["size"] = word_size_pt(mask, w, sx)

    # 쪽 머리: 개정 표기(Rev·Np.) 낱말을 닻으로
    rev_words = [w for ln in lines for w in ln["words"] if REV.search(w["text"]) and w["box"][3] < 0.2 * ph]
    head_bottom_pt = None
    if rev_words:
        ry = max(w["box"][3] for w in rev_words)
        below = [s for s in head_lines if s[0] / sx >= ry - 2]
        head_bottom_pt = (below[0][1] / sx) if below else ry
        head_lines = [s for s in head_lines if s[0] / sx <= head_bottom_pt + 1]
    else:
        head_lines = []
    if head_lines:
        m["head_lines"] = [line_info(s) for s in head_lines]

    logo_x = (head_lines[0][2] / sx - 1) if head_lines else None
    if head_bottom_pt is not None:
        hw = [w for ln in lines for w in ln["words"]
              if w["box"][3] <= head_bottom_pt + 1 and (logo_x is None or w["box"][0] >= logo_x)]
        rv = [w for w in hw if _same_row(w, rev_words) and w["box"][0] >= min(r["box"][0] for r in rev_words) - 60]
        rest = [w for w in hw if w not in rv]
        rows = _rows(rest)
        head = {}
        if rv:
            head["rev"] = _text_box(rv, mask, sx)
        if rows:
            head["title"] = _text_box(rows[-1], mask, sx)
        m["head_text"] = head
        # 문서명 줄: 글이 그림일 수도 있어 잉크로 잰다(첫 머리 선 위, 로고 칸 오른쪽)
        if len(head_lines) >= 2:
            hl = head_lines[0]
            box = mask.crop((hl[2], 0, W, hl[0] - 1)).getbbox()
            if box:
                m["head_doc"] = {"x0": _r(mm(box[0] + hl[2])), "y_top": _r(mm(box[1])), "y_bottom": _r(mm(box[3])),
                                 "size": _r((box[3] - box[1]) / sx / 0.88, 1)}

    # 꼬리: 표·선보다 아래, 쪽 아래 12% 안의 글 줄
    content_bottom = max([s[1] for s in hs if s not in foot_lines] + [v[1] for v in vs] + [0]) / sx
    foot_words = [w for ln in lines for w in ln["words"] if w["box"][1] > max(0.88 * ph, content_bottom)]
    if foot_lines:
        m["foot_lines"] = [line_info(s) for s in foot_lines]
    if foot_words:
        fb = _text_box(foot_words, mask, sx)
        m["foot_text"] = {"x_center": _r((fb["x0"] + fb["x1"]) / 2), "y_bottom": fb["y_bottom"], "size": fb["size"]}

    # 본문 영역: 머리 선 아래 ~ 꼬리(선·글) 위
    top_px = int((head_bottom_pt + 1) * sx) if head_bottom_pt is not None else 0
    bot_pt = min([s[0] / sx for s in foot_lines] + [w["box"][1] for w in foot_words] + [ph])
    bot_px = int((bot_pt - 1) * sx)
    body_bb = mask.crop((0, top_px, W, bot_px)).getbbox() if bot_px > top_px else None
    if body_bb:
        m["body"] = {"top": _r(mm(body_bb[1] + top_px)), "bottom": _r(mm(H - (body_bb[3] + top_px))),
                     "left": _r(mm(body_bb[0])), "right": _r(mm(W - body_bb[2]))}

    # 표: 본문 안의 선
    in_body = lambda s: s[0] >= top_px and s[1] <= bot_px  # noqa: E731
    th = [s for s in hs if in_body(s)]
    tv = [v for v in vs if in_body(v) and v[1] - v[0] >= 5 * px_mm]
    tbox = None
    if len(tv) >= 2 and th:
        tbox = (min(v[2] for v in tv), min(s[0] for s in th), max(v[3] for v in tv), max(s[1] for s in th))
        m["table"] = _table(th, tv, tbox, mm)

    # 글자 크기·줄 간격
    def inside(w):
        if tbox is None:
            return False
        x0, y0, x1, y1 = (c * sx for c in w["box"])
        return x0 >= tbox[0] - 2 and x1 <= tbox[2] + 2 and y0 >= tbox[1] - 2 and y1 <= tbox[3] + 2

    body_lines = [ln for ln in lines if ln["box"][1] * sx >= top_px and ln["box"][3] * sx <= bot_px]
    txt = [w for ln in body_lines for w in ln["words"] if not inside(w)]
    tbl = [w for ln in body_lines for w in ln["words"] if inside(w)]
    m["text"] = {
        "body_size": _r(_med(w["size"] for w in txt), 1),
        "table_size": _r(_med(w["size"] for w in tbl), 1),
        "max_size": _r(max((_med(w["size"] for w in ln["words"] if not inside(w)) or 0) for ln in body_lines) or None, 1)
        if body_lines else None,  # 표 밖 글 줄 가운데 가장 큰 것(제목)
        "line_pitch": _r(_pitch([ln for ln in body_lines if not all(inside(w) for w in ln["words"])], pmm)),
        "n_words": len(txt) + len(tbl),
    }
    return m


def _same_row(w, rev):
    return any(abs(w["box"][3] - r["box"][3]) < 2.5 for r in rev)


def _rows(ws):
    rows: list[list[dict]] = []
    for w in sorted(ws, key=lambda w: w["box"][3]):
        if rows and abs(rows[-1][-1]["box"][3] - w["box"][3]) < 2.5:
            rows[-1].append(w)
        else:
            rows.append([w])
    return rows


def _text_box(ws, mask, sx):
    """글 묶음의 잉크 상자(mm). 글꼴마다 다른 글자 상자 여백 대신 실제 잉크로 잰다."""
    x0, y0 = min(w["box"][0] for w in ws), min(w["box"][1] for w in ws)
    x1, y1 = max(w["box"][2] for w in ws), max(w["box"][3] for w in ws)
    crop = mask.crop((round(x0 * sx), round(y0 * sx), round(x1 * sx), round(y1 * sx)))
    cw, ch = crop.size
    data = bytearray(crop.tobytes())
    for y in range(ch):  # 글자 상자에 걸친 선은 지운다
        if data[y * cw:(y + 1) * cw].count(255) > 0.85 * cw:
            data[y * cw:(y + 1) * cw] = bytes(cw)
    bb = Image.frombytes("L", (cw, ch), bytes(data)).getbbox()
    mm = lambda px: px / sx * PT_MM  # noqa: E731
    if not bb:
        bb = (0, 0, cw, ch)
    return {"x0": _r(mm(round(x0 * sx) + bb[0])), "x1": _r(mm(round(x0 * sx) + bb[2])),
            "y_bottom": _r(mm(round(y0 * sx) + bb[3])), "size": _r(_med(w.get("size") for w in ws), 1)}


def _pitch(lines, pmm):
    ls = sorted(lines, key=lambda ln: ln["box"][1])
    ds = []
    for a, b in zip(ls, ls[1:]):
        ha = a["box"][3] - a["box"][1]
        dy = b["box"][1] - a["box"][1]
        ov = min(a["box"][2], b["box"][2]) - max(a["box"][0], b["box"][0])
        if 0.5 * ha < dy < 2.2 * ha and ov > 0:
            ds.append(dy)
    return pmm(statistics.median(ds)) if ds else None


def _cluster(vals, tol):
    """[(위치, 무게)] → 가까운 것끼리 묶은 [(가중 평균 위치, 무게 합)]."""
    out: list[list[float]] = []
    for x, wt in sorted(vals):
        if out and x - out[-1][2] <= tol:
            c = out[-1]
            c[0] += x * wt
            c[1] += wt
            c[2] = x
        else:
            out.append([x * wt, wt, x])
    return [(c[0] / c[1], c[1]) for c in out]


def _table(th, tv, tbox, mm):
    px_mm = 1 / mm(1)
    cl = _cluster([((v[2] + v[3]) / 2, v[1] - v[0]) for v in tv], 0.6 * px_mm)
    top = max(wt for _, wt in cl)
    xs = [x for x, wt in cl if wt >= 0.3 * top]
    widths = [mm(b - a) for a, b in zip(xs, xs[1:])]
    total = sum(widths) or 1
    tw = tbox[2] - tbox[0]
    full = sorted([s for s in th if s[3] - s[2] >= 0.5 * tw], key=lambda s: s[0])
    rows = []  # 열마다 그 열 가운데를 지나는 가로선 사이 거리
    for a, b in zip(xs, xs[1:]):
        mid = (a + b) / 2
        ys = [y for y, _ in _cluster([((s[0] + s[1]) / 2, 1) for s in th if s[2] <= mid <= s[3]], 0.3 * px_mm)]
        rows += [mm(y2 - y1) for y1, y2 in zip(ys, ys[1:]) if mm(y2 - y1) >= 2]
    outer_h = [s for s in th if s in (full[0], full[-1])] if full else []
    edge = [v for v in tv if abs((v[2] + v[3]) / 2 - xs[0]) < px_mm or abs((v[2] + v[3]) / 2 - xs[-1]) < px_mm]
    inner_h = [s for s in full[1:-1]]
    inner_v = [v for v in tv if v not in edge]
    t = lambda ss, a, b: _med(mm(s[b] - s[a] + 1) for s in ss)  # noqa: E731
    outer = _med([t(outer_h, 0, 1), t(edge, 2, 3)])
    inner = _med([t(inner_h, 0, 1), t(inner_v, 2, 3)])
    return {
        "x0": _r(mm(tbox[0])), "x1": _r(mm(tbox[2] + 1)), "y0": _r(mm(tbox[1])), "y1": _r(mm(tbox[3] + 1)),
        "col_widths": [_r(w) for w in widths], "col_ratio": [_r(100 * w / total) for w in widths],
        "row_height_med": _r(_med(rows)), "row_height_min": _r(min(rows) if rows else None),
        "outer_thick": _r(outer), "inner_thick": _r(inner),
    }


# ── 대조 ─────────────────────────────────────────────────────────────


def _flat(m: dict, prefix="") -> dict:
    out = {}
    for k, v in m.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            for i, e in enumerate(v):
                out.update(_flat(e, f"{key}[{i}]."))
        else:
            out[key] = v
    return out


# 내용(글 길이·행 수)에 따라 달라지는 값 — 보고만 하고 판정하지 않는다
REFERENCE = {"head_text.title.x1", "head_text.rev.x0", "table.y1", "table.col_widths", "table.row_height_med",
             "text.n_words"}
OK, FAIL, EXEMPT, NA = "통과", "미달", "예외", "비교불가"


def _kind(key: str) -> str | None:
    last = key.rsplit(".", 1)[-1]
    if key in REFERENCE:
        return None
    if key.startswith("paper."):
        return "paper"
    if last in {"size", "body_size", "table_size", "max_size"}:
        return "pt"
    if last == "col_ratio":
        return "ratio"
    if last in {"thick", "outer_thick", "inner_thick"}:
        return "grade_mm"
    return "mm"


def compare(c: dict, o: dict) -> list[dict]:
    fc, fo = _flat(c), _flat(o)
    notice_only = "foot_text.y_bottom" in fo and "foot_text.y_bottom" not in fc
    checks = []
    for key in list(dict.fromkeys(list(fc) + list(fo))):
        kind = _kind(key)
        if kind is None:
            continue
        a, b = fc.get(key), fo.get(key)
        if a is None and b is None:
            continue
        ck = {"item": key, "canon": a, "ours": b, "diff": None, "tol": None, "status": FAIL, "note": ""}
        checks.append(ck)
        if a is None or b is None:
            ck["note"] = "정본에만 있음" if b is None else "우리에만 있음"
            if key.startswith("foot_") and a is None:
                ck.update(status=EXEMPT, note="우리 고지 줄(8.11 명세 §10, 원본 양식에 없음)")
            elif key.startswith("text."):
                ck.update(status=NA, note=ck["note"] + " — 쪽 내용이 달라 한쪽에 해당 글이 없음")
            continue
        if kind == "paper":
            ok = a == b if isinstance(a, str) else abs(a - b) <= TOL_MM
            ck["diff"] = None if isinstance(a, str) else _r(b - a)
        elif kind in ("mm", "pt"):
            tol = TOL_MM if kind == "mm" else TOL_PT
            d = b - a
            ok = abs(d) <= tol
            ck.update(diff=_r(d), tol=tol)
            if not ok:
                ck["note"] = f"우리가 {abs(d):.2f}{'mm' if kind == 'mm' else 'pt'} {'큼' if d > 0 else '작음'}"
            if not ok and key == "margin.bottom" and notice_only:
                ck.update(status=EXEMPT, note=ck["note"] + " — 우리 고지 줄 때문(본문 아래는 body.bottom 에서 판정)")
                continue
        elif kind == "grade_mm":
            ok = grade(a) == grade(b)
            ck.update(diff=_r(b - a), tol="같은 등급")
            if not ok:
                ck["note"] = f"{grade(a)} → {grade(b)}"
        else:  # ratio
            ck["tol"] = TOL_RATIO
            if len(a) != len(b):
                ok = False
                ck["note"] = f"열 수 다름 (정본 {len(a)}, 우리 {len(b)})"
            else:
                ds = [y - x for x, y in zip(a, b)]
                worst = max(range(len(ds)), key=lambda i: abs(ds[i])) if ds else 0
                ck["diff"] = [_r(d) for d in ds]
                ok = all(abs(d) <= TOL_RATIO for d in ds)
                if not ok:
                    ck["note"] = f"{worst}번 열 {ds[worst]:+.1f}%p (최대)"
        ck["status"] = OK if ok else FAIL
    return checks


# ── 이미지 ───────────────────────────────────────────────────────────


def side_by_side(canon: str, cp: int, ours: str, op: int, out: Path, dpi: int = 100) -> None:
    a, b = render(canon, cp, dpi).convert("RGB"), render(ours, op, dpi).convert("RGB")
    h = max(a.height, b.height)
    # 겹침: 정본만 빨강, 우리만 파랑, 겹친 곳 검정
    ma = ink_mask(a.convert("L"))
    mb = ink_mask(b.convert("L").resize(a.size))
    ov = Image.merge("RGB", (ImageChops.invert(mb), ImageChops.invert(ImageChops.lighter(ma, mb)), ImageChops.invert(ma)))
    wide = Image.new("RGB", (a.width + b.width + a.width + 24, h), (200, 60, 60))
    wide.paste(a, (0, 0))
    wide.paste(b, (a.width + 12, 0))
    wide.paste(ov, (a.width + b.width + 24, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    wide.save(out)


# ── 실행 ─────────────────────────────────────────────────────────────


def parse_pair(s: str) -> tuple[str, int, int]:
    kind, _, rest = s.rpartition("=")
    c, o = rest.split(":")
    return (kind or f"p{c}-{o}", int(c), int(o))


def table_text(result: dict) -> str:
    out = []
    for p in result["pairs"]:
        cnt = p["count"]
        out.append(f"\n## {p['type']} (정본 {p['canon_page']}쪽 : 우리 {p['ours_page']}쪽) — "
                   + " · ".join(f"{k} {v}" for k, v in cnt.items()))
        out.append("| 항목 | 정본 | 우리 | 차 | 기준 | 판정 | 비고 |")
        out.append("|---|---|---|---|---|---|---|")
        for c in p["checks"]:
            fmt = lambda v: "-" if v is None else (" ".join(str(x) for x in v) if isinstance(v, list) else str(v))  # noqa: E731
            out.append(f"| {c['item']} | {fmt(c['canon'])} | {fmt(c['ours'])} | {fmt(c['diff'])} | {fmt(c['tol'])} | "
                       f"{c['status']} | {c['note']} |")
    return "\n".join(out)


def run(canon: str, ours: str, pairs: list[tuple[str, int, int]], dpi: int = 300, images: Path | None = None) -> dict:
    res = {"canon": Path(canon).name, "ours": Path(ours).name, "dpi": dpi,
           "criteria": {"mm": TOL_MM, "pt": TOL_PT, "ratio_pp": TOL_RATIO, "line": "같은 등급(<0.25 가는선, ≤0.45 중간선, 그 위 굵은선)"},
           "pairs": []}
    for i, (kind, cp, op) in enumerate(pairs):
        mc, mo = measure(canon, cp, dpi), measure(ours, op, dpi)
        checks = compare(mc, mo)
        count = {st: sum(c["status"] == st for c in checks) for st in (OK, FAIL, EXEMPT, NA)}
        pair = {"type": kind, "canon_page": cp, "ours_page": op, "count": count, "canon": mc, "ours": mo, "checks": checks}
        if images:
            img = images / f"{i:02d}-{kind}-c{cp}-o{op}.png"
            side_by_side(canon, cp, ours, op, img)
            pair["image"] = str(img)
        res["pairs"].append(pair)
    res["summary"] = {p["type"]: p["count"] for p in res["pairs"]}
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("canon")
    ap.add_argument("ours")
    ap.add_argument("--pages", nargs="+", required=True, help="[유형=]정본쪽:우리쪽")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--images", type=Path)
    ap.add_argument("--table", action="store_true")
    a = ap.parse_args(argv)
    res = run(a.canon, a.ours, [parse_pair(s) for s in a.pages], a.dpi, a.images)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.table:
        print(table_text(res))
    else:
        print(json.dumps(res["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
