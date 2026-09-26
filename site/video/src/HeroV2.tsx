import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import 'pretendard/dist/web/static/pretendard.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import data from '../public/data.json';
import {C, FONT, MONO, hatchBg} from './theme';

// v2(독립 리뷰 shower·hate 반영): 화면의 엑셀 행과 8.11 숫자가 1:1 로 설명되게.
// - 판 = 나동 건축 철근콘크리트공사의 실제 행 전부(12행, 시트·행 번호 그대로). 줄이던 중복 제거를 없앴다.
// - 대조 장면: 지급(건) 8행 2,000 + 14행 950 = 2,950 ↔ 8.11 콘크리트(25-24-150) 2,950 과 횟수(계획서.json 값)
// - 첫 프레임부터 오른쪽에 빈 '품질관리계획서' 쪽 윤곽, 쪽은 불투명하게 한 장씩, 칩은 한 번에 3~4개
// - 끝: 결과 설명 한 줄 + 핵심 3가지(실제 예제 값) + "단번 · danburn start"
// 글자 크기는 랜딩 표시 폭(16:9 → 약 900px, 4:5 → 390px)에서 핵심 글자가 14px·10px 이상이 되게 잡았다.
//  A 0–90 판·빈 쪽 · B 80–280 걸린 행 → 칩 · C 280–380 쪽 3장 · C2 380–450 8.11 채우기
//  D 450–560 대조 · E 560–660 끝(22초)
export const DURATION_V2 = 660;

type SheetRow = {sheet: string; row: number; part: string; name: string; spec: string; unit: string; qty: number; material: string};
const SHEET_ROWS = data.sheet as SheetRow[];
const CMP = data.compare as {
  spec: string; item: string; total: number; unit: string; page: number;
  sources: SheetRow[]; tests: {test: string; freq: string; basis: string; count: number}[];
  crop: {file: string; x0: number; y0: number; x1: number; y1: number};
};
const STACK = [data.shots.cover, data.shots.flow, data.shots.table] as string[];
const PAGE_TITLES = ['표지', '업무 흐름표 · 1~10장 33절', '8.11 시험계획표'];

const fmt = (n: number) => n.toLocaleString('ko-KR', {maximumFractionDigits: 2});
const unitK = (u: string) => ({M3: '㎥', M2: '㎡', TON: 'ton', M: 'm'} as Record<string, string>)[u] ?? u;
const ease = Easing.bezier(0.2, 0.7, 0.2, 1);
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

function layout(wide: boolean) {
  return wide
    ? {
        W: 1920, H: 1080,
        sheet: {x: 64, y: 118, w: 930, head: 118, row: 56, font: 31},
        cols: [118, 300, 210, 100, 170], // 시트·행 | 품명 | 규격 | 단위 | 수량
        slot: {x: 1120, y: 92, w: 636, h: 900},
        chipFont: 27,
        cmpL: {x: 64, y: 250, w: 900}, cmpR: {x: 1010, y: 190, w: 850},
        end: {x: 96, y: 300, head: 62, fact: 34, small: 28},
      }
    : {
        W: 1080, H: 1350,
        sheet: {x: 36, y: 96, w: 1008, head: 110, row: 48, font: 30},
        cols: [118, 330, 230, 100, 186],
        slot: {x: 690, y: 852, w: 336, h: 475},
        chipFont: 28,
        cmpL: {x: 36, y: 96, w: 1008}, cmpR: {x: 36, y: 640, w: 1008},
        end: {x: 48, y: 150, head: 60, fact: 32, small: 30},
      };
}

const Card: React.FC<{x: number; y: number; w: number; h: number; blue?: boolean; radius?: number; style?: React.CSSProperties; children?: React.ReactNode}> =
  ({x, y, w, h, blue, radius = 10, style, children}) => (
    <div style={{position: 'absolute', left: x, top: y, width: w, height: h, ...style}}>
      {[10, 5].map((o) => (
        <div key={o} style={{position: 'absolute', left: o, top: o, width: w, height: h, borderRadius: radius, border: `1px solid ${C.line}`, background: C.bg}} />
      ))}
      <div style={{position: 'absolute', inset: 0, borderRadius: radius, border: `1px solid ${blue ? C.blue : C.lineDark}`, background: C.paper,
        overflow: 'hidden', boxShadow: blue ? `0 0 0 4px ${C.blueSoft}` : 'none'}}>{children}</div>
    </div>
  );

