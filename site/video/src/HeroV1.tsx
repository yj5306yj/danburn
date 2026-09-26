import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import 'pretendard/dist/web/static/pretendard.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import data from '../public/data.json';
import {C, FONT, MONO, hatchBg} from './theme';

// v1(사용자 피드백 "눕지 말고 명확하게"): 바닥 시점 대신 정면. 판·쪽을 세워 글자가 읽히게 크게,
// 쪽은 옆으로 살짝 겹쳐 쌓고, 8.11 은 정면 확대(줌)로 줄이 채워지는 것을 보여 준다. 1920×1080 기준.
//  1  0–110   내역서 판이 서고 표 줄이 그려진다
//  2  90–230  규칙에 걸린 자재 행이 파랗게 → 칩이 파란 선을 따라 오른쪽 쪽 자리로
//  3  220–330 실제 계획서 쪽 5장(표지·목차·흐름표·양식·8.11)이 한 장씩 겹쳐 쌓인다
//  3b 330–450 8.11 쪽으로 확대, 파란 주사선을 따라 줄이 채워진다(카메라가 주사선을 따라감)
//  4  450–540 확대 풀림, 왼쪽에 "품질관리계획서.hwpx · N쪽" + 작은 "단번"
export const DURATION_V1 = 540;

type Row = {name: string; spec: string; unit: string; qty: number; material: string};
const BOQ = data.boq as Row[];

// 판에 보일 18행: 규칙에 걸린 자재를 앞에(종류가 겹치지 않게), 걸리지 않은 행(노무 등)을 사이사이에
const SHEET_ROWS: Row[] = (() => {
  const hit: Row[] = [];
  const seen = new Set<string>();
  for (const r of BOQ) {
    if (r.material && !seen.has(r.name + r.spec) && hit.length < 14) {
      seen.add(r.name + r.spec);
      hit.push(r);
    }
  }
  const miss = BOQ.filter((r) => !r.material).slice(0, 4);
  const out: Row[] = [];
  hit.forEach((r, i) => {
    out.push(r);
    if (i % 4 === 3 && miss.length) out.push(miss.shift()!);
  });
  return out.slice(0, 18);
})();

const SHEET = {x: 110, y: 110, w: 800, h: 860, top: 104, row: 42};
const SLOT = {x: 1150, y: 96, w: 566, h: 800, dx: 22, dy: 10}; // 쪽 자리(A4 비), 겹침 간격
const COLS = [{k: '품명', w: 300}, {k: '규격', w: 200}, {k: '단위', w: 90}, {k: '수량', w: 170}];
const fmt = (n: number) => n.toLocaleString('ko-KR', {maximumFractionDigits: 2});
const ease = Easing.bezier(0.2, 0.7, 0.2, 1);
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

// 두께 느낌: 같은 외곽선을 오른쪽 아래로 두 겹(원근 없이 정면)
const Card: React.FC<{x: number; y: number; w: number; h: number; blue?: boolean; radius?: number; children?: React.ReactNode; style?: React.CSSProperties}> =
  ({x, y, w, h, blue, radius = 10, children, style}) => (
    <div style={{position: 'absolute', left: x, top: y, width: w, height: h, ...style}}>
      {[10, 5].map((o) => (
        <div key={o} style={{position: 'absolute', left: o, top: o, width: w, height: h, borderRadius: radius,
          border: `1px solid ${C.line}`, background: C.bg}} />
      ))}
      <div style={{position: 'absolute', inset: 0, borderRadius: radius, border: `1px solid ${blue ? C.blue : C.lineDark}`,
        background: C.paper, overflow: 'hidden', boxShadow: blue ? `0 0 0 4px ${C.blueSoft}` : 'none'}}>{children}</div>
    </div>
  );

