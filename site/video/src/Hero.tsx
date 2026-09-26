import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import 'pretendard/dist/web/static/pretendard.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import data from '../public/data.json';
import {C, FONT, MONO, hatchBg} from './theme';
import {isoTransform, project} from './iso';

// 장면(30fps, 540프레임 = 18초)
//  1  0–120   내역서 판이 놓이고 표가 그려진다
//  2  120–240 규칙에 걸린 자재 행이 파랗게 표시되고 파란 선을 따라 계획서 쪽으로 간다
//  3  240–450 실제 계획서 쪽(표지·목차·흐름표·양식·8.11)이 한 장씩 쌓이고 8.11 표에 줄이 채워진다
//  4  450–540 끝: "품질관리계획서.hwpx · N쪽" + 작은 "단번"
export const DURATION = 540;

type Row = {name: string; spec: string; unit: string; qty: number; material: string};
const BOQ = data.boq as Row[];

// 판 위에 보일 내역서 행: 규칙에 걸린 자재를 서로 다른 이름으로 앞에, 걸리지 않은 행 몇 개를 섞는다.
const SHEET_ROWS: Row[] = (() => {
  const hit: Row[] = [];
  const seen = new Set<string>();
  for (const r of BOQ) {
    if (r.material && !seen.has(r.material + r.spec) && hit.length < 11) {
      seen.add(r.material + r.spec);
      hit.push(r);
    }
  }
  const miss = BOQ.filter((r) => !r.material).slice(0, 3);
  return [...hit.slice(0, 4), miss[0], ...hit.slice(4, 8), miss[1], ...hit.slice(8), miss[2]].filter(Boolean);
})();

const SHEET = {w: 720, h: 560, row: 32, head: 76};
const PAGE = {w: 380, h: 537}; // A4 비
const fmt = (n: number) => n.toLocaleString('ko-KR', {maximumFractionDigits: 2});

const ease = Easing.bezier(0.2, 0.7, 0.2, 1);
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

// 판 두께: 같은 모양 외곽선을 아래로 두 겹
const Slab: React.FC<{w: number; h: number; children?: React.ReactNode; radius?: number}> = ({w, h, children, radius = 12}) => (
  <>
    {[-10, -5].map((z) => (
      <div key={z} style={{position: 'absolute', width: w, height: h, borderRadius: radius, border: `1px solid ${C.line}`,
        background: C.bg, transform: `translateZ(${z}px)`}} />
    ))}
    <div style={{position: 'absolute', width: w, height: h, borderRadius: radius, border: `1px solid ${C.lineDark}`,
      background: C.paper, overflow: 'hidden'}}>{children}</div>
  </>
);

const Label: React.FC<{x: number; y: number; text: string; dx?: number; dy?: number; opacity?: number; blue?: boolean}> = ({x, y, text, dx = 0, dy = -70, opacity = 1, blue}) => (
  <div style={{opacity}}>
    <svg style={{position: 'absolute', left: 0, top: 0, overflow: 'visible'}}>
      <line x1={x} y1={y} x2={x + dx} y2={dy < 0 ? y + dy + 14 : y + dy - 10} stroke={blue ? C.blue : C.lineDark} strokeWidth={1} />
      <rect x={x - 4} y={y - 4} width={8} height={8} fill={C.paper} stroke={blue ? C.blue : C.lineDark} strokeWidth={1} />
    </svg>
    <div style={{position: 'absolute', left: x + dx - 200, top: y + dy - 6, width: 400, textAlign: 'center', fontFamily: MONO,
      fontSize: 15, letterSpacing: 1.2, color: blue ? C.blue : C.muted}}>{text}</div>
  </div>
);

