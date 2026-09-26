// 평행(직교) 아이소메트릭 투영. CSS 의 `rotateX(TILT) rotateZ(SPIN)` 과 같은 수식으로
// 평면 위 점(x, y, z)을 화면 좌표로 바꾼다 — 2D 라벨·연결선을 3D 판에 정확히 붙이기 위해.
export const TILT = 58; // deg, rotateX
export const SPIN = -42; // deg, rotateZ

const rad = (d: number) => (d * Math.PI) / 180;

export const isoTransform = `rotateX(${TILT}deg) rotateZ(${SPIN}deg)`;

/** 판 원점(판 왼쪽 위 모서리) 기준 점 → 판 원점 기준 화면 변위(px). z 는 판에서 위로. */
export function project(x: number, y: number, z = 0): {x: number; y: number} {
  // CSS 는 오른쪽 변환부터 점에 적용: p' = Rx(TILT) · Rz(SPIN) · p
  const cz = Math.cos(rad(SPIN));
  const sz = Math.sin(rad(SPIN));
  const x1 = x * cz - y * sz;
  const y1 = x * sz + y * cz;
  const cx = Math.cos(rad(TILT));
  const sx = Math.sin(rad(TILT));
  const y2 = y1 * cx - z * sx;
  return {x: x1, y: y2};
}
