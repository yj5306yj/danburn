"""패키지에 들어 있는 기준 데이터 위치(L8-P1). 설치본(휠)에서도 저장소에서도 같은 곳을 본다."""
from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
RULES_DIR = DATA_DIR / "rules"
TEMPLATES_DIR = DATA_DIR / "templates"
