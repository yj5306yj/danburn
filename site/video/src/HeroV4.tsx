import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import 'pretendard/dist/web/static/pretendard.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import data from '../public/data.json';
import {C, FONT, MONO, hatchBg} from './theme';

// v4(impeccable critique L8-C1 반영, 사용자 결정 우선):
// - 정면 유지(아이소 기각 — 사용자 "눕지 말고 명확하게"). 판의 가짜 두께 외곽선 제거.
// - 파랑 절제: 지금 날아가는 행만 채우고, 지나간 행은 왼쪽 3px 눈금 + 검정 품명. 대조 장면 파란 면은 8.11 머리 한 줄 + 결과 2,950 만.
//   포커스링 halo·펄스 없음. 파란 글자는 blueInk(#1d4ed8).
// - 칩이 빈 계획서 줄에 도착해 그 줄을 "콘크리트 25-24-150"으로 바꿔 쓴다. 선은 도착 뒤 물러난다.
// - 16초(480f)로 단축, 끝 → 처음 루프 페이드. 끝 장면은 제목·명령 없이 쪽 더미 + 지시선 콜아웃 3개 + 한 줄 "도급내역서 → 품질관리계획서.hwpx".
// - 작은 글자 키움(행 번호·합성 예제 pill·노무 · 제외), 행 표기 통일("지급 8 · 상부공사"), 4:5 는 가장자리 선 없이 눈금·큰 매칭 라벨·줄 바꿔 쓰기.
//  A 0–45 판·빈 쪽 · B 40–158 칩 → 쪽 줄 · C 158–206 쪽 3장 · C2 206–250 8.11 채우기
//  D 252–384 대조 · E 384–465 콜아웃 · 루프 페이드 465–480
export const DURATION_V4 = 480;

type SheetRow = {sheet: string; row: number; part: string; name: string; spec: string; unit: string; qty: number; material: string};
type Crop = {file: string; x0: number; y0: number; x1: number; y1: number; hl: {x: number; y: number; w: number; h: number}};
const SHEET_ROWS = data.sheet as SheetRow[];
const CMP = data.compare as {
  spec: string; item: string; total: number; unit: string; page: number;
  sources: SheetRow[]; tests: {test: string; freq: string; basis: string; count: number}[];
  crop_narrow: Crop; crop_a: Crop; crop_b: Crop;
};
const STACK = [data.shots.cover, data.shots.flow, data.shots.table] as string[];
const PAGE_TITLES = ['표지', '업무 흐름표 · 1~10장 33절', '8.11 시험계획표'];

const fmt = (n: number) => n.toLocaleString('ko-KR', {maximumFractionDigits: 2});
const unitK = (u: string) => ({M3: '㎥', M2: '㎡', TON: 'ton', M: 'm'} as Record<string, string>)[u] ?? u;
const sheetShort = (s: string) => s.replace('(건)', '');
const rowTag = (r: SheetRow) => `${sheetShort(r.sheet)} ${r.row}`;
const ease = Easing.bezier(0.2, 0.7, 0.2, 1);
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

function layout(wide: boolean) {
  return wide
    ? {
        sheet: {x: 64, y: 118, w: 930, head: 110, row: 56, font: 34, rowNo: 22, labor: 24},
        cols: [118, 310, 210, 92, 170],
        slot: {x: 1120, y: 92, w: 636, h: 900, pad: 56, title: 46, line0: 190, gap: 44, lineFont: 22, lines: 14},
        label: 26, pill: 22, callout: 36,
      }
    : {
        sheet: {x: 36, y: 96, w: 1008, head: 104, row: 48, font: 30, rowNo: 26, labor: 28},
        cols: [118, 330, 230, 100, 186],
        slot: {x: 690, y: 852, w: 336, h: 475, pad: 26, title: 30, line0: 104, gap: 34, lineFont: 16, lines: 10},
        label: 30, pill: 26, callout: 34,
      };
}

