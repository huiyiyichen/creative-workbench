import { describe, expect, it } from 'vitest';
import { analysisLabel, compactNumber, formatDuration, primarySeries, sparkPath, waveform } from '@/lib/collection';

describe('阶段 1 采集页展示逻辑', () => {
  it('观测不足 2 个点不画曲线', () => {
    expect(sparkPath([], 100, 20)).toBeNull();
    expect(sparkPath([5], 100, 20)).toBeNull();
    expect(sparkPath([1, 3], 100, 20)).toBe('M2.0,18.0 L98.0,2.0');
    expect(sparkPath([4, 4], 100, 20)).toBe('M2.0,10.0 L98.0,10.0');
  });

  it('选主指标时跳过排名', () => {
    expect(primarySeries({ rank: [{ at: 'a', value: 1 }], likes: [{ at: 'a', value: 2 }] })).toBe('likes');
    expect(primarySeries({ rank: [{ at: 'a', value: 1 }] })).toBeNull();
    expect(primarySeries({})).toBeNull();
  });

  it('时长与大数字', () => {
    expect(formatDuration(61)).toBe('1:01');
    expect(formatDuration(3723)).toBe('1:02:03');
    expect(formatDuration(null)).toBeNull();
    expect(compactNumber(12345)).toBe('1.2万');
    expect(compactNumber(null)).toBe('—');
  });

  it('生成封面波形稳定', () => {
    expect(waveform('Opus 5.5')).toEqual(waveform('Opus 5.5'));
    expect(waveform('Opus 5.5')).not.toEqual(waveform('别的标题'));
    expect(waveform('x', 8)).toHaveLength(8);
  });

  it('分析状态文案', () => {
    expect(analysisLabel({ analysis_level: 'full', full_eligible: true })).toBe('已分析');
    expect(analysisLabel({ analysis_level: 'none', full_eligible: false })).toBe('不做完整分析');
    expect(analysisLabel({ analysis_level: 'none', full_eligible: null })).toBe('未分析');
  });
});
