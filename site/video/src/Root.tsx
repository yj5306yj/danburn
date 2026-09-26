import {Composition} from 'remotion';
import {DURATION, Hero} from './Hero';
import {DURATION_V1, HeroV1} from './HeroV1';
import {DURATION_V2, HeroV2} from './HeroV2';
import {DURATION_V3, HeroV3} from './HeroV3';
import {DURATION_V4, HeroV4} from './HeroV4';

// v4(critique 반영, 16초 루프) 가 현재 판. v3(v2 작은 수정) v2(대조·설명 끝) v1(정면·확대)·v0(아이소메트릭)은 비교용으로 남긴다.
// 16:9(히어로 오른쪽 칸) · 4:5(좁은 화면·SNS — v0 만 배치 있음).
export const Root = () => (
  <>
    <Composition id="HeroV4" component={HeroV4} durationInFrames={DURATION_V4} fps={30} width={1920} height={1080} />
    <Composition id="HeroV4x45" component={HeroV4} durationInFrames={DURATION_V4} fps={30} width={1080} height={1350} />
    <Composition id="HeroV3" component={HeroV3} durationInFrames={DURATION_V3} fps={30} width={1920} height={1080} />
    <Composition id="HeroV3x45" component={HeroV3} durationInFrames={DURATION_V3} fps={30} width={1080} height={1350} />
    <Composition id="HeroV2" component={HeroV2} durationInFrames={DURATION_V2} fps={30} width={1920} height={1080} />
    <Composition id="HeroV2x45" component={HeroV2} durationInFrames={DURATION_V2} fps={30} width={1080} height={1350} />
    <Composition id="HeroV1" component={HeroV1} durationInFrames={DURATION_V1} fps={30} width={1920} height={1080} />
    <Composition id="Hero" component={Hero} durationInFrames={DURATION} fps={30} width={1920} height={1080} />
    <Composition id="Hero45" component={Hero} durationInFrames={DURATION} fps={30} width={1080} height={1350} />
  </>
);
