import { describe, expect, it } from 'vitest';
import { defaultAspect, genApi, targetLabel } from '../api/_generations';

describe('生图目标', () => {
  it('目标决定默认画幅', () => {
    expect(defaultAspect({ type: 'xhs', index: 1 })).toBe('3:4');
    expect(defaultAspect({ type: 'shot', shot: 2 })).toBe('16:9');
    expect(defaultAspect({ type: 'moodboard' })).toBe('1:1');
    expect(defaultAspect(null)).toBe('1:1');
  });
  it('目标名称', () => {
    expect(targetLabel({ type: 'xhs', index: 2 })).toBe('小红书配图 第 2 张');
    expect(targetLabel({ type: 'cover' })).toBe('公众号封面');
    expect(targetLabel({ type: 'shot', shot: 3 })).toBe('分镜 3 关键帧');
  });
  it('候选图地址走 API 前缀', () => {
    expect(genApi.fileUrl('/api/v1/generations/3/files/0')).toMatch(/\/generations\/3\/files\/0$/);
  });
});
