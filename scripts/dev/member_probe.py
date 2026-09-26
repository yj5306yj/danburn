"""도급내역서에서 레미콘 규격별 부위 단서(section 단어·품명 단어) 빈도를 표준출력에 낸다.

사용: .venv/bin/python scripts/dev/member_probe.py <내역서.xlsx> [...] --block <블록>
- 레미콘 행: 규격이 레미콘 규격(굵은골재-강도-슬럼프)으로 읽히는 행(지급 레미콘, 사급 'C급 콘크리트 치기' 등).
- 타설 행: 품명에 '타설'이 있고 단위가 m3인 사급 행. 규격의 슬럼프(S15cm 등)와 철근/무근으로 묶는다.
블록 고르기: BoqLine.block 에 블록명이 들어 있으면 그 열, 블록 열이 없는 시트는 시트 이름 꼬리
(예: '내역(건)B동' → 'B동')가 블록명 안에 있으면 고른다. 꼬리 없는 공구 합계 시트는 뺀다.
로컬 실자료 확인용이다. 결과는 파일로 남기지 않는다(실명·값 누출 방지).
"""
import argparse
import re
from collections import Counter, defaultdict

from danburn.boq import SECTION_SEP, normalize_concrete_spec, normalize_unit, read_boq

_SLUMP = re.compile(r"S\s*(\d{1,2})\s*cm", re.I)


def _key(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", text.lower())


def in_block(line, block: str) -> bool:
    want = _key(block)
    if line.block:
        have = _key(line.block)
        return bool(have) and (want in have or have in want)
    tail = _key(re.sub(r"^.*\)", "", line.sheet))
    return bool(tail) and tail in want


def _parts(section: str) -> list[str]:
    return [re.sub(r"\s*-\s*\d+$", "", p).strip() for p in section.split(SECTION_SEP) if p.strip()]


def _show(title: str, counter: Counter, qty: dict) -> None:
    items = ", ".join(f"{k or '(없음)'} {v}행/{qty[k]:,.0f}" for k, v in counter.most_common())
    print(f"    {title}: {items}")


def _report(label: str, lines) -> None:
    first, middle, last, names = Counter(), Counter(), Counter(), Counter()
    q_first, q_middle, q_last, q_names = (defaultdict(float) for _ in range(4))
    for line in lines:
        parts = _parts(line.section)
        head = parts[0] if parts else ""
        mid = SECTION_SEP.join(parts[1:-1]) if len(parts) > 2 else ""
        tail = parts[-1] if parts else ""
        for counter, qty, key in ((first, q_first, head), (middle, q_middle, mid),
                                  (last, q_last, tail), (names, q_names, line.name[:20])):
            counter[key] += 1
            qty[key] += line.qty
    print(f"  {label}  합계 {sum(l.qty for l in lines):,.0f} ({len(lines)}행)")
    _show("시설(첫 단어)", first, q_first)
    _show("중간", middle, q_middle)
    _show("끝 단어", last, q_last)
    _show("품명", names, q_names)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--block", required=True)
    args = ap.parse_args()

    lines = [l for f in args.files for l in read_boq(f) if in_block(l, args.block)]
    concrete = defaultdict(list)
    pours = defaultdict(list)
    for line in lines:
        spec = normalize_concrete_spec(line.spec)
        if spec:
            concrete[(line.discipline, spec, line.supply)].append(line)
        elif "타설" in line.name and normalize_unit(line.unit) == "m3":
            slump = _SLUMP.search(line.spec)
            kind = "무근" if "무근" in line.name else ("철근" if "철근" in line.name else "기타")
            pours[(line.discipline, kind, f"S{slump.group(1)}" if slump else "S?")].append(line)

    print(f"# 블록 {args.block}: 행 {len(lines)}개")
    print("## 레미콘 규격 행 (공종, 규격, 지급/사급)")
    for key in sorted(concrete):
        _report(" / ".join(key), concrete[key])
    print("## 타설 행 (공종, 철근/무근, 슬럼프)")
    for key in sorted(pours):
        _report(" / ".join(key), pours[key])


if __name__ == "__main__":
    main()
