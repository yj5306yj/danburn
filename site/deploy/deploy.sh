#!/usr/bin/env bash
# 랜딩 배포(Cloudflare Workers `danburn` → danburn.kr · www · danburn.danburn.workers.dev).
# 배포 폴더에는 site/landing 의 index.html·style.css·media 만 넣는다(스케치·초안은 올리지 않음).
# src/index.js 는 /media/ 영상에 바이트 범위(206) 응답을 붙인다 — iOS Safari 영상 재생용.
# 사용: site/deploy/deploy.sh            (wrangler 로그인 필요: npx wrangler whoami)
#       site/deploy/deploy.sh --dry-run  (올리지 않고 설정만 확인)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
landing="$here/../landing"
rm -rf "$here/public"
mkdir -p "$here/public"
cp "$landing/index.html" "$landing/style.css" "$here/public/"
cp -R "$landing/media" "$here/public/"
cd "$here"
npx --yes wrangler deploy "$@"
