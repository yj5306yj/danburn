"""도급내역서를 read_boq로 읽어 (공종, 지급/사급, 블록(없으면 시트), 품명 앞 10자, 정규화 규격, 단위)별 합계를 표준출력에 낸다.

레미콘은 슬럼프 mm 규격, 철근 재료 행은 "SD500 D13" 꼴로 정규화한다.

사용: .venv/bin/python scripts/dev/boq_probe.py <내역서.xlsx>
로컬 실자료 확인용이다. 결과는 파일로 남기지 않는다(실명·값 누출 방지).
"""
import sys
from collections import defaultdict

from danburn.boq import normalize_concrete_spec, normalize_rebar_spec, normalize_unit, read_boq


def main(path: str) -> None:
    lines = read_boq(path)
    sums: dict[tuple, float] = defaultdict(float)
    counts: dict[tuple, int] = defaultdict(int)
    for line in lines:
        spec = (normalize_concrete_spec(line.spec) or normalize_rebar_spec(line.name, line.spec)
                or line.spec)
        # 블록 열이 없는 시트(블록별 내역 시트)는 시트 이름으로 구분한다.
        key = (line.discipline, line.supply, line.block or line.sheet, line.name[:10], spec,
               normalize_unit(line.unit))
        sums[key] += line.qty
        counts[key] += 1
    print(f"행 {len(lines)}개, 묶음 {len(sums)}개")
    for key in sorted(sums):
        print("\t".join(key), f"{sums[key]:,.2f}", f"({counts[key]}행)", sep="\t")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