const Label: React.FC<{x: number; y: number; text: string; blue?: boolean; opacity?: number; size?: number; children?: React.ReactNode}> =
  ({x, y, text, blue, opacity = 1, size = 24, children}) => (
    <div style={{position: 'absolute', left: x, top: y, opacity, fontFamily: MONO, fontSize: size, letterSpacing: 1.2, whiteSpace: 'nowrap',
      color: blue ? C.blueInk : C.muted, display: 'flex', alignItems: 'center', gap: 10}}>
      <span style={{width: 9, height: 9, border: `1px solid ${blue ? C.blue : C.lineDark}`, background: C.paper}} />
      {text}
      {children}
    </div>
  );

export const HeroV4: React.FC = () => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const wide = width / height > 1.2;
  const L = layout(wide);
  const S = L.sheet;
  const slot = L.slot;
  const colX = L.cols.reduce<number[]>((a, w, i) => [...a, i ? a[i - 1] + L.cols[i - 1] : 22], []);

  const loop = interpolate(frame, [465, 480], [1, 0], clamp); // 끝 → 처음(빈 바탕) 이음새 없이
  // A
  const inA = interpolate(frame, [0, 20], [0, 1], {...clamp, easing: ease});
  const rowIn = (i: number) => interpolate(frame, [6 + i * 3, 16 + i * 3], [0, 1], {...clamp, easing: ease});
  // 장면 전환(완전히 사라진 뒤 다음)
  const toCmp = interpolate(frame, [252, 266], [0, 1], {...clamp, easing: ease});
  const cmpIn = interpolate(frame, [268, 288], [0, 1], {...clamp, easing: ease});
  const cmpOut = 1 - interpolate(frame, [370, 384], [0, 1], clamp);
  const toEnd = interpolate(frame, [384, 404], [0, 1], {...clamp, easing: ease});

  // B: 한 행씩(칩 간격 9f, 비행 32f)
  const hitIdx = SHEET_ROWS.map((r, i) => (r.material ? i : -1)).filter((i) => i >= 0);
  const kOf = (i: number) => hitIdx.indexOf(i);
  const start = (i: number) => 40 + kOf(i) * 9;
  const flyT = (i: number) => (kOf(i) < 0 ? 0 : interpolate(frame, [start(i) + 4, start(i) + 36], [0, 1], {...clamp, easing: ease}));
  const hot = (i: number) => (kOf(i) < 0 ? 0 : interpolate(frame, [start(i), start(i) + 5, start(i) + 24, start(i) + 34], [0, 1, 1, 0], clamp)); // 날아가는 동안만
  const done = (i: number) => kOf(i) >= 0 && frame >= start(i) + 36;
  const arrived = (i: number) => interpolate(frame, [start(i) + 36, start(i) + 42], [0, 1], clamp);
  const lineBack = (i: number) => interpolate(frame, [start(i) + 36, start(i) + 56], [1, 0.25], clamp);
  const laborIn = interpolate(frame, [44, 60], [0, 1], clamp);

  const rowY = (i: number) => S.y + S.head + (i + 0.5) * S.row;
  const lineY = (k: number) => slot.y + slot.line0 + k * slot.gap;
  const route = (i: number) => {
    const a = {x: S.x + S.w, y: rowY(i)};
    const k = kOf(i);
    const b = {x: slot.x + slot.pad, y: lineY(k)};
    return [a, {x: a.x + 34 + k * 5, y: a.y}, {x: slot.x - 18, y: b.y}, b];
  };
  const along = (pts: {x: number; y: number}[], t: number) => {
    const seg = pts.slice(1).map((p, j) => Math.hypot(p.x - pts[j].x, p.y - pts[j].y));
    const total = seg.reduce((x, y) => x + y, 0);
    let d = t * total;
    for (let j = 0; j < seg.length; j++) {
      if (d <= seg[j] || j === seg.length - 1) {
        const u = seg[j] ? Math.min(1, d / seg[j]) : 0;
        return {x: pts[j].x + (pts[j + 1].x - pts[j].x) * u, y: pts[j].y + (pts[j + 1].y - pts[j].y) * u, total};
      }
      d -= seg[j];
    }
    return {...pts[pts.length - 1], total};
  };

  // C·C2
  const dropAt = (i: number) => 158 + i * 16;
  const pageIdx = STACK.reduce((acc, _, i) => (frame >= dropAt(i) ? i : acc), -1);
  const fill = interpolate(frame, [206, 250], [0, 1], clamp);
  const scanY = 0.235 + fill * 0.625;
  const nRows = Math.round(fill * data.table_rows.length);
  // D
  const sumIn = interpolate(frame, [296, 310], [0, 1], clamp);
  const sumPop = interpolate(frame, [296, 308], [1.04, 1], clamp);
  // E
  const endIn = interpolate(frame, [396, 420], [0, 1], {...clamp, easing: ease});
  const calloutIn = (k: number) => interpolate(frame, [404 + k * 8, 420 + k * 8], [0, 1], {...clamp, easing: ease});

  const stageOpacity = Math.max(1 - toCmp, toEnd); // 끝 장면에서 쪽 더미를 주인공으로(불투명)
  const stackOffset = (i: number) => ({x: i * (wide ? 14 : 10), y: i * (wide ? 8 : 6)});
  const liveRow = hitIdx.filter((i) => flyT(i) > 0 && flyT(i) < 1).pop() ?? -1;

  return (
    <AbsoluteFill style={{...hatchBg, fontFamily: FONT, color: C.ink, overflow: 'hidden'}}>
      <div style={{position: 'absolute', inset: 0, opacity: loop}}>
        {/* ── 판 + 쪽 무대 ── */}
        <div style={{position: 'absolute', inset: 0, opacity: stageOpacity}}>
          {/* 판: 도급내역서(정면, 가짜 두께 없음) — 끝 장면에서는 숨김 */}
          <div style={{opacity: 1 - toEnd}}>
            <Label x={S.x + 4} y={S.y - 50} text="도급내역서.xlsx" opacity={inA} size={L.label}>
              <span style={{marginLeft: 8, padding: '2px 10px', border: `1px solid ${C.lineDark}`, borderRadius: 4, fontSize: L.pill, color: C.muted}}>합성 예제</span>
            </Label>
            <div style={{position: 'absolute', left: S.x, top: S.y + (1 - inA) * 24, width: S.w, height: S.head + SHEET_ROWS.length * S.row + 12,
              borderRadius: 10, border: `1px solid ${C.lineDark}`, background: C.paper, overflow: 'hidden', opacity: inA}}>
              <div style={{height: 52, borderBottom: `1px solid ${C.line}`, display: 'flex', alignItems: 'center', padding: '0 22px',
                fontSize: 24, color: C.muted, whiteSpace: 'nowrap'}}>
                {data.block} · 건축 · 철근콘크리트공사 — 실제 행 전부
              </div>
              <div style={{position: 'absolute', top: 52, left: 0, right: 0, height: S.head - 52, borderBottom: `1px solid ${C.lineDark}`, fontSize: 22, color: C.muted}}>
                {['시트·행', '품명', '규격', '단위', '수량'].map((h, i) => (
                  <div key={h} style={{position: 'absolute', left: colX[i], top: 16, width: L.cols[i] - 22, textAlign: i === 4 ? 'right' : 'left'}}>{h}</div>
                ))}
              </div>
              {SHEET_ROWS.map((r, i) => {
                const h = hot(i);
                const labor = !r.material;
                const tick = done(i);
                return (
                  <div key={i} style={{position: 'absolute', top: S.head + i * S.row, left: 0, right: 0, height: S.row, borderBottom: `1px solid ${C.line}`,
                    opacity: rowIn(i), fontSize: S.font, background: h ? `rgba(219,232,253,${h})` : 'transparent',
                    boxShadow: tick ? `inset 3px 0 0 ${C.blue}` : 'none'}}>
                    <div style={{position: 'absolute', left: colX[0], top: (S.row - S.rowNo * 1.3) / 2, fontFamily: MONO, fontSize: S.rowNo, color: C.muted, whiteSpace: 'nowrap'}}>
                      {rowTag(r)}
                    </div>
                    {[r.name, r.spec, unitK(r.unit), fmt(r.qty)].map((v, j) => (
                      <div key={j} style={{position: 'absolute', left: colX[j + 1], top: (S.row - S.font * 1.3) / 2, width: L.cols[j + 1] - 22,
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textAlign: j === 3 ? 'right' : 'left',
                        color: labor ? C.muted : C.ink, fontVariantNumeric: 'tabular-nums'}}>{v}</div>
                    ))}
                    {labor && (
                      <div style={{position: 'absolute', right: 12, top: (S.row - S.labor * 1.5) / 2, height: S.labor * 1.5, padding: '0 10px', display: 'flex',
                        alignItems: 'center', border: `1px solid ${C.lineDark}`, borderRadius: 6, background: C.paper, fontSize: S.labor, color: C.muted, opacity: laborIn}}>
                        노무 · 제외
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* 선(16:9 만): 날아가는 동안 그려지고 도착 뒤 물러난다 */}
          {wide && (
            <svg style={{position: 'absolute', left: 0, top: 0, overflow: 'visible', opacity: 1 - toEnd}} width={width} height={height}>
              {hitIdx.map((i) => {
                const pts = route(i);
                const len = along(pts, 1).total + 2;
                const drawn = Math.min(1, flyT(i) * 1.15);
                return <path key={i} d={'M ' + pts.map((p) => `${p.x} ${p.y}`).join(' L ')} fill="none" stroke={C.blueLine} strokeWidth={1.3}
                  strokeDasharray={len} strokeDashoffset={len * (1 - drawn)} opacity={lineBack(i)} />;
              })}
            </svg>
          )}

          {/* 쪽 자리: 빈 '품질관리계획서' 윤곽 — 칩이 도착한 줄을 바꿔 쓴다 */}
          <Label x={wide ? slot.x : S.x + 4} y={wide ? slot.y - 46 : slot.y + 24} blue={pageIdx >= 0}
            text={pageIdx < 0 ? '품질관리계획서.hwpx' : fill > 0 ? `8.11 시험계획표 · ${nRows}행 작성` : PAGE_TITLES[pageIdx]}
            opacity={inA * (1 - toEnd)} size={L.label} />
          <div style={{position: 'absolute', left: slot.x, top: slot.y, width: slot.w, height: slot.h, borderRadius: 4, border: `1px solid ${C.lineDark}`,
            background: C.paper, opacity: inA}}>
            <div style={{position: 'absolute', left: slot.pad, top: slot.pad + 10, fontSize: slot.title, fontWeight: 600, letterSpacing: -0.5}}>품질관리계획서</div>
            <div style={{position: 'absolute', left: slot.pad, right: slot.pad, top: slot.line0 - slot.gap * 0.9, height: 1, background: C.lineDark}} />
          </div>
          {Array.from({length: slot.lines}).map((_, k) => {
            const i = hitIdx[k];
            const got = i !== undefined ? arrived(i) : 0;
            const w0 = (slot.w - 2 * slot.pad) * (0.92 - (k % 3) * 0.14);
            const hint = k < 2 ? interpolate(frame, [14 + k * 12, 34 + k * 12], [0, 1], {...clamp, easing: ease}) * (1 - got) : 0; // 첫 2초 암시
            const r = i !== undefined ? SHEET_ROWS[i] : null;
            return (
              <div key={k} style={{position: 'absolute', left: slot.x + slot.pad, top: lineY(k), width: slot.w - 2 * slot.pad, opacity: inA}}>
                <div style={{position: 'absolute', left: 0, top: 0, height: 1, width: w0, background: got > 0.5 ? C.blue : C.line}} />
                {hint > 0 && <div style={{position: 'absolute', left: 0, top: -2, height: 4, borderRadius: 2, width: w0 * hint, background: C.blueLine}} />}
                {r && got > 0 && (
                  <div style={{position: 'absolute', left: 0, bottom: 4, fontFamily: MONO, fontSize: slot.lineFont, color: C.blueInk, whiteSpace: 'nowrap',
                    opacity: got, transform: `scale(${1.4 - 0.4 * got})`, transformOrigin: 'left bottom'}}>
                    {r.material} {r.spec}
                  </div>
                )}
              </div>
            );
          })}
          {/* 칩(16:9): 선을 따라 날아가 줄에 안착 */}
          {wide && hitIdx.map((i) => {
            const f = flyT(i);
            if (f <= 0.02 || arrived(i) >= 1) return null;
            const p = along(route(i), f);
            const r = SHEET_ROWS[i];
            const land = arrived(i);
            return (
              <div key={i} style={{position: 'absolute', left: p.x, top: p.y - 22, padding: '6px 14px', borderRadius: 8, background: C.blueSoft,
                border: `1px solid ${C.blue}`, fontSize: 27, whiteSpace: 'nowrap', transformOrigin: 'left center',
                transform: `translateX(${f < 1 ? -40 : 0}px) scale(${1 - 0.4 * land})`, opacity: 1 - land}}>
                {r.name} <span style={{color: C.muted}}>→</span> {r.material}{' '}
                <span style={{fontFamily: MONO, color: C.blueInk, fontSize: 22}}>{r.spec}</span>
              </div>
            );
          })}
          {/* 쪽 3장: 불투명하게 한 장씩 */}
          {STACK.map((src, i) => {
            const t = interpolate(frame, [dropAt(i), dropAt(i) + 14], [0, 1], {...clamp, easing: ease});
            if (t <= 0) return null;
            const o = stackOffset(i + 1);
            const isTable = i === STACK.length - 1;
            return (
              <div key={src} style={{position: 'absolute', left: slot.x + o.x + (1 - t) * 44, top: slot.y + o.y, width: slot.w, height: slot.h, opacity: t,
                borderRadius: 3, overflow: 'hidden', background: C.paper, border: `1px solid ${isTable && fill > 0 && fill < 1 ? C.blue : C.lineDark}`}}>
                <Img src={staticFile(src)} style={{width: '100%', height: '100%'}} />
                {isTable && (
                  <>
                    <div style={{position: 'absolute', left: '7%', right: '5%', top: `${scanY * 100}%`, bottom: '13%', background: C.paper,
                      opacity: frame < 206 ? 1 : fill >= 1 ? 0 : 1}} />
                    <div style={{position: 'absolute', left: '6%', right: '4%', top: `${scanY * 100}%`, height: 3, background: C.blue,
                      opacity: fill > 0 && fill < 1 ? 1 : 0}} />
                  </>
                )}
              </div>
            );
          })}
        </div>

        {/* 4:5: 칩 대신 지금 옮기는 매칭 한 줄을 판 아래 빈 곳에 크게 */}
        {!wide && liveRow >= 0 && (() => {
          const r = SHEET_ROWS[liveRow];
          return (
            <div style={{position: 'absolute', left: S.x + 4, top: slot.y + 96, width: slot.x - S.x - 40, opacity: 1 - toCmp}}>
              <div style={{fontFamily: MONO, fontSize: 26, color: C.muted, marginBottom: 10}}>{rowTag(r)} →</div>
              <div style={{fontSize: 36, lineHeight: 1.3, padding: '10px 16px', border: `1px solid ${C.blue}`, borderRadius: 8, background: C.blueSoft}}>
                {r.name} <span style={{color: C.muted}}>→</span> {r.material}{' '}
                <span style={{fontFamily: MONO, color: C.blueInk, fontSize: 32}}>{r.spec}</span>
              </div>
            </div>
          );
        })()}

        {/* ── D 대조: 실물 쪽 자르기가 주인공, 카드는 작게 ── */}
        <div style={{position: 'absolute', inset: 0, opacity: cmpIn * cmpOut}}>
          {(() => {
            const cr = CMP.crop_narrow;
            const cx = wide ? 64 : 36;
            const cw = wide ? width - 2 * 64 : width - 2 * 36;
            const ch = (cw * (cr.y1 - cr.y0)) / (cr.x1 - cr.x0);
            const cy = wide ? 470 : 520;
            const top = wide ? 118 : 96;
            const cardW = wide ? (width - 2 * 64 - 40) / 2 : width - 72;
            const ka = cw / (CMP.crop_a.x1 - CMP.crop_a.x0);
            const chA = ka * (CMP.crop_a.y1 - CMP.crop_a.y0);
            const cwB = ka * (CMP.crop_b.x1 - CMP.crop_b.x0);
            const hr = wide ? cr.hl : CMP.crop_a.hl;
            const hh = wide ? ch : chA;
            const hl = {x: cx + hr.x * cw, y: cy + hr.y * hh, w: hr.w * cw, h: hr.h * hh};
            const small = wide ? 26 : 28;
            return (
              <>
                {/* 원본: 엑셀 두 행(흰 카드) + 합계(검정, 결과만 파랑) */}
                <div style={{position: 'absolute', left: cx, top, width: cardW}}>
                  <Label x={0} y={-46} text={`도급내역서.xlsx · ${data.block}`} size={24} />
                  {CMP.sources.map((r, k) => (
                    <div key={k} style={{display: 'flex', alignItems: 'center', gap: 14, height: 56, padding: '0 16px', marginBottom: 8,
                      border: `1px solid ${C.lineDark}`, borderRadius: 8, background: C.paper, fontSize: small + 4, whiteSpace: 'nowrap'}}>
                      <span style={{fontFamily: MONO, fontSize: wide ? 22 : 24, color: C.muted, width: wide ? 250 : 270, flexShrink: 0}}>{rowTag(r)} · {r.part}</span>
                      <span>{r.name} <span style={{fontFamily: MONO, fontSize: small}}>{r.spec}</span></span>
                      <span style={{marginLeft: 'auto', fontWeight: 600, fontVariantNumeric: 'tabular-nums'}}>{fmt(r.qty)} {unitK(r.unit)}</span>
                    </div>
                  ))}
                  <div style={{marginTop: 10, fontSize: 44, fontWeight: 650, opacity: sumIn, whiteSpace: 'nowrap', transformOrigin: 'left center',
                    transform: `scale(${sumPop})`}}>
                    {CMP.sources.map((r) => fmt(r.qty)).join(' + ')} = <span style={{color: C.blueInk}}>{fmt(CMP.total)} {CMP.unit}</span>
                  </div>
                </div>
                {/* 결과 요약: 8.11 머리 한 줄만 파란 면 */}
                <div style={{position: 'absolute', left: wide ? cx + cardW + 40 : cx, top: wide ? top : top + 250, width: cardW, opacity: sumIn}}>
                  <Label x={0} y={-46} blue text={`8.11 시험계획표 · 계획서 ${CMP.page}쪽`} size={24} />
                  <div style={{border: `1px solid ${C.lineDark}`, borderRadius: 8, background: C.paper, overflow: 'hidden', fontSize: small, lineHeight: 1.5}}>
                    <div style={{display: 'flex', whiteSpace: 'nowrap', padding: '10px 16px', background: C.blueSoft, borderBottom: `1px solid ${C.blue}`}}>
                      <span>{CMP.item}</span>
                      <span style={{marginLeft: 'auto', fontWeight: 600, color: C.blueInk}}>{fmt(CMP.total)} {CMP.unit}</span>
                    </div>
                    <div style={{color: C.muted, fontSize: small - 2, padding: '8px 16px'}}>
                      {Array.from(new Set(CMP.tests.map((t) => t.count))).map((n) =>
                        `${CMP.tests.filter((t) => t.count === n).map((t) => t.test).join('·')} ${n}회`).join('  /  ')}
                    </div>
                  </div>
                </div>
                {/* 주인공: 실제 쪽 원문 자르기 + 수량 칸(1px 파란 테, 링 없음) */}
                <Label x={cx} y={cy - 46} blue text={wide ? `실제 쪽 — 품질관리계획서 ${CMP.page}쪽, 8.11 시험계획표 원문 그대로` : `실제 쪽 — 계획서 ${CMP.page}쪽 원문(둘로 나눔)`} size={24} />
                {wide ? (
                  <Img src={staticFile(cr.file)} style={{position: 'absolute', left: cx, top: cy, width: cw, height: ch, border: `1px solid ${C.lineDark}`,
                    borderRadius: 4, background: C.paper}} />
                ) : (
                  <>
                    <Img src={staticFile(CMP.crop_a.file)} style={{position: 'absolute', left: cx, top: cy, width: cw, height: chA,
                      border: `1px solid ${C.lineDark}`, borderRadius: 4, background: C.paper}} />
                    <div style={{position: 'absolute', left: cx, top: cy + chA + 10, fontFamily: MONO, fontSize: 24, color: C.muted}}>이어서 →</div>
                    <Img src={staticFile(CMP.crop_b.file)} style={{position: 'absolute', left: cx, top: cy + chA + 48, width: cwB, height: chA,
                      border: `1px solid ${C.lineDark}`, borderRadius: 4, background: C.paper}} />
                  </>
                )}
                <div style={{position: 'absolute', left: hl.x, top: hl.y, width: hl.w, height: hl.h, border: `2px solid ${C.blue}`, borderRadius: 6, opacity: sumIn}} />
                {wide && (
                  <svg style={{position: 'absolute', left: 0, top: 0, overflow: 'visible', opacity: sumIn}} width={width} height={height}>
                    <path d={`M ${cx + 560} ${top + 2 * 64 + 34} L ${hl.x + hl.w / 2} ${top + 2 * 64 + 34} L ${hl.x + hl.w / 2} ${hl.y}`}
                      fill="none" stroke={C.blue} strokeWidth={1.3} />
                  </svg>
                )}
              </>
            );
          })()}
        </div>

        {/* ── E 끝: 쪽 더미(주인공) + 지시선 콜아웃 3개 + 사실 한 줄 ── */}
        {(() => {
          const topPage = stackOffset(STACK.length);
          const px = slot.x + topPage.x;
          const py = slot.y + topPage.y;
          const facts = [
            // v4.1: 머리말 한국어. 값은 React 노드 — 기준 고시 번호는 한 덩어리로(줄바꿈 금지)
            {k: '서식', v: <>양식 {data.forms}종 · 1~10장 흐름표</>, at: 0.14},
            {k: '8.11', v: <>시험계획표 {data.table_rows.length}행 · <span style={{whiteSpace: 'nowrap'}}>고시 {data.basis_no.replace('-', '\u2011')}</span></>, at: 0.46},
            {k: '한글 파일', v: <>품질관리계획서.hwpx · {data.pages}쪽</>, at: 0.78},
          ];
          const lx = wide ? 120 : 36;
          return (
            <div style={{position: 'absolute', inset: 0, opacity: endIn}}>
              <div style={{position: 'absolute', left: lx, top: wide ? 150 : slot.y - 210, fontSize: 40, fontWeight: 600, letterSpacing: -0.6, lineHeight: 1.3,
                whiteSpace: wide ? 'nowrap' : 'normal', wordBreak: 'keep-all', width: wide ? 'auto' : width - 2 * lx}}>
                도급내역서를 넣으면 <span style={{whiteSpace: 'nowrap'}}>품질관리계획서.hwpx가</span> 만들어집니다
              </div>
              <svg style={{position: 'absolute', left: 0, top: 0, overflow: 'visible'}} width={width} height={height}>
                {facts.map((f, k) => {
                  const ty = py + slot.h * f.at;
                  const tx = px;
                  const ly = wide ? 330 + k * 190 : ty;          // 4:5: 라벨을 쪽 높이에 맞춰 수평 지시선
                  const ex = wide ? 960 : px - 70;
                  return (
                    <g key={k} opacity={calloutIn(k)}>
                      <path d={wide ? `M ${ex} ${ly} L ${tx - 60} ${ly} L ${tx} ${ty}` : `M ${ex} ${ly} L ${tx} ${ty}`}
                        fill="none" stroke={C.lineDark} strokeWidth={1} />
                      <rect x={tx - 4} y={ty - 4} width={8} height={8} fill={C.paper} stroke={C.lineDark} strokeWidth={1} />
                    </g>
                  );
                })}
              </svg>
              {facts.map((f, k) => {
                const ly = wide ? 330 + k * 190 : py + slot.h * f.at;
                return (
                  <div key={k} style={{position: 'absolute', left: lx, top: wide ? ly - 22 : ly - 42, opacity: calloutIn(k), fontFamily: MONO, fontSize: L.callout,
                    letterSpacing: 0.6, color: C.muted, whiteSpace: wide ? 'nowrap' : 'normal', wordBreak: 'keep-all', lineHeight: 1.35,
                    width: wide ? 'auto' : px - lx - 40}}>
                    {f.k} <span style={{color: C.lineDark}}>·</span> <span style={{color: C.ink}}>{f.v}</span>
                  </div>
                );
              })}
            </div>
          );
        })()}
      </div>
    </AbsoluteFill>
  );
};
