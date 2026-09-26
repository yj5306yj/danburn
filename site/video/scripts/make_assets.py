#!/usr/bin/env python3
"""히어로 영상 재료를 합성 예제에서 만든다(실제 현장 자료를 쓰지 않는다).

흐름: scripts/make_example_boq.py → danburn plan --offline → rhwp export-pdf → pdftoppm 쪽 PNG
산출: site/video/public/pages/*.png, site/video/public/data.json
  data.json = {pages: 전체 쪽 수, shots: {cover, flow, table: 파일명}, stack: [파일명…],
               boq: [{name, spec, unit, qty, material}], table_rows: [{item, test, qty, unit, count}]}

사용(저장소 루트에서): .venv/bin/python site/video/scripts/make_assets.py
필요: .venv(danburn), .tools/rhwp/rhwp, pdftoppm·pdftotext·pdfinfo(poppler)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = Path(__file__).resolve().parents[1] / "public"
PY = ROOT / ".venv" / "bin" / "python"
QCPLAN = ROOT / ".venv" / "bin" / "danburn"   # 이름 변경(qcplan → danburn)
RHWP = ROOT / ".tools" / "rhwp" / "rhwp"
BOQ = ROOT / "examples" / "out" / "example_boq.xlsx"
PROJECT = ROOT / "data" / "templates" / "project.example.yaml"
BLOCK = "나동"
DPI = 110
ZOOM_DPI = 220     # v1: 8.11 쪽을 2배 확대해도 줄 글씨가 읽히게


def run(*cmd: str | Path) -> str:
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True).stdout


def page_text(pdf: Path, n: int) -> str:
    return re.sub(r"\s", "", run("pdftotext", "-f", n, "-l", n, pdf, "-"))


COMPARE_SPEC = "25-24-150"   # v2 대조 장면: 나동에 두 행(상부·지하주차장)으로 나뉘어 합산되는 레미콘 규격
SHEET_SCOPE = "철근콘크리트공사"   # 판에 보일 범위: 나동 건축 이 공종의 실제 행 전부(8.11 첫 쪽에 모두 나옴)
CROP_DPI = 250


def words(pdf: Path, n: int) -> list[tuple[str, float, float, float, float]]:
    xml = run("pdftotext", "-bbox", "-f", n, "-l", n, pdf, "-")
    return [(m.group(5), *map(float, m.group(1, 2, 3, 4))) for m in re.finditer(
        r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)<', xml)]


def crop_block(pdf: Path, n: int, spec: str, dst: Path, narrow: bool = False, part: str = "") -> dict:
    """8.11 쪽에서 '콘크리트(spec)' 묶음(압축강도~단위수량 6줄)을 표 폭으로 잘라 PNG 로. 쪽 좌표(pt)도 돌려준다."""
    w = words(pdf, n)
    label = next(t for t in w if t[0] == f"({spec})")
    top = max(t[2] for t in w if t[0] == "압축강도" and t[2] < label[2])
    bot = min(t[4] for t in w if t[0] == "단위수량" and t[4] > label[4])
    x0 = min(t[1] for t in w if t[0] == "공종") - 3
    x1 = max(t[3] for t in w if t[0] == "비고") + 3
    if narrow:  # 콘크리트 라벨 칸 왼쪽 ~ 계획횟수 '현장' 칸 오른쪽(첫 횟수 숫자 오른쪽 끝 + 여백)
        x0 = label[1] - 6
        x1 = max(t[3] for t in w if t[0] in ("36", "25") and top <= t[2] <= bot) + 14
    if part:  # 좁은 화면용: 빈도 칸(첫 '360'·'120' 숫자) 왼쪽에서 둘로 나눈다
        split = min(t[1] for t in w if t[0] in ("360㎥", "120㎥", "360", "120") and top <= t[2] <= bot) - 4
        x0, x1 = (x0, split) if part == "a" else (split, x1)
    y0, y1 = top - 4, bot + 4
    k = CROP_DPI / 72
    run("pdftoppm", "-r", CROP_DPI, "-png", "-singlefile", "-f", n, "-l", n, "-x", int(x0 * k), "-y", int(y0 * k),
        "-W", int((x1 - x0) * k), "-H", int((y1 - y0) * k), pdf, dst.with_suffix(""))
    qty = next(t for t in w if t[0] == "2,950" and top <= t[2] <= bot)   # 강조할 수량 칸(자르기 안 비율, b 조각에선 무의미)
    hl = {"x": (qty[1] - 8 - x0) / (x1 - x0), "y": (qty[2] - 6 - y0) / (y1 - y0),
          "w": (qty[3] - qty[1] + 16) / (x1 - x0), "h": (qty[4] - qty[2] + 12) / (y1 - y0)}
    return {"file": f"pages/{dst.name}", "x0": x0, "y0": y0, "x1": x1, "y1": y1, "hl": hl}


def main() -> int:
    run(PY, ROOT / "scripts" / "make_example_boq.py", "--out", BOQ)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        hwpx = tmp / "계획서.hwpx"
        run(QCPLAN, "plan", "--boq", BOQ, "--block", BLOCK, "--project", PROJECT, "--revision", "0",
            "--date", "2026. 01. 05.", "--offline", "--out", hwpx)
        pdf = tmp / "계획서.pdf"
        run(RHWP, "export-pdf", hwpx, "-o", pdf)
        pages = int(re.search(r"Pages:\s+(\d+)", run("pdfinfo", pdf)).group(1))

        texts = {n: page_text(pdf, n) for n in range(1, pages + 1)}
        flow = next(n for n, t in texts.items() if "업무단계" in t)
        table = next(n for n, t in texts.items() if "품질시험및검사계획" in t)
        # 쌓을 쪽: 표지 → 목차 → 흐름표 → 양식 한 장 → 8.11 표(맨 위)
        form = next(n for n, t in texts.items() if "[양식" in t)
        stack = [1, 2, flow, form, table]

        out = PUBLIC / "pages"
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        names = {}
        for n in sorted(set(stack)):
            dpi = ZOOM_DPI if n == table else DPI      # 8.11 쪽은 확대 장면용으로 더 촘촘히
            run("pdftoppm", "-r", dpi, "-png", "-singlefile", "-f", n, "-l", n, pdf, out / f"p{n:03d}")
            names[n] = f"pages/p{n:03d}.png"
        rows = json.loads((tmp / "계획서.json").read_text(encoding="utf-8"))
        forms = len(set(re.findall(r"\[양식(\d+)\]", "".join(texts.values()))))
        crop = crop_block(pdf, table, COMPARE_SPEC, out / "crop-811.png")
        crop_narrow = crop_block(pdf, table, COMPARE_SPEC, out / "crop-811-narrow.png", narrow=True)
        crop_a = crop_block(pdf, table, COMPARE_SPEC, out / "crop-811-a.png", narrow=True, part="a")   # 4:5: 품목~수량·단위
        crop_b = crop_block(pdf, table, COMPARE_SPEC, out / "crop-811-b.png", narrow=True, part="b")   # 4:5: 빈도~횟수

    sys.path.insert(0, str(ROOT / "src"))
    from danburn.boq import read_boq
    from danburn.calc import match_rule
    from danburn.rules import load_rules
    rules = load_rules(ROOT / "data" / "rules")
    boq, seen = [], set()
    for ln in read_boq(BOQ):
        if ln.block and BLOCK not in ln.block:
            continue
        key = (ln.name, ln.spec)
        if key in seen:
            continue
        seen.add(key)
        rule = match_rule(ln, rules)
        boq.append({"name": ln.name, "spec": ln.spec, "unit": ln.unit, "qty": ln.qty,
                    "material": rule.label if rule else ""})

    sheet = []
    for ln in read_boq(BOQ):
        if ln.discipline != "건축" or BLOCK not in (ln.block or "") or SHEET_SCOPE not in (ln.section or ""):
            continue
        rule = match_rule(ln, rules)
        parts = (ln.section or "").split(" > ")
        sheet.append({"sheet": ln.sheet, "row": ln.row, "part": parts[-2] if len(parts) > 1 else "",
                      "name": ln.name.strip(), "spec": ln.spec.strip(), "unit": ln.unit, "qty": ln.qty,
                      "material": rule.label if rule else "", "spec_label": ""})
    src = [r for r in sheet if r["name"] == "레미콘" and r["spec"] == COMPARE_SPEC]
    tests = [r for r in rows if r["material"] == "ready_mixed_concrete" and r["spec"] == COMPARE_SPEC]
    compare = {"spec": COMPARE_SPEC, "item": tests[0]["item"], "sources": src,
               "total": tests[0]["qty"], "unit": tests[0]["unit"],
               "tests": [{"test": t["test_type"], "freq": t["frequency"], "basis": t["calc_basis"],
                          "count": t["count_site"] or t["count_external"]} for t in tests],
               "crop": crop, "page": table}
    basis_no = re.search(r"제\d{4}-\d+호", rules["ready_mixed_concrete"].basis_version).group(0)

    table_rows = [{"item": r["item"], "test": r["test_type"], "qty": r["qty"], "unit": r["unit"],
                   "count": r["count_site"] or r["count_external"] or r["count_ks"]} for r in rows]
    data = {"pages": pages, "shots": {"cover": names[1], "flow": names[flow], "table": names[table]},
            "stack": [names[n] for n in stack], "boq": boq, "table_rows": table_rows,
            "sheet": sheet, "compare": {**compare, "crop_narrow": crop_narrow, "crop_a": crop_a, "crop_b": crop_b}, "forms": forms, "basis_no": basis_no, "block": BLOCK}
    (PUBLIC / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"pages={pages} flow=p{flow} table=p{table} boq_rows={len(boq)} table_rows={len(table_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
