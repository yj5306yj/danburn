import os
import shutil
import subprocess
import sys
from pathlib import Path

# 테스트는 기본으로 네트워크에 나가지 않는다(check_basis 는 네트워크 표시 테스트에서만).
os.environ.setdefault("DANBURN_OFFLINE", "1")


def find_hwpx_validate(bindir: Path | None = None) -> Path | None:
    """python-hwpx 의 스키마 검사기 실행 파일. 지금 파이썬의 스크립트 폴더(맥·리눅스 bin/hwpx-validate,
    Windows Scripts\\hwpx-validate.exe)를 먼저, 없으면 PATH 에서 찾는다. 확장자 없는 이름만 보면 Windows 에서 놓친다."""
    bindir = Path(sys.executable).parent if bindir is None else bindir
    for name in ("hwpx-validate", "hwpx-validate.exe"):
        if (bindir / name).is_file():
            return bindir / name
    found = shutil.which("hwpx-validate", path=str(bindir)) or shutil.which("hwpx-validate")
    return Path(found) if found else None


VALIDATE = find_hwpx_validate()


def run_hwpx_validate(path: Path) -> None:
    """검사기를 실제로 돌려 종료 0 과 '검사한 부분이 있음'을 함께 확인한다(실행 없이 통과로 치지 않는다)."""
    assert VALIDATE is not None, "hwpx-validate 를 찾지 못함"
    r = subprocess.run([str(VALIDATE), str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "validated " in r.stdout, "검사기가 아무 부분도 검사하지 않음: " + r.stdout + r.stderr
