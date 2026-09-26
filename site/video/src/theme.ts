// 색·선·글꼴 — 랜딩 레퍼런스의 뉘앙스(옅은 회색·가는 선·옅은 파랑 하나)만 따른다.
export const C = {
  bg: '#f5f5f4',
  hatch: 'rgba(0,0,0,0.035)',
  paper: '#ffffff',
  line: '#b9bcc1',
  lineDark: '#6b6f76',
  ink: '#1f2328',
  muted: '#6b6f76',
  blue: '#3b82f6',
  blueSoft: '#dbe8fd',
  blueLine: '#8db6f7',
  blueInk: '#1d4ed8', // 파란 글자 전용(blueSoft 위 5.42:1, 흰 바탕 6.7:1) — 선·면·눈금은 blue (v4, L8-C1 #6)
};

export const FONT = "'Pretendard', 'Apple SD Gothic Neo', sans-serif";
export const MONO = "'IBM Plex Mono', ui-monospace, monospace";

export const hatchBg = {
  backgroundColor: C.bg,
  backgroundImage: `repeating-linear-gradient(135deg, ${C.hatch} 0px, ${C.hatch} 1px, transparent 1px, transparent 8px)`,
};
