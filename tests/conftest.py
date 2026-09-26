import os

# 테스트는 기본으로 네트워크에 나가지 않는다(check_basis 는 네트워크 표시 테스트에서만).
os.environ.setdefault("DANBURN_OFFLINE", "1")
