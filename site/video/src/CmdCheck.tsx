import React, {useMemo} from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import data from '../public/cmd/check.json';
import {Line, Screen, Terminal, clamp, useFontsReady, useLayout} from './Term';

// 기존 계획서 검사: /danburn:check 옛기준 계획서.hwpx → 결과 한 줄 → [개정됨] 항목이 하나씩 쌓임 → 결과 줄의 '개정됨 5' 표시.
// 화면 줄은 public/cmd/check.json screen(= danburn check --offline 의 실제 출력 줄)에서만.
//  0–8 빈 프롬프트 · 8–54 명령 타이핑 · 60–72 머리·결과 · 90–170 개정됨 5건 · 184 알림 줄 · 206 '개정됨 5' 표시 · 285–300 루프 페이드
export const DURATION_CHECK = 300;

const SCREEN = data.screen as Screen[];
const AT = [0, 60, 70, 84, 92, 110, 128, 146, 164, 182, 190];
// 데스크톱: 긴 출력 두 줄. 휴대폰(줄 폭이 좁음): [개정됨] 항목과 결과 줄은 세 줄까지 — 21줄(CAP)을 꽉 채운다
const MAX_ROWS = (s: Screen) => (s.k === 'out' ? 2 : 1);
const MAX_ROWS_PHONE = (s: Screen) => (s.item || s.hl ? 3 : s.k === 'out' ? 2 : 1);
const END = 285;

export const CmdCheck: React.FC = () => {
  const frame = useCurrentFrame();
  const ready = useFontsReady();
  const L = useLayout();
  const lines: Line[] = useMemo(() => SCREEN.map((s, n) => ({...s, at: AT[n], rows: 0,
    typeAt: s.k === 'cmd' ? 8 : undefined})), []);
  if (!ready) return null;
  const fade = 1 - interpolate(frame, [END, END + 12], [0, 1], clamp);
  return <Terminal frame={frame} lines={lines} maxRows={L.phone ? MAX_ROWS_PHONE : MAX_ROWS} markAt={206} fade={fade} />;
};
