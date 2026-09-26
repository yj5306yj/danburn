"""맥(한컴 없음) HWPX 도구 사슬 스모크: 합성 시험계획표 HWPX를 만든다.

사용: .venv/bin/python scripts/dev/hwpx_smoke.py <출력.hwpx>
자료는 전부 합성이다(실제 현장·회사 없음).
"""
import sys
from hwpx import HwpxDocument

rows = [
    ("종목", "시험항목", "빈도", "계획횟수"),
    ("레미콘", "압축강도", "120㎥마다", "12"),
    ("레미콘", "슬럼프", "120㎥마다", "12"),
    ("철근", "인장강도", "50t마다", "3"),
]
doc = HwpxDocument.new()
doc.add_heading("품질시험계획표 (합성 예시)", level=1)
doc.add_paragraph("아래 표는 도구 점검용 합성 자료이다.")
table = doc.add_table(len(rows), len(rows[0]))
for r, row in enumerate(rows):
    for c, val in enumerate(row):
        table.set_cell_text(r, c, val)
report = doc.save_to_path(sys.argv[1], return_report=True)
print("saved", sys.argv[1], report)
