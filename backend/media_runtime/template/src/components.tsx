import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

export type SceneProps = {
  index: number;
  scene: {
    beat: string;
    visual: string;
    camera: string;
    audio: string;
    caption: string;
    prompt: string;
    frames: number;
    voiceFile?: string;
  };
  palette: {background: string; foreground: string; accent: string; secondary: string};
};

export const Stage: React.FC<React.PropsWithChildren<{background?: string; color?: string}>> = ({
  children, background = '#f7f8fa', color = '#17191d',
}) => <AbsoluteFill style={{background, color, fontFamily: 'Workbench, sans-serif'}}>{children}</AbsoluteFill>;

export const Reveal: React.FC<React.PropsWithChildren<{delay?: number; x?: number; y?: number; style?: React.CSSProperties}>> = ({
  children, delay = 0, x = 0, y = 36, style,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = spring({frame: frame - delay, fps, config: {damping: 22, stiffness: 110}});
  return <div style={{opacity: Math.min(1, progress), transform: `translate(${x * (1 - progress)}px, ${y * (1 - progress)}px)`, ...style}}>{children}</div>;
};

export const AnimatedNumber: React.FC<{value: number; start?: number; duration?: number; decimals?: number; suffix?: string; style?: React.CSSProperties}> = ({
  value, start = 0, duration = 40, decimals = 0, suffix = '', style,
}) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [start, start + duration], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return <span style={{fontVariantNumeric: 'tabular-nums', ...style}}>{(value * (1 - Math.pow(1 - progress, 3))).toLocaleString('en-US', {maximumFractionDigits: decimals, minimumFractionDigits: decimals})}{suffix}</span>;
};

export const Label: React.FC<React.PropsWithChildren<{color?: string; style?: React.CSSProperties}>> = ({
  children, color = '#60656f', style,
}) => <div style={{fontSize: 28, lineHeight: 1.4, color, ...style}}>{children}</div>;

export const Connector: React.FC<{from: [number, number]; to: [number, number]; color?: string; delay?: number; width?: number; height?: number}> = ({
  from, to, color = '#2264ec', delay = 0, width = 1920, height = 1080,
}) => {
  const frame = useCurrentFrame();
  const reveal = interpolate(frame, [delay, delay + 24], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const length = Math.hypot(to[0] - from[0], to[1] - from[1]);
  return <svg width={width} height={height} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
    <path d={`M ${from.join(' ')} L ${to.join(' ')}`} fill="none" stroke={color} strokeWidth={4} strokeDasharray={length} strokeDashoffset={length * (1 - reveal)} />
  </svg>;
};

export const Caption: React.FC<{text: string; color?: string}> = ({text, color = '#ffffff'}) => (
  <div style={{position: 'absolute', bottom: 48, left: '8%', width: '84%', textAlign: 'center', fontSize: 32, lineHeight: 1.5, color, textShadow: '0 2px 8px #0009'}}>
    {text}
  </div>
);