const Label: React.FC<{x: number; y: number; text: string; blue?: boolean; opacity?: number; size?: number}> = ({x, y, text, blue, opacity = 1, size = 24}) => (
  <div style={{position: 'absolute', left: x, top: y, opacity, fontFamily: MONO, fontSize: size, letterSpacing: 1.2, whiteSpace: 'nowrap',
    color: blue ? C.blue : C.muted, display: 'flex', alignItems: 'center', gap: 10}}>
    <span style={{width: 9, height: 9, border: `1px solid ${blue ? C.blue : C.lineDark}`, background: C.paper}} />
    {text}
  </div>
);

export const HeroV2: React.FC = () => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const wide = width / height > 1.2;
  const L = layout(wide);
  const S = L.sheet;
  const colX = L.cols.reduce<number[]>((a, w, i) => [...a, i ? a[i - 1] + L.cols[i - 1] : 22], []);

  // A 판 + 빈 쪽 윤곽
  const inA = interpolate(frame, [0, 24], [0, 1], {...clamp, easing: ease});
  const rowsDrawn = interpolate(frame, [10, 80], [0, SHEET_ROWS.length], clamp);
  // D 대조 장면 동안 판·쪽을 치운다
  const toCmp = interpolate(frame, [440, 468], [0, 1], {...clamp, easing: ease});
  const toEnd = interpolate(frame, [556, 586], [0, 1], {...clamp, easing: ease});
  const stageOpacity = (1 - toCmp) + toEnd * 0.3; // 끝 장면에서 쪽 더미를 배경으로 다시

  // B 걸린 행 → 칩(한 번에 3~4개)
  const hitIdx = SHEET_ROWS.map((r, i) => (r.material ? i : -1)).filter((i) => i >= 0);
  const hot = (i: number) => {
    const k = hitIdx.indexOf(i);
    return k < 0 ? 0 : interpolate(frame, [86 + k * 14, 96 + k * 14], [0, 1], clamp);
  };
  const flyT = (i: number) => {
    const k = hitIdx.indexOf(i);
    return k < 0 ? 0 : interpolate(frame, [100 + k * 16, 150 + k * 16], [0, 1], {...clamp, easing: ease});
  };
  const laborIn = interpolate(frame, [96, 116], [0, 1], clamp);
  const rowY = (i: number) => S.y + S.head + (i + 0.5) * S.row;
  // 16:9: 행 높이 그대로 수평으로(칩이 서로 가로지르지 않게). 4:5: 쪽 자리가 아래라 쪽 윗변 쪽으로 모은다
  const target = (i: number) => {
    const k = Math.max(0, hitIdx.indexOf(i));
    return wide
      ? {x: L.slot.x - 6, y: Math.min(Math.max(rowY(i), L.slot.y + 40), L.slot.y + L.slot.h - 40)}
      : {x: L.slot.x + 30 + (k * (L.slot.w - 60)) / Math.max(1, hitIdx.length - 1), y: L.slot.y - 6};
  };

  // 선 경로: 16:9 는 행 끝 → 조금 오른쪽 → 쪽 왼쪽. 4:5 는 오른쪽 여백을 타고 내려가 판 아래 틈으로(판을 가로지르지 않게)
  const route = (i: number): {x: number; y: number}[] => {
    const a = {x: S.x + S.w, y: rowY(i)};
    const b = target(i);
    if (wide) return [a, {x: a.x + 30 + hitIdx.indexOf(i) * 6, y: a.y}, b];
    const k = hitIdx.indexOf(i);
    const rx = width - 10 - k * 2;
    const gy = L.slot.y - 12 - k * 1.5;
    return [a, {x: rx, y: a.y}, {x: rx, y: gy}, {x: b.x, y: gy}, b];
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

  // C 쪽 3장(불투명, 한 장씩)
  const dropAt = (i: number) => 284 + i * 34;
  const pageIdx = STACK.reduce((acc, _, i) => (frame >= dropAt(i) ? i : acc), -1);
  // C2 8.11 채우기
  const fill = interpolate(frame, [380, 440], [0, 1], clamp);
  const scanY = 0.235 + fill * 0.625;
  const nRows = Math.round(fill * data.table_rows.length);

  // D 대조
  const cmpIn = interpolate(frame, [452, 480], [0, 1], {...clamp, easing: ease});
  const cmpOut = 1 - toEnd;
  const sumIn = interpolate(frame, [492, 512], [0, 1], clamp);
  const pulse = interpolate(frame % 40, [0, 20, 40], [0.55, 1, 0.55]);

  const endIn = interpolate(frame, [572, 604], [0, 1], {...clamp, easing: ease});
  const factIn = (k: number) => interpolate(frame, [596 + k * 10, 614 + k * 10], [0, 1], {...clamp, easing: ease});

  const slot = L.slot;
  const stackOffset = (i: number) => ({x: i * (wide ? 14 : 10), y: i * (wide ? 8 : 6)});

  return (
    <AbsoluteFill style={{...hatchBg, fontFamily: FONT, color: C.ink, overflow: 'hidden'}}>
      <div style={{position: 'absolute', inset: 0, opacity: Math.min(1, stageOpacity), transform: `translateX(${toEnd * (wide ? 260 : 0)}px)`}}>
        {/* 판: 도급내역서 */}
        <div style={{opacity: 1 - toEnd}}>
          <Label x={S.x + 4} y={S.y - 48} text="도급내역서.xlsx" opacity={inA} size={wide ? 26 : 28} />
          <Card x={S.x} y={S.y + (1 - inA) * 30} w={S.w} h={S.head + SHEET_ROWS.length * S.row + 14} style={{opacity: inA}}>
            <div style={{height: 54, borderBottom: `1px solid ${C.line}`, display: 'flex', alignItems: 'center', padding: '0 22px',
              fontSize: 22, color: C.muted, gap: 12, whiteSpace: 'nowrap'}}>
              {data.block} · 건축 · 철근콘크리트공사 — 실제 행 전부 <span style={{fontFamily: MONO, fontSize: 18}}>(합성 예제)</span>
            </div>
            <div style={{position: 'absolute', top: 54, left: 0, right: 0, height: S.head - 54, borderBottom: `1px solid ${C.lineDark}`, fontSize: 22, color: C.muted}}>
              {['시트·행', '품명', '규격', '단위', '수량'].map((h, i) => (
                <div key={h} style={{position: 'absolute', left: colX[i], top: 18, width: L.cols[i] - 22, textAlign: i === 4 ? 'right' : 'left'}}>{h}</div>
              ))}
            </div>
            {SHEET_ROWS.map((r, i) => {
              const shown = Math.min(1, Math.max(0, rowsDrawn - i));
              const h = hot(i);
              const labor = !r.material;
              return (
                <div key={i} style={{position: 'absolute', top: S.head + i * S.row, left: 0, right: 0, height: S.row, borderBottom: `1px solid ${C.line}`,
                  opacity: shown, fontSize: S.font, background: h ? `rgba(219,232,253,${h})` : 'transparent'}}>
                  <div style={{position: 'absolute', left: colX[0], top: (S.row - 22) / 2, fontFamily: MONO, fontSize: 18, color: C.muted, whiteSpace: 'nowrap'}}>
                    {r.sheet.replace('(건)', '')} {r.row}
                  </div>
                  {[r.name, r.spec, unitK(r.unit), fmt(r.qty)].map((v, j) => (
                    <div key={j} style={{position: 'absolute', left: colX[j + 1], top: (S.row - S.font * 1.3) / 2, width: L.cols[j + 1] - 22,
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textAlign: j === 3 ? 'right' : 'left',
                      color: labor ? C.muted : h > 0.5 && j === 0 ? C.blue : C.ink, fontVariantNumeric: 'tabular-nums'}}>{v}</div>
                  ))}
                  {labor && (
                    <div style={{position: 'absolute', right: 14, top: (S.row - 32) / 2, height: 32, padding: '0 10px', display: 'flex', alignItems: 'center',
                      border: `1px solid ${C.lineDark}`, borderRadius: 6, background: C.paper, fontSize: 20, color: C.muted, opacity: laborIn}}>
                      노무 · 제외
                    </div>
                  )}
                </div>
              );
            })}
          </Card>
        </div>

        {/* 파란 선 */}
        <svg style={{position: 'absolute', left: 0, top: 0, overflow: 'visible', opacity: 1 - toEnd}} width={width} height={height}>
          {hitIdx.map((i) => {
            const pts = route(i);
            const len = along(pts, 1).total + 2;
            const drawn = Math.min(1, flyT(i) * 1.3);
            return <path key={i} d={'M ' + pts.map((p) => `${p.x} ${p.y}`).join(' L ')} fill="none" stroke={C.blueLine} strokeWidth={1.4}
              strokeDasharray={len} strokeDashoffset={len * (1 - drawn)} />;
          })}
        </svg>
        {/* 쪽 자리: 첫 프레임부터 빈 '품질관리계획서' 윤곽 → 실제 쪽이 한 장씩 불투명하게 덮는다 */}
        <Label x={wide ? slot.x : S.x + 4} y={wide ? slot.y - 44 : slot.y + 24} blue={pageIdx >= 0}
          text={pageIdx < 0 ? '품질관리계획서.hwpx' : fill > 0 ? `8.11 시험계획표 · ${nRows}행 작성` : PAGE_TITLES[pageIdx]}
          opacity={inA} size={wide ? 26 : 30} />
        <Card x={slot.x} y={slot.y} w={slot.w} h={slot.h} radius={4} style={{opacity: inA}}>
          <div style={{padding: wide ? '70px 56px' : '40px 32px'}}>
            <div style={{fontSize: wide ? 46 : 32, fontWeight: 600, letterSpacing: -0.5}}>품질관리계획서</div>
            <div style={{height: 1, background: C.lineDark, margin: wide ? '18px 0 40px' : '12px 0 24px'}} />
            {Array.from({length: wide ? 14 : 10}).map((_, k) => (
              <div key={k} style={{height: 1, background: C.line, margin: wide ? '0 0 38px' : '0 0 26px', width: `${92 - (k % 3) * 14}%`}} />
            ))}
          </div>
        </Card>
        {STACK.map((src, i) => {
          const t = interpolate(frame, [dropAt(i), dropAt(i) + 16], [0, 1], {...clamp, easing: ease});
          if (t <= 0) return null;
          const o = stackOffset(i + 1);
          const isTable = i === STACK.length - 1;
          return (
            <Card key={src} x={slot.x + o.x + (1 - t) * 50} y={slot.y + o.y} w={slot.w} h={slot.h} radius={3} blue={isTable && fill > 0 && fill < 1}
              style={{opacity: t}}>
              <Img src={staticFile(src)} style={{width: '100%', height: '100%'}} />
              {isTable && (
                <>
                  <div style={{position: 'absolute', left: '7%', right: '5%', top: `${scanY * 100}%`, bottom: '13%', background: C.paper,
                    opacity: frame < 380 ? 1 : fill >= 1 ? 0 : 1}} />
                  <div style={{position: 'absolute', left: '6%', right: '4%', top: `${scanY * 100}%`, height: 3, background: C.blue,
                    opacity: fill > 0 && fill < 1 ? 1 : 0}} />
                </>
              )}
            </Card>
          );
        })}
        {hitIdx.map((i) => {
          const f = flyT(i);
          if (!wide || f <= 0.02 || f >= 0.98) return null; // 4:5 는 칩 없이 선·강조만(판 위 겹침 방지)
          const p = along(route(i), f);
          const r = SHEET_ROWS[i];
          return (
            <div key={i} style={{position: 'absolute', left: wide ? p.x - 40 : p.x - 12, top: p.y - 22, padding: '6px 14px',
              transform: wide ? 'none' : 'translateX(-100%)',
              borderRadius: 8, background: C.blueSoft, border: `1px solid ${C.blue}`, fontSize: L.chipFont, whiteSpace: 'nowrap',
              opacity: interpolate(f, [0.02, 0.12, 0.85, 0.98], [0, 1, 1, 0])}}>
              {r.name} <span style={{color: C.muted}}>→</span> {r.material}{' '}
              <span style={{fontFamily: MONO, color: C.blue, fontSize: L.chipFont - 5}}>{r.spec}</span>
            </div>
          );
        })}

      </div>

      {/* D 대조: 원본(엑셀 두 행)과 결과(8.11 행)를 한 화면에 */}
      <div style={{position: 'absolute', inset: 0, opacity: cmpIn * cmpOut}}>
        <div style={{position: 'absolute', left: L.cmpL.x, top: L.cmpL.y, width: L.cmpL.w}}>
          <Label x={0} y={-50} text="도급내역서.xlsx · 지급(건) · 나동" size={24} />
          {CMP.sources.map((r, k) => (
            <div key={k} style={{display: 'flex', alignItems: 'center', gap: 18, height: 78, padding: '0 20px', marginBottom: 10,
              border: `1px solid ${C.blue}`, borderRadius: 8, background: C.blueSoft, fontSize: 36, whiteSpace: 'nowrap'}}>
              <span style={{fontFamily: MONO, fontSize: 22, color: C.muted, width: 250, flexShrink: 0}}>{r.row}행 · {r.part}</span>
              <span>{r.name}</span>
              <span style={{fontFamily: MONO, fontSize: 30}}>{r.spec}</span>
              <span style={{marginLeft: 'auto', fontWeight: 600, fontVariantNumeric: 'tabular-nums'}}>{fmt(r.qty)} {unitK(r.unit)}</span>
            </div>
          ))}
          <div style={{marginTop: 22, fontSize: 46, fontWeight: 600, color: C.blue, opacity: sumIn, whiteSpace: 'nowrap'}}>
            {CMP.sources.map((r) => fmt(r.qty)).join(' + ')} = {fmt(CMP.total)} {CMP.unit}
          </div>
          <div style={{marginTop: 8, fontSize: 24, color: C.muted, opacity: sumIn}}>같은 규격 두 행을 더해 한 줄로 계획합니다</div>
        </div>

        <div style={{position: 'absolute', left: L.cmpR.x, top: L.cmpR.y, width: L.cmpR.w}}>
          <Label x={0} y={-50} blue text={`8.11 시험계획표 · 계획서 ${CMP.page}쪽`} size={24} />
          <div style={{border: `1px solid ${C.blue}`, borderRadius: 8, background: C.paper, overflow: 'hidden'}}>
            <div style={{display: 'flex', alignItems: 'center', gap: 16, height: 74, padding: '0 20px', background: C.blueSoft,
              borderBottom: `1px solid ${C.blue}`, fontSize: 34, whiteSpace: 'nowrap'}}>
              <span>{CMP.item}</span>
              <span style={{marginLeft: 'auto', fontWeight: 600, color: C.blue, opacity: 0.6 + 0.4 * pulse * sumIn}}>{fmt(CMP.total)} {CMP.unit}</span>
            </div>
            {CMP.tests.map((t, k) => (
              <div key={k} style={{display: 'flex', alignItems: 'center', height: wide ? 52 : 50, padding: '0 20px', borderTop: k ? `1px solid ${C.line}` : 'none',
                fontSize: 30, whiteSpace: 'nowrap'}}>
                <span style={{width: wide ? 200 : 210}}>{t.test}</span>
                <span style={{fontFamily: MONO, fontSize: 22, color: C.muted}}>{t.basis}</span>
                <span style={{marginLeft: 'auto', fontWeight: 600, fontSize: 34, fontVariantNumeric: 'tabular-nums'}}>{t.count}회</span>
              </div>
            ))}
          </div>
          <div style={{marginTop: 18, fontSize: 20, color: C.muted, fontFamily: MONO}}>실제 쪽 일부 ↓</div>
          <Img src={staticFile(CMP.crop.file)} style={{marginTop: 6, width: '100%', border: `1px solid ${C.line}`, borderRadius: 4}} />
        </div>

        {/* 합계 → 8.11 수량 연결선 */}
        {wide && (
          <svg style={{position: 'absolute', left: 0, top: 0, overflow: 'visible', opacity: sumIn}} width={width} height={height}>
            <path d={`M ${L.cmpL.x + 560} ${L.cmpL.y + 2 * 88 + 50} L ${L.cmpR.x - 24} ${L.cmpL.y + 2 * 88 + 50} L ${L.cmpR.x - 24} ${L.cmpR.y + 37} L ${L.cmpR.x} ${L.cmpR.y + 37}`}
              fill="none" stroke={C.blue} strokeWidth={1.5} />
          </svg>
        )}
      </div>

      {/* E 끝: 결과 설명 */}
      <div style={{position: 'absolute', left: L.end.x, top: L.end.y, opacity: endIn, transform: `translateY(${(1 - endIn) * 16}px)`,
        width: wide ? 1300 : width - 2 * L.end.x}}>
        <div style={{fontSize: L.end.head, fontWeight: 650, letterSpacing: -1.2, lineHeight: 1.2, whiteSpace: wide ? 'nowrap' : 'normal'}}>
          도급내역서를 넣으면,{wide ? ' ' : <br />}품질관리계획서가 완성됩니다
        </div>
        <div style={{marginTop: wide ? 44 : 36, display: 'flex', flexDirection: 'column', gap: wide ? 20 : 18}}>
          {[
            ['1~10장 전체 서식', `흐름표 · 양식 ${data.forms}종`],
            ['8.11 시험계획표 자동 계산', `${data.table_rows.length}행 · 현행 기준 고시 ${data.basis_no}`],
            ['한글에서 바로 여는 품질관리계획서.hwpx', `${data.pages}쪽`],
          ].map(([a, b], k) => (
            <div key={k} style={{display: 'flex', alignItems: 'baseline', gap: 16, fontSize: L.end.fact, opacity: factIn(k), flexWrap: 'wrap'}}>
              <span style={{width: 14, height: 14, background: C.blue, display: 'inline-block', transform: 'translateY(-4px)'}} />
              <span style={{fontWeight: 600}}>{a}</span>
              <span style={{color: C.muted}}>{b}</span>
            </div>
          ))}
        </div>
        <div style={{marginTop: wide ? 56 : 44, fontSize: L.end.small, color: C.muted, opacity: factIn(3)}}>
          단번 · <span style={{fontFamily: MONO, color: C.ink}}>danburn start</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
