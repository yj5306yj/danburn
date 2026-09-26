#!/usr/bin/env bash
# 맥(한컴 없음) 개발 도구 설치: Python 환경 + rhwp CLI. 전역 설치 없음.
# 사용: scripts/dev/setup-tools.sh   (필요: uv, gh, node>=20)
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$root"
[ -x .venv/bin/python ] || uv venv --python 3.12 .venv
uv pip install -q --python .venv/bin/python 'python-hwpx==6.5.0' openpyxl lxml pytest
RHWP=v0.8.6
arch="$(uname -m)"; [ "$arch" = arm64 ] && arch=aarch64
asset="rhwp-$RHWP-macos-$arch.tar.gz"
mkdir -p .tools && cd .tools
if [ ! -x rhwp/rhwp ]; then
  gh release download "$RHWP" -R edwardkim/rhwp -p "$asset" -p SHA256SUMS.txt --clobber
  grep " $asset\$" SHA256SUMS.txt | shasum -a 256 -c
  tar xzf "$asset"
fi
cd "$root"
echo "python-hwpx: $(.venv/bin/python -c 'import importlib.metadata as m;print(m.version("python-hwpx"))')"
echo "rhwp: $(.tools/rhwp/rhwp --version 2>/dev/null || echo installed)"
echo "kordoc: npx -y kordoc@4.15.4 <file>  (설치 없이 실행)"
