import React, {useEffect, useMemo, useState} from 'react';
import {AbsoluteFill, continueRender, delayRender, interpolate, useVideoConfig} from 'remotion';
import 'pretendard/dist/web/static/pretendard.css';
import '@fontsource/ibm-plex-mono/400.css';
import {T, TERM_FONT} from './theme';

// CmdStart·CmdCheck 공용 터미널. 화면 글자는 public/cmd/*.json 의 screen 에서만 온다(여기서 문구를 만들지 않는다).
// 줄 바꿈은 터미널처럼 글자 단위로 직접 한다(캔버스로 폭을 재서) — 스크롤·강조 위치를 정확히 알기 위해.
// 줄 수를 넘으면 마지막 줄 끝을 '…'로 자른다(글자는 바꾸지 않음).

// 판 두 가지(같은 줄·같은 속도): 데스크톱 4:3 960×720 · 휴대폰 4:5 720×900(글자를 키우고 줄 폭을 줄임).
// 보이는 글자 = size × 표시폭 / w. 데스크톱 28/960: 480px → 14px, 560px → 16.3px.
// 휴대폰 27/720: 358px(390 화면 − 16px 여백 두 쪽) → 13.4px, 328px(360 화면) → 12.3px.
export type Layout = {w: number; h: number; size: number; lh: number; bar: number; padX: number; padY: number; textW: number; cap: number; phone: boolean};
const layoutOf = (w: number, h: number, size: number, lh: number, bar: number, padX: number, padY: number, phone: boolean): Layout =>
  ({w, h, size, lh, bar, padX, padY, phone, textW: w - padX * 2, cap: Math.floor((h - bar - padY * 2) / lh)});
export const DESKTOP = layoutOf(960, 720, 28, 40, 40, 30, 20, false);
export const PHONE = layoutOf(720, 900, 27, 39, 36, 24, 16, true);
export function useLayout(): Layout {
  const {width} = useVideoConfig();
  return width === PHONE.w ? PHONE : DESKTOP;
}
const PROMPT = '› ';             // 입력 줄 앞 중립 기호

export type Screen = {k: 'cmd' | 'in' | 'out' | 'gap'; text: string; i?: number; a?: number; hl?: boolean; item?: boolean; mark?: string};
export type Line = Screen & {at: number; rows: number; typeAt?: number};   // at: 나타나는 프레임, typeAt: 타이핑 시작
type Style = 'out' | 'muted' | 'bright' | 'tag' | 'type';

export const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const CPF = 0.6;                 // 타이핑: 프레임당 글자

let ctx: CanvasRenderingContext2D | null = null;
const measure = (s: string, size: number) => {
  if (!ctx) ctx = document.createElement('canvas').getContext('2d')!;
  ctx.font = `400 ${size}px ${TERM_FONT}`;
  return ctx.measureText(s).width;
};

export function useFontsReady() {
  const [ready, setReady] = useState(false);
  const [handle] = useState(() => delayRender('터미널 글꼴'));
  useEffect(() => {
    Promise.all([
      document.fonts.load(`400 28px 'IBM Plex Mono'`, 'Aa0'),
      document.fonts.load(`400 28px Pretendard`, '가나'),
    ]).then(() => {
      ctx = null;
      setReady(true);
      continueRender(handle);
    });
  }, [handle]);
  return ready;
}

// 글자 단위로 폭에 맞춰 줄을 나눈다. [줄 글자, 시작 위치][]
export function wrap(text: string, width: number, maxRows: number, size: number): {rows: [string, number][]; cut: boolean} {
  const chars = Array.from(text);
  const rows: [string, number][] = [];
  let cur = '';
  let start = 0;
  chars.forEach((ch, n) => {
    if (cur && measure(cur + ch, size) > width) {
      // 띄어쓰기가 줄 앞쪽 40% 뒤에 있으면 거기서 바꾼다(KCS 29 같은 낱말이 갈라지지 않게). 없으면 글자 단위
      const cs = Array.from(cur);
      const sp = cs.lastIndexOf(' ');
      if (ch !== ' ' && sp > cs.length * 0.4) {
        rows.push([cs.slice(0, sp + 1).join(''), start]);
        cur = cs.slice(sp + 1).join('');
        start += sp + 1;
      } else {
        rows.push([cur, start]);
        cur = '';
        start = n;
      }
    }
    cur += ch;
  });
  rows.push([cur, start]);
  if (rows.length <= maxRows) return {rows, cut: false};
  const kept = rows.slice(0, maxRows);
  let last = kept[maxRows - 1][0];
  while (last && measure(last + '…', size) > width) last = Array.from(last).slice(0, -1).join('');
  kept[maxRows - 1] = [last.replace(/\s+$/, ''), kept[maxRows - 1][1]];
  return {rows: kept, cut: true};
}

// 글자 위치별 모양: [개정됨] 머리는 노란 칸, 옛 인용은 회색, '→ 현행 …'은 밝게
function styles(l: Line): Style[] {
  const n = Array.from(l.text).length;
  const s: Style[] = Array(n).fill(l.k === 'gap' ? 'muted' : l.hl ? 'bright' : 'out');
  if (l.item) {
    const chars = Array.from(l.text);
    const tagEnd = chars.indexOf(']') + 1;
    const arrow = l.text.indexOf(' → ');
    const arrowAt = arrow < 0 ? n : Array.from(l.text.slice(0, arrow)).length;
    for (let k = 0; k < n; k++) s[k] = k < tagEnd ? 'tag' : k < arrowAt ? 'muted' : 'bright';
  }
  return s;
}

