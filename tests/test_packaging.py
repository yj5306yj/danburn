"""설치본에 기준 데이터가 들어가는지(L8-P1). 휠을 실제로 만들어 설치하는 검사는 scripts/check_wheel.sh(느림)."""
from __future__ import annotations

import tomllib
from fnmatch import fnmatch
from pathlib import Path

import pytest

import danburn
from danburn.paths import DATA_DIR, RULES_DIR, TEMPLATES_DIR
from danburn.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
PKG = Path(danburn.__file__).resolve().parent


def test_data_lives_inside_package():
    assert DATA_DIR == PKG / "data" and DATA_DIR.is_dir()
    for p in (RULES_DIR, TEMPLATES_DIR, DATA_DIR / "interview.yaml", DATA_DIR / "byeolpyo2_index.yaml",
              DATA_DIR / "extra_catalog.yaml", DATA_DIR / "common_specs.yaml", DATA_DIR / "member_keywords.yaml",
              TEMPLATES_DIR / "qplan.yaml", TEMPLATES_DIR / "project.example.yaml"):
        assert p.exists(), p
    assert not (ROOT / "data").exists()                   # 저장소 루트 data/ 는 없어야 한다(모듈이 거기를 보던 결함)


def test_package_data_globs_cover_every_data_file():
    conf = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = conf["tool"]["setuptools"]["package-data"]["danburn"]
    files = [p.relative_to(PKG).as_posix() for p in DATA_DIR.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    assert files and all(any(fnmatch(f, g) for g in globs) for f in files)


def test_modules_do_not_look_outside_package():
    for py in PKG.glob("*.py"):
        assert "parents[2]" not in py.read_text(encoding="utf-8"), py.name


def test_missing_rules_dir_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="규칙 폴더"):
        load_rules(tmp_path / "없음")
