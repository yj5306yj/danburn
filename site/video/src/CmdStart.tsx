import React, {useMemo} from 'react';
import {Easing, Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import data from '../public/cmd/start.json';
import {Layout, Line, Screen, Terminal, clamp, useFontsReady, useLayout} from './Term';
import {T} from './theme';

// 새로 만들기: /danburn:start 를 치면 도구가 묻고(내역서·동) 판정한 뒤 계획서를 만든다 → 계획서 쪽이 나온다.
// 화면 줄은 public/cmd/start.json screen(= danburn start --plain 의 실제 출력 줄 + 답 목록)에서만.
//  0–8 빈 프롬프트 · 8–32 명령 타이핑 · 38–190 질문·답·판정·만들기 · 196–240 계획서 쪽 · 240–285 머묾 · 285–300 루프 페이드
export const DURATION_START = 300;

const SCREEN = data.screen as Screen[];
const SHOTS = data.doc.shots;
// 줄마다 나타나는 프레임(명령 뒤) — 질문 다음 입력 줄은 잠깐 뒤 타이핑
const AT = [0, 40, 52, 70, 88, 100, 116, 124, 130, 136, 148, 156, 168, 182];
// 보이는 줄 수(CAP) 안에 명령 줄까지 남도록: 읽은 결과(READ)는 한 줄, 나머지 긴 출력은 두 줄에서 끝을 '…'로(두 판 같음)
const MAX_ROWS = (s: Screen) => (s.text.startsWith('READ ') ? 1 : s.k === 'out' ? 2 : 1);
// 휴대폰은 줄 폭이 좁고 CAP 이 21줄이라 질문 줄 셋·READ 둘까지(18줄)
const MAX_ROWS_PHONE = (s: Screen) => (s.text.startsWith('Q') ? 3 : s.k === 'out' ? 2 : 1);
// 계획서 쪽 자리: 데스크톱은 오른쪽, 휴대폰은 마지막 '계획서:' 줄 위 오른쪽
const DOC = (L: Layout) => L.phone
  ? {table: [440, 190, 236], cover: [388, 226, 236], label: 22}
  : {table: [664, 72, 268], cover: [600, 112, 268], label: 24};
const ease = Easing.bezier(0.2, 0.7, 0.2, 1);
const END = 285;

export const CmdStart: React.FC = () => {
  const frame = useCurrentFrame();
  const ready = useFontsReady();
  const L = useLayout();
  const D = DOC(L);
  const lines: Line[] = useMemo(() => SCREEN.map((s, n) => ({...s, at: AT[n], rows: 0,
    typeAt: s.k === 'cmd' ? 8 : s.k === 'in' ? AT[n] + 4 : undefined})), []);
  if (!ready) return null;
  const docIn = (d: number) => interpolate(frame, [196 + d, 222 + d], [0, 1], {...clamp, easing: ease});
  const fade = 1 - interpolate(frame, [END, END + 12], [0, 1], clamp);
  const dim = interpolate(frame, [196, 214], [0, 1], clamp);
  const page = (src: string, x: number, y: number, w: number, k: number, label?: string) => (
    <div style={{position: 'absolute', left: x, top: y + (1 - k) * 60, width: w, opacity: k * fade}}>
      <div style={{background: '#fff', boxShadow: '0 12px 32px rgba(0,0,0,0.45)', outline: `1px solid ${T.edge}`}}>
        <Img src={staticFile(src)} style={{width: '100%', display: 'block'}} />
      </div>
      {label ? <div style={{marginTop: 10, fontSize: D.label, lineHeight: `${L.lh}px`, color: T.yellow, whiteSpace: 'nowrap'}}>{label}</div> : null}
    </div>
  );
  return (
    <Terminal frame={frame} lines={lines} maxRows={L.phone ? MAX_ROWS_PHONE : MAX_ROWS} dim={dim} fade={fade}>
      {page(SHOTS.table, D.table[0], D.table[1], D.table[2], docIn(10))}
      {page(SHOTS.cover, D.cover[0], D.cover[1], D.cover[2], docIn(0), data.doc.file)}
    </Terminal>
  );
};
