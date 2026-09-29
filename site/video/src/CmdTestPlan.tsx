import React, {useMemo} from 'react';
import {Easing, Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import data from '../public/cmd/testplan.json';
import {Layout, Line, Screen, Terminal, clamp, useFontsReady, useLayout} from './Term';
import {T} from './theme';

// 시험계획서만 따로: /danburn:test-plan 산출 → 결과 화면(만든 파일 · 시험 N행 · 확인할 것(할 일 붙음) · (스캔첨부) 빈칸 ·
// 다음 할 일 1) project.yaml 에 적고 다시 실행) → 한글 문서의 2부 가로 표 쪽과 3부 시험실 (스캔첨부) 쪽이 가운데(흐린 줄 위)에 나온다.
// 화면 줄은 public/cmd/testplan.json screen(= danburn test-plan 의 사람용 결과 화면 줄)에서만.
//  0–8 빈 프롬프트 · 8–44 명령 타이핑 · 56–150 결과 줄 · 170 '시험 N행'·'(스캔첨부) 빈칸 N곳' 표시 · 180–226 문서 쪽 · 226–285 머묾 · 285–300 루프 페이드
export const DURATION_TESTPLAN = 300;

const SCREEN = data.screen as Screen[];
const SHOTS = data.doc.shots;
const AT = [0, 56, 64, 76, 88, 94, 104, 110, 124, 130, 142];
const MAX_ROWS = (s: Screen) => (s.k === 'out' ? 2 : 1);
const MAX_ROWS_PHONE = (s: Screen) => (s.k === 'out' && !s.text.startsWith('  - ') ? 3 : s.k === 'out' ? 2 : 1);
// 문서 쪽 자리 [x, y, 폭]: 표 쪽은 A4 가로(폭:높이 = 297:210), 시험실 쪽은 A4 세로
const DOC = (L: Layout) => L.phone
  ? {table: [380, 272, 306], room: [210, 276, 150]}   // 휴대폰: '시험 N행' 아래 · '(스캔첨부) 빈칸' 위
  : {table: [540, 290, 380], room: [336, 300, 168]};   // 데스크톱: 강조(만든 파일·1) 줄)·표시(시험 N행·(스캔첨부) 빈칸) 글자는 가리지 않음
const ease = Easing.bezier(0.2, 0.7, 0.2, 1);
const END = 285;

export const CmdTestPlan: React.FC = () => {
  const frame = useCurrentFrame();
  const ready = useFontsReady();
  const L = useLayout();
  const D = DOC(L);
  const lines: Line[] = useMemo(() => SCREEN.map((s, n) => ({...s, at: AT[n], rows: 0,
    typeAt: s.k === 'cmd' ? 8 : undefined})), []);
  if (!ready) return null;
  const docIn = (d: number) => interpolate(frame, [180 + d, 206 + d], [0, 1], {...clamp, easing: ease});
  const fade = 1 - interpolate(frame, [END, END + 12], [0, 1], clamp);
  const dim = interpolate(frame, [180, 198], [0, 1], clamp);
  const page = (src: string, x: number, y: number, w: number, k: number) => (
    <div style={{position: 'absolute', left: x, top: y + (1 - k) * 60, width: w, opacity: k * fade}}>
      <div style={{background: '#fff', boxShadow: '0 12px 32px rgba(0,0,0,0.45)', outline: `1px solid ${T.edge}`}}>
        <Img src={staticFile(src)} style={{width: '100%', display: 'block'}} />
      </div>
    </div>
  );
  return (
    <Terminal frame={frame} lines={lines} maxRows={L.phone ? MAX_ROWS_PHONE : MAX_ROWS} dim={dim} markAt={170} fade={fade}>
      {page(SHOTS.table, D.table[0], D.table[1], D.table[2], docIn(0))}
      {page(SHOTS.room, D.room[0], D.room[1], D.room[2], docIn(12))}
    </Terminal>
  );
};
