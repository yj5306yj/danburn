"""별표2 밖 자재 식별 — 조용한 누락을 “발주처 기준 필요”로 드러낸다(data/extra_catalog.yaml)."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

CATALOG = Path(__file__).resolve().parents[2] / "data" / "extra_catalog.yaml"


def _sq(s: str) -> str:
    return re.sub(r"[\s·\-]", "", (s or "")).upper()


def load_catalog(path: Path = CATALOG) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def flag_extras(lines, catalog: dict | None = None) -> dict:
    """입력 행에서 별표2 밖 자재를 찾는다 → {'owner_standard_needed': [...], 'site_measurements': [...]}.
    긴 이름부터 맞춘다. 노무·시공 행도 포함한다(자재가 시공 항목에 들어 있는 경우가 많다)."""
    cat = catalog or load_catalog()
    entries = sorted(((len(_sq(n)), e, n) for e in cat.get("materials", []) for n in e["names"]), key=lambda x: -x[0])
    hits: dict[str, dict] = {}
    for ln in lines:
        name = _sq(getattr(ln, "name", "") if not isinstance(ln, dict) else ln.get("name", ""))
        for _, e, n in entries:
            if _sq(n) in name:
                h = hits.setdefault(e["key"], {"key": e["key"], "label": e["label"], "lines": 0, "examples": []})
                h["lines"] += 1
                raw = ln.name if not isinstance(ln, dict) else ln.get("name", "")
                if raw not in h["examples"] and len(h["examples"]) < 3:
                    h["examples"].append(raw)
                break
    return {"owner_standard_needed": list(hits.values()),
            "site_measurements": [dict(m) for m in cat.get("site_measurements", [])]}
