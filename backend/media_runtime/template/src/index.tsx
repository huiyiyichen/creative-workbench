import React from 'react';
import {AbsoluteFill, Audio, Composition, Sequence, registerRoot, staticFile, useCurrentFrame} from 'remotion';
import timeline from '../timeline.json';
import {Scene} from './Scenes';

const Captions: React.FC = () => {
  const frame = useCurrentFrame();
  const time = frame / timeline.fps;
  const cue = (timeline.captions ?? []).find(cue => time >= cue.start && time < cue.end);
  if (!cue) return null;
  return <div style={{position: 'absolute', bottom: 48, left: 80, right: 80, zIndex: 100, textAlign: 'center', fontFamily: 'Workbench', fontSize: 48, fontWeight: 600, lineHeight: 1.4}}>
    <span style={{color: '#fff', background: 'rgba(0,0,0,0.65)', padding: '8px 14px'}}>{cue.text}</span>
  </div>;
};

const Film: React.FC = () => {
  let offset = 0;
  return <AbsoluteFill>
    <style>{`@font-face{font-family:Workbench;src:url("${staticFile('fonts/NotoSansSC.ttf')}")}*{box-sizing:border-box;letter-spacing:0}`}</style>
    {timeline.scenes.map((scene, index) => {
      const from = offset;
      offset += scene.frames;
      return <Sequence key={index} from={from} durationInFrames={scene.frames}>
        <Scene index={index} scene={scene} palette={timeline.palette} />
        {scene.voiceFile && <Audio src={staticFile(scene.voiceFile)} />}
      </Sequence>;
    })}
    {timeline.soundtrack && <Audio src={staticFile(timeline.soundtrack)} />}
    <Captions />
  </AbsoluteFill>;
};

registerRoot(() => <Composition
  id="Film"
  component={Film}
  width={timeline.width}
  height={timeline.height}
  fps={timeline.fps}
  durationInFrames={timeline.scenes.reduce((sum, scene) => sum + scene.frames, 0)}
/>);
