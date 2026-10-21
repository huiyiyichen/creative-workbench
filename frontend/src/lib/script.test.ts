import { describe, expect, it } from 'vitest';
import { estimateSeconds, fmtDuration, parseScript } from './script';

describe('parseScript', () => {
  it('镜头、弹幕与普通行', () => {
    const lines = parseScript('【画面：桌面特写】第一句话。\n\n【弹幕】前方高能\n普通一句\n[画面: 街景] 第三句');
    expect(lines).toEqual([
      { shot: '桌面特写', text: '第一句话。' },
      { text: '', danmaku: '前方高能' },
      { text: '普通一句' },
      { shot: '街景', text: '第三句' },
    ]);
  });
  it('空稿', () => {
    expect(parseScript('')).toEqual([]);
    expect(parseScript(null)).toEqual([]);
  });
  it('时长估算', () => {
    expect(estimateSeconds(parseScript('一二三四五六七八九'))).toBe(2);
    expect(fmtDuration(65)).toBe('1:05');
  });
});
