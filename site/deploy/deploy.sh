#!/usr/bin/env bash
# 랜딩 배포(Cloudflare Workers `danburn` → danburn.kr · www · danburn.danburn.workers.dev).
# 배포 폴더에는 site/landing 의 아래 목록만 넣는다(스케치·초안은 올리지 않음):
#   index.html · en/(영문 쪽, 주소 /en) · 404.html · style.css · media/ · favicon.svg · robots.txt · sitemap.xml · _redirects(/about → /en)
# src/index.js 는 /media/ 영상에 바이트 범위(206) 응답을 붙인다 — iOS Safari 영상 재생용.
# 사용: site/deploy/deploy.sh            (wrangler 로그인 필요: npx wrangler whoami)
#       site/deploy/deploy.sh --dry-run  (올리지 않고 설정만 확인)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
landing="$here/../landing"
rm -rf "$here/public"
mkdir -p "$here/public"
cp "$landing/index.html" "$landing/404.html" "$landing/style.css" "$landing/favicon.svg" \
   "$landing/robots.txt" "$landing/sitemap.xml" "$landing/_redirects" "$here/public/"
cp -R "$landing/media" "$landing/en" "$here/public/"
# IndexNow 키 파일(32자리 16진수 이름의 .txt): 검색엔진에 새 주소를 알릴 때 소유 확인에 쓰인다
find "$landing" -maxdepth 1 -name "[0-9a-f]*.txt" ! -name robots.txt -exec cp {} "$here/public/" \;
cd "$here"
npx --yes wrangler deploy "$@"