const COLOR: Record<Style, React.CSSProperties> = {
  out: {color: T.out},
  muted: {color: T.muted},
  bright: {color: T.text},
  tag: {color: T.bg, background: T.yellow},
  type: {color: T.yellow},
};

const Cursor: React.FC<{frame: number; on?: boolean; size: number}> = ({frame, on, size}) => (
  <span style={{display: 'inline-block', width: size * 0.55, height: size * 1.05, verticalAlign: 'text-bottom', marginLeft: 1,
    background: T.yellow, opacity: on || Math.floor(frame / 15) % 2 === 0 ? 0.9 : 0}} />
);

export const Terminal: React.FC<{frame: number; lines: Line[]; maxRows: (s: Screen) => number; dim?: number; markAt?: number;
  fade?: number; children?: React.ReactNode}> = ({frame, lines, maxRows, dim = 0, markAt = Infinity, fade = 1, children}) => {
  const L = useLayout();
  const {w: W, bar: BAR, padX: PAD_X, padY: PAD_Y, lh: LH, cap: CAP, size: SIZE} = L;
  const wrapped = useMemo(() => lines.map((l) => {
    const typed = l.k === 'cmd' || l.k === 'in';
    const full = typed ? PROMPT + l.text : l.text;
    return {l, typed, ...wrap(full, L.textW, maxRows(l), L.size)};
  }), [lines, maxRows, L]);

  // 스크롤: 나타난 줄 수가 CAP 을 넘으면 넘친 만큼 부드럽게 올린다
  const shown = wrapped.reduce((a, w) => a + w.rows.length * interpolate(frame, [w.l.at, w.l.at + 6], [0, 1], clamp), 0);
  const scroll = Math.max(0, shown - CAP) * LH;
  const typing = wrapped.find((w) => w.typed && frame >= w.l.at && frame < (w.l.typeAt ?? w.l.at) + Array.from(w.l.text).length / CPF + 4);

  return (
    <AbsoluteFill style={{background: T.bg, fontFamily: TERM_FONT, fontSize: SIZE, lineHeight: `${LH}px`, overflow: 'hidden'}}>
      <div style={{position: 'absolute', left: 0, top: 0, width: W, height: BAR, background: T.bar, borderBottom: `1px solid ${T.edge}`,
        display: 'flex', alignItems: 'center', gap: 10, paddingLeft: 18}}>
        {[0, 1, 2].map((d) => <span key={d} style={{width: 12, height: 12, borderRadius: 6, background: T.dot}} />)}
      </div>
      <div style={{position: 'absolute', left: PAD_X, top: BAR + PAD_Y, width: L.textW, height: CAP * LH, overflow: 'hidden'}}>
        <div style={{transform: `translateY(${-scroll}px)`, opacity: fade}}>
          {wrapped.map(({l, typed, rows, cut}, li) => {
            if (frame < l.at) return null;
            const op = interpolate(frame, [l.at, l.at + 4], [0, 1], clamp);
            const st = styles(l);
            // 타이핑: 프롬프트 뒤 글자를 CPF 속도로
            const nTyped = typed ? Math.floor(Math.max(0, frame - (l.typeAt ?? l.at)) * CPF) : Infinity;
            const markOn = l.mark ? interpolate(frame, [markAt, markAt + 8], [0, 1], clamp) : 0;
            const markStart = l.mark ? Array.from(l.text.slice(0, l.text.indexOf(l.mark))).length : -1;
            const markEnd = markStart + (l.mark ? Array.from(l.mark).length : 0);
            const flash = l.item ? interpolate(frame, [l.at, l.at + 6, l.at + 30], [0, 1, 0.35], clamp) : 0;
            const isTyping = typing === wrapped[li];
            const lineDim = dim && !l.hl ? 1 - dim * 0.6 : 1;
            return (
              <div key={li} style={{position: 'relative', opacity: op * lineDim,
                background: l.hl ? T.yellowSoft : l.item ? `rgba(245,197,66,${0.1 * flash})` : undefined,
                boxShadow: l.hl ? `inset 4px 0 0 ${T.yellow}` : undefined, marginLeft: -PAD_X / 2, paddingLeft: PAD_X / 2}}>
                {rows.map(([row, start], ri) => {
                  const chars = Array.from(row);
                  const last = ri === rows.length - 1;
                  return (
                    <div key={ri} style={{height: LH, whiteSpace: 'pre'}}>
                      {chars.map((ch, ci) => {
                        const k = start + ci;
                        if (typed) {
                          const body = k - Array.from(PROMPT).length;
                          if (body >= nTyped) return null;
                          return <span key={ci} style={body < 0 ? {color: T.muted} : COLOR.type}>{ch}</span>;
                        }
                        const lk = k;
                        const inMark = lk >= markStart && lk < markEnd;
                        return <span key={ci} style={{...COLOR[st[lk]],
                          ...(inMark && markOn ? {background: `rgba(245,197,66,${0.95 * markOn})`, color: T.bg} : {})}}>{ch}</span>;
                      })}
                      {last && cut ? <span style={{color: T.muted}}>…</span> : null}
                      {last && typed && isTyping ? <Cursor frame={frame} size={SIZE} on={isTyping && nTyped < Array.from(l.text).length} /> : null}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
      {children}
    </AbsoluteFill>
  );
};