export const Hero: React.FC = () => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const wide = width / height > 1.2;

  // 판 원점(화면 좌표): 16:9 는 왼쪽 판·오른쪽 쪽 더미, 4:5 는 위·아래
  const SO = wide ? {x: width * 0.12, y: height * 0.41} : {x: width * 0.08, y: height * 0.36};
  const PO = wide ? {x: width * 0.56, y: height * 0.44} : {x: width * 0.34, y: height * 0.8};

  // 1. 판 들어오기 + 표 줄 그리기
  const sheetIn = interpolate(frame, [0, 40], [0, 1], {...clamp, easing: ease});
  const rowsDrawn = interpolate(frame, [20, 110], [0, SHEET_ROWS.length], clamp);
  const sheetDim = interpolate(frame, [440, 480], [1, 0.45], clamp);

  // 2. 걸린 행 파랗게 → 칩이 선을 따라 이동
  const hitIdx = SHEET_ROWS.map((r, i) => (r.material ? i : -1)).filter((i) => i >= 0);
  const rowHot = (i: number) => {
    const k = hitIdx.indexOf(i);
    if (k < 0) return 0;
    return interpolate(frame, [95 + k * 9, 105 + k * 9], [0, 1], clamp);
  };
  const rowFly = (i: number) => {
    const k = hitIdx.indexOf(i);
    return k < 0 ? 0 : interpolate(frame, [130 + k * 8, 200 + k * 8], [0, 1], {...clamp, easing: ease});
  };

  // 3. 쪽 쌓기 + 8.11 채우기
  const stack = data.stack as string[];
  const dropAt = (i: number) => 240 + i * 26;
  const fill = interpolate(frame, [372, 450], [0, 1], clamp);
  const rowsCount = Math.round(fill * data.table_rows.length);

  // 4. 끝 글
  const endIn = interpolate(frame, [460, 500], [0, 1], {...clamp, easing: ease});

  // 연결선: 판 오른쪽 가장자리 → 쪽 더미 왼쪽 모서리 (평면 좌표를 투영)
  const sheetEdge = (i: number) => {
    const p = project(SHEET.w, SHEET.head + (i + 0.5) * SHEET.row, 0);
    return {x: SO.x + p.x, y: SO.y + p.y};
  };
  const stackIn = (i: number) => {
    const k = Math.max(0, hitIdx.indexOf(i));
    const p = project(0, PAGE.h * (0.2 + (0.6 * k) / Math.max(1, hitIdx.length - 1)), 30);
    return {x: PO.x + p.x, y: PO.y + p.y};
  };


  const cols = [230, 170, 90, 150];
  const colX = cols.reduce<number[]>((a, w, i) => [...a, (a[i - 1] ?? 18) + (i ? cols[i - 1] : 0)], []);

  return (
    <AbsoluteFill style={{...hatchBg, fontFamily: FONT, color: C.ink}}>
      {/* 1. 내역서 판 */}
      <div style={{position: 'absolute', left: SO.x, top: SO.y, transformStyle: 'preserve-3d', transformOrigin: '0 0',
        transform: `${isoTransform} translateZ(${(1 - sheetIn) * 80}px)`, opacity: sheetIn * sheetDim}}>
        <Slab w={SHEET.w} h={SHEET.h}>
          <div style={{height: 40, borderBottom: `1px solid ${C.line}`, display: 'flex', alignItems: 'center', padding: '0 18px',
            fontFamily: MONO, fontSize: 15, color: C.muted, gap: 14}}>
            <span style={{width: 10, height: 10, borderRadius: 5, border: `1px solid ${C.line}`}} />
            example_boq.xlsx · 내역(건)
          </div>
          <div style={{position: 'absolute', top: 40, left: 0, right: 0, height: 36, borderBottom: `1px solid ${C.lineDark}`,
            fontSize: 16, color: C.muted}}>
            {['품명', '규격', '단위', '수량'].map((h, i) => (
              <div key={h} style={{position: 'absolute', left: colX[i], top: 8}}>{h}</div>
            ))}
          </div>
          {SHEET_ROWS.map((r, i) => {
            const shown = Math.min(1, Math.max(0, rowsDrawn - i));
            const hot = rowHot(i);
            const gone = rowFly(i);
            return (
              <div key={i} style={{position: 'absolute', top: SHEET.head + i * SHEET.row, left: 0, right: 0, height: SHEET.row,
                borderBottom: `1px solid ${C.line}`, opacity: shown, fontSize: 17,
                background: hot ? `rgba(219,232,253,${hot * (1 - gone * 0.6)})` : 'transparent'}}>
                {[r.name, r.spec, r.unit, fmt(r.qty)].map((v, j) => (
                  <div key={j} style={{position: 'absolute', left: colX[j], top: 5, whiteSpace: 'nowrap', maxWidth: cols[j] - 10,
                    overflow: 'hidden', color: hot > 0.5 && j === 0 ? C.blue : C.ink, textAlign: j === 3 ? 'right' : 'left',
                    width: j === 3 ? cols[j] - 20 : undefined}}>{v}</div>
                ))}
              </div>
            );
          })}
        </Slab>
      </div>

      {/* 2. 파란 선과 이동하는 자재 칩 */}
      <svg style={{position: 'absolute', inset: 0, overflow: 'visible'}} width={width} height={height}>
        {hitIdx.map((i) => {
          const a = sheetEdge(i);
          const t = rowHot(i);
          const b = stackIn(i);
          const mid = {x: a.x + 36 + hitIdx.indexOf(i) * 3, y: a.y};
          const len = Math.hypot(mid.x - a.x, 0) + Math.hypot(b.x - mid.x, b.y - mid.y);
          const vis = t * (frame < 470 ? 1 : interpolate(frame, [470, 500], [1, 0.25], clamp));
          return (
            <path key={i} d={`M ${a.x} ${a.y} L ${mid.x} ${a.y} L ${b.x} ${b.y}`} fill="none" stroke={C.blueLine}
              strokeWidth={1} strokeDasharray={len} strokeDashoffset={len * (1 - Math.min(1, rowFly(i) * 1.4 + t * 0.35))}
              opacity={vis} />
          );
        })}
      </svg>
      {hitIdx.map((i) => {
        const f = rowFly(i);
        if (f <= 0 || f >= 1) return null;
        const a = sheetEdge(i);
        const b = stackIn(i);
        const mid = {x: a.x + 36 + hitIdx.indexOf(i) * 3, y: a.y};
        const p = f < 0.5 ? {x: a.x + (mid.x - a.x) * f * 2, y: a.y} : {x: mid.x + (b.x - mid.x) * (f - 0.5) * 2, y: mid.y + (b.y - mid.y) * (f - 0.5) * 2};
        const r = SHEET_ROWS[i];
        return (
          <div key={i} style={{position: 'absolute', left: p.x - 8, top: p.y - 15, padding: '5px 10px', borderRadius: 6,
            background: C.blueSoft, border: `1px solid ${C.blue}`, fontSize: 15, color: C.ink, whiteSpace: 'nowrap',
            opacity: interpolate(f, [0, 0.1, 0.85, 1], [0, 1, 1, 0])}}>
            {r.material} <span style={{fontFamily: MONO, color: C.blue, fontSize: 13}}>{r.spec}</span>
          </div>
        );
      })}

      {/* 3. 계획서 쪽 더미 */}
      <div style={{position: 'absolute', left: PO.x, top: PO.y, transformStyle: 'preserve-3d', transformOrigin: '0 0', transform: isoTransform}}>
        {/* 받침 판 */}
        <div style={{position: 'absolute', left: -30, top: -30, width: PAGE.w + 60, height: PAGE.h + 60, borderRadius: 14,
          border: `1px dashed ${C.line}`, opacity: interpolate(frame, [200, 240], [0, 1], clamp)}} />
        {stack.map((src, i) => {
          const t = interpolate(frame, [dropAt(i), dropAt(i) + 24], [0, 1], {...clamp, easing: ease});
          if (t <= 0) return null;
          const top = i === stack.length - 1;
          const z = 6 + i * 14 + (1 - t) * 160;
          return (
            <div key={src} style={{position: 'absolute', width: PAGE.w, height: PAGE.h, background: C.paper,
              border: `1px solid ${top ? C.blue : C.lineDark}`, borderRadius: 3, transform: `translate(${i * 4}px, ${-i * 4}px) translateZ(${z}px)`,
              opacity: t, overflow: 'hidden', boxShadow: top ? `0 0 0 3px ${C.blueSoft}` : 'none'}}>
              <Img src={staticFile(src)} style={{width: '100%', height: '100%'}} />
              {top && (
                <>
                  {/* 아직 채워지지 않은 줄을 흰 판으로 덮고, 경계에 파란 주사선 */}
                  <div style={{position: 'absolute', left: '7%', right: '5%', top: `${24 + fill * 62}%`, bottom: '13%',
                    background: C.paper, opacity: fill >= 1 ? 0 : 1}} />
                  <div style={{position: 'absolute', left: '7%', right: '5%', top: `${24 + fill * 62}%`, height: 2,
                    background: C.blue, opacity: fill > 0 && fill < 1 ? 1 : 0}} />
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* 라벨(2D, 투영 좌표에 붙임) */}
      {(() => {
        const p = project(SHEET.w * 0.18, 0, 0);
        return <Label x={SO.x + p.x} y={SO.y + p.y} dx={-30} dy={-80} text="BOQ · XLSX" opacity={sheetIn * sheetDim} />;
      })()}
      {(() => {
        const top = stack.length - 1;
        const p = project(PAGE.w * 0.6 + top * 4, -top * 4, 6 + top * 14);
        const o = interpolate(frame, [dropAt(top) + 20, dropAt(top) + 40], [0, 1], clamp);
        return <Label x={PO.x + p.x} y={PO.y + p.y} dx={40} dy={-90} blue
          text={`8.11 품질시험계획 · ${rowsCount}/${data.table_rows.length}행`} opacity={o} />;
      })()}
      {(() => {
        const p = project(PAGE.w * 0.55, PAGE.h, 6);
        const o = interpolate(frame, [260, 290], [0, 1], clamp) * (1 - endIn * 0.6);
        return <Label x={PO.x + p.x} y={PO.y + p.y} dx={60} dy={90} text="표지 · 목차 · 흐름표 · 양식 · 8.11" opacity={o} />;
      })()}

      {/* 4. 끝 글 */}
      <div style={{position: 'absolute', left: wide ? width * 0.06 : width * 0.08, bottom: wide ? height * 0.1 : height * 0.06,
        opacity: endIn, transform: `translateY(${(1 - endIn) * 16}px)`}}>
        <div style={{fontFamily: MONO, fontSize: 16, letterSpacing: 1.5, color: C.blue, marginBottom: 10}}>QUALITY MANAGEMENT PLAN · HWPX</div>
        <div style={{fontSize: wide ? 56 : 52, fontWeight: 600, letterSpacing: -1}}>
          품질관리계획서.hwpx <span style={{color: C.muted, fontWeight: 400}}>·</span> {data.pages}쪽
        </div>
        <div style={{marginTop: 14, fontSize: 22, color: C.muted, letterSpacing: 0.5}}>단번</div>
      </div>
    </AbsoluteFill>
  );
};