const Tag: React.FC<{x: number; y: number; text: string; blue?: boolean; opacity?: number; up?: number}> = ({x, y, text, blue, opacity = 1, up = 44}) => (
  <div style={{opacity}}>
    <svg style={{position: 'absolute', left: 0, top: 0, overflow: 'visible'}}>
      <line x1={x} y1={y} x2={x} y2={y - up + 8} stroke={blue ? C.blue : C.lineDark} strokeWidth={1} />
      <rect x={x - 4} y={y - 4} width={8} height={8} fill={C.paper} stroke={blue ? C.blue : C.lineDark} strokeWidth={1} />
    </svg>
    <div style={{position: 'absolute', left: x - 6, top: y - up - 16, fontFamily: MONO, fontSize: 17, letterSpacing: 1.4,
      whiteSpace: 'nowrap', color: blue ? C.blue : C.muted}}>{text}</div>
  </div>
);

export const HeroV1: React.FC = () => {
  const frame = useCurrentFrame();
  const stack = data.stack as string[];
  const top = stack.length - 1;

  // 1. 판
  const sheetIn = interpolate(frame, [0, 30], [0, 1], {...clamp, easing: ease});
  const rowsDrawn = interpolate(frame, [15, 95], [0, SHEET_ROWS.length], clamp);
  const sheetFade = interpolate(frame, [326, 350], [1, 0], clamp); // 확대 때는 판·선을 치워 8.11 만 보이게

  // 2. 걸린 행 → 칩
  const hitIdx = SHEET_ROWS.map((r, i) => (r.material ? i : -1)).filter((i) => i >= 0);
  const hot = (i: number) => {
    const k = hitIdx.indexOf(i);
    return k < 0 ? 0 : interpolate(frame, [88 + k * 5, 98 + k * 5], [0, 1], clamp);
  };
  const fly = (i: number) => {
    const k = hitIdx.indexOf(i);
    return k < 0 ? 0 : interpolate(frame, [120 + k * 6, 185 + k * 6], [0, 1], {...clamp, easing: ease});
  };
  const rowY = (i: number) => SHEET.y + SHEET.top + (i + 0.5) * SHEET.row;
  const target = (i: number) => {
    const k = Math.max(0, hitIdx.indexOf(i));
    return {x: SLOT.x, y: SLOT.y + 120 + (k * (SLOT.h - 240)) / Math.max(1, hitIdx.length - 1)};
  };
  const bend = (i: number) => SHEET.x + SHEET.w + 40 + hitIdx.indexOf(i) * 7;

  // 3. 쪽 쌓기
  const dropAt = (i: number) => 220 + i * 22;
  const slotIn = interpolate(frame, [150, 200], [0, 1], clamp);

  // 3b. 확대 + 채우기 (8.11 쪽 좌표계: 0~1)
  const fill = interpolate(frame, [355, 440], [0, 1], clamp);
  const scanY = 0.235 + fill * 0.625; // 표 머리 아래 ~ 표 끝
  const zoom = interpolate(frame, [328, 356, 446, 474], [1, 2.05, 2.05, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
  const topPage = {x: SLOT.x + top * SLOT.dx, y: SLOT.y + top * SLOT.dy};
  // 확대 중심: 쪽 가로 가운데, 세로는 주사선(화면 가운데로 끌어옴)
  // 주사선을 화면 아래쪽(가운데보다 약 1/3 아래)에 두어 채워진 줄이 화면 대부분을 차지하게
  const focus = {x: topPage.x + SLOT.w * 0.5, y: topPage.y + SLOT.h * Math.min(Math.max(scanY - 0.2, 0.33), 0.62)};
  const zt = (zoom - 1) / 1.05; // 0..1
  const cam = {
    tx: (960 - zoom * focus.x) * zt + 0 * (1 - zt),
    ty: (540 - zoom * focus.y) * zt,
  };
  const rowsCount = Math.round(fill * data.table_rows.length);

  // 4. 끝
  const endIn = interpolate(frame, [470, 505], [0, 1], {...clamp, easing: ease});

  const colX = COLS.reduce<number[]>((a, c, i) => [...a, i ? a[i - 1] + COLS[i - 1].w : 28], []);

  return (
    <AbsoluteFill style={{...hatchBg, fontFamily: FONT, color: C.ink, overflow: 'hidden'}}>
      {/* 카메라(확대)는 판·선·쪽 전체에 건다 */}
      <div style={{position: 'absolute', inset: 0, transformOrigin: '0 0',
        transform: `translate(${cam.tx}px, ${cam.ty}px) scale(${zoom})`}}>
        {/* 1. 내역서 판 */}
        <Card x={SHEET.x} y={SHEET.y + (1 - sheetIn) * 40} w={SHEET.w} h={SHEET.h} style={{opacity: sheetIn * sheetFade}}>
          <div style={{height: 52, borderBottom: `1px solid ${C.line}`, display: 'flex', alignItems: 'center', padding: '0 24px',
            fontFamily: MONO, fontSize: 17, color: C.muted, gap: 14}}>
            <span style={{width: 11, height: 11, borderRadius: 6, border: `1px solid ${C.line}`}} />
            example_boq.xlsx · 나동 도급내역
          </div>
          <div style={{position: 'absolute', top: 52, left: 0, right: 0, height: 52, borderBottom: `1px solid ${C.lineDark}`,
            fontSize: 19, color: C.muted}}>
            {COLS.map((c, i) => (
              <div key={c.k} style={{position: 'absolute', left: colX[i], top: 13, width: c.w - 24, textAlign: i === 3 ? 'right' : 'left'}}>{c.k}</div>
            ))}
          </div>
          {SHEET_ROWS.map((r, i) => {
            const shown = Math.min(1, Math.max(0, rowsDrawn - i));
            const h = hot(i);
            return (
              <div key={i} style={{position: 'absolute', top: SHEET.top + i * SHEET.row, left: 0, right: 0, height: SHEET.row,
                borderBottom: `1px solid ${C.line}`, opacity: shown, fontSize: 21,
                background: h ? `rgba(219,232,253,${h})` : 'transparent'}}>
                {[r.name, r.spec, r.unit, fmt(r.qty)].map((v, j) => (
                  <div key={j} style={{position: 'absolute', left: colX[j], top: 7, width: COLS[j].w - 24, whiteSpace: 'nowrap',
                    overflow: 'hidden', textOverflow: 'ellipsis', textAlign: j === 3 ? 'right' : 'left',
                    color: h > 0.5 && j === 0 ? C.blue : C.ink, fontVariantNumeric: 'tabular-nums'}}>{v}</div>
                ))}
              </div>
            );
          })}
        </Card>

        {/* 2. 파란 선 */}
        <svg style={{position: 'absolute', left: 0, top: 0, overflow: 'visible', opacity: sheetFade}} width={1920} height={1080}>
          {hitIdx.map((i) => {
            const a = {x: SHEET.x + SHEET.w, y: rowY(i)};
            const b = target(i);
            const mx = bend(i);
            const len = mx - a.x + Math.hypot(b.x - mx, b.y - a.y) + 40;
            const drawn = Math.min(1, hot(i) * 0.25 + fly(i) * 1.2);
            return (
              <path key={i} d={`M ${a.x} ${a.y} L ${mx} ${a.y} L ${b.x - 30} ${b.y} L ${b.x} ${b.y}`} fill="none"
                stroke={C.blueLine} strokeWidth={1.2} strokeDasharray={len} strokeDashoffset={len * (1 - drawn)} />
            );
          })}
        </svg>
        {hitIdx.map((i) => {
          const f = fly(i);
          if (f <= 0 || f >= 1) return null;
          const a = {x: SHEET.x + SHEET.w, y: rowY(i)};
          const b = target(i);
          const mx = bend(i);
          const p = f < 0.35 ? {x: a.x + (mx - a.x) * (f / 0.35), y: a.y}
            : {x: mx + (b.x - mx) * ((f - 0.35) / 0.65), y: a.y + (b.y - a.y) * ((f - 0.35) / 0.65)};
          const r = SHEET_ROWS[i];
          return (
            <div key={i} style={{position: 'absolute', left: p.x + 6, top: p.y - 17, padding: '5px 12px', borderRadius: 6,
              background: C.blueSoft, border: `1px solid ${C.blue}`, fontSize: 18, whiteSpace: 'nowrap',
              opacity: interpolate(f, [0, 0.08, 0.88, 1], [0, 1, 1, 0])}}>
              {r.name} <span style={{color: C.muted}}>→</span> {r.material}{' '}
              <span style={{fontFamily: MONO, color: C.blue, fontSize: 15}}>{r.spec}</span>
            </div>
          );
        })}

        {/* 3. 쪽 자리(점선) + 쪽 */}
        <div style={{position: 'absolute', left: SLOT.x - 14, top: SLOT.y - 14, width: SLOT.w + top * SLOT.dx + 28,
          height: SLOT.h + top * SLOT.dy + 28, border: `1px dashed ${C.line}`, borderRadius: 14, opacity: slotIn * (1 - endIn * 0.7)}} />
        {stack.map((src, i) => {
          const t = interpolate(frame, [dropAt(i), dropAt(i) + 20], [0, 1], {...clamp, easing: ease});
          if (t <= 0) return null;
          const isTop = i === top;
          return (
            <Card key={src} x={SLOT.x + i * SLOT.dx + (1 - t) * 60} y={SLOT.y + i * SLOT.dy} w={SLOT.w} h={SLOT.h} radius={3}
              blue={isTop && frame > 330 && frame < 470} style={{opacity: t * (isTop ? 1 : 1 - zt * 0.85)}}>
              <Img src={staticFile(src)} style={{width: '100%', height: '100%'}} />
              {isTop && (
                <>
                  <div style={{position: 'absolute', left: '7%', right: '5%', top: `${scanY * 100}%`, bottom: '13%',
                    background: C.paper, opacity: fill >= 1 ? 0 : 1}} />
                  <div style={{position: 'absolute', left: '6%', right: '4%', top: `${scanY * 100}%`, height: 3 / zoom,
                    background: C.blue, opacity: fill > 0 && fill < 1 ? 1 : 0}} />
                </>
              )}
            </Card>
          );
        })}
      </div>

      {/* 화면 고정 라벨(확대와 무관) */}
      <Tag x={SHEET.x + 30} y={SHEET.y - 4} text="BOQ · XLSX" opacity={sheetIn * (1 - zt) * interpolate(frame, [450, 480], [1, 0], clamp)} />
      <Tag x={SLOT.x + 30} y={SLOT.y - 4} text="표지 · 목차 · 흐름표 · 양식 · 8.11" opacity={slotIn * (1 - zt) * (1 - endIn)} />
      <div style={{position: 'absolute', left: 64, top: 52, fontFamily: MONO, fontSize: 22, letterSpacing: 1.5, color: C.blue,
        opacity: zt, padding: '8px 14px', background: C.paper, border: `1px solid ${C.blue}`, borderRadius: 6}}>
        8.11 품질시험계획 · {rowsCount}/{data.table_rows.length}행
      </div>

      {/* 4. 끝 글 */}
      <div style={{position: 'absolute', left: 110, top: 400, opacity: endIn, transform: `translateY(${(1 - endIn) * 16}px)`}}>
        <div style={{fontFamily: MONO, fontSize: 18, letterSpacing: 1.6, color: C.blue, marginBottom: 14}}>QUALITY MANAGEMENT PLAN · HWPX</div>
        <div style={{fontSize: 64, fontWeight: 600, letterSpacing: -1.2, lineHeight: 1.15}}>
          품질관리계획서.hwpx<br />
          <span style={{color: C.muted, fontWeight: 400}}>·</span> {data.pages}쪽
        </div>
        <div style={{marginTop: 22, fontSize: 26, color: C.muted}}>단번</div>
      </div>
    </AbsoluteFill>
  );
};
