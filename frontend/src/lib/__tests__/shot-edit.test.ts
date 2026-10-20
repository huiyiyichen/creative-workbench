import { describe, expect, it } from 'vitest';
import { emptyShot, mergeShotWithNext, moveSection, splitShot, splitTextNearMiddle } from '../projects';

const shot = (over: Partial<ReturnType<typeof emptyShot>>) => ({ ...emptyShot(), ...over });

describe('splitTextNearMiddle', () => {
  it('在最靠近中间的句末断开', () => {
    expect(splitTextNearMiddle('短。中间这句话比较长。尾巴。')).toEqual(['短。中间这句话比较长。', '尾巴。']);
  });
  it('没有句末时按字数对半', () => {
    expect(splitTextNearMiddle('一二三四')).toEqual(['一二', '三四']);
  });
  it('短文本不拆', () => {
    expect(splitTextNearMiddle('一')).toEqual(['一', '']);
  });
});

describe('splitShot', () => {
  it('时长对半、旁白断句、画面保留', () => {
    const out = splitShot([shot({ seconds: 5, visual: '海边', audio: '浪来了。人走了。', transition: '叠化' })], 0);
    expect(out).toHaveLength(2);
    expect(out.map((s) => s.seconds)).toEqual([2.5, 2.5]);
    expect(out.map((s) => s.audio)).toEqual(['浪来了。', '人走了。']);
    expect(out.map((s) => s.visual)).toEqual(['海边', '海边']);
    expect(out[0].transition).toBe('直切');
    expect(out[1].transition).toBe('叠化');
  });
  it('越界不变', () => {
    const list = [shot({})];
    expect(splitShot(list, 3)).toBe(list);
  });
});

describe('mergeShotWithNext', () => {
  it('时长相加、文字相接、转场取后一镜', () => {
    const out = mergeShotWithNext(
      [shot({ seconds: 2.5, visual: '海边', audio: '浪来了。', transition: '直切' }), shot({ seconds: 3, visual: '海边', audio: '人走了。', transition: '黑场' }), shot({ visual: '下一镜' })],
      0,
    );
    expect(out).toHaveLength(2);
    expect(out[0]).toMatchObject({ seconds: 5.5, visual: '海边', audio: '浪来了。人走了。', transition: '黑场' });
    expect(out[1].visual).toBe('下一镜');
  });
  it('最后一镜不合并', () => {
    const list = [shot({}), shot({})];
    expect(mergeShotWithNext(list, 1)).toBe(list);
  });
});

describe('moveSection', () => {
  const body = ['引子', '## 甲', '甲1', '### 甲小节', '甲2', '## 乙', '乙1', '## 丙', '丙1'].join('\n\n');
  it('下移：整节（含子标题）放到目标节后面', () => {
    expect(moveSection(body, 0, 3)?.split('\n\n')).toEqual(['引子', '## 乙', '乙1', '## 丙', '丙1', '## 甲', '甲1', '### 甲小节', '甲2']);
  });
  it('上移：放到目标节前面', () => {
    expect(moveSection(body, 3, 0)?.split('\n\n')).toEqual(['引子', '## 丙', '丙1', '## 甲', '甲1', '### 甲小节', '甲2', '## 乙', '乙1']);
  });
  it('相邻下移', () => {
    expect(moveSection(body, 2, 3)?.split('\n\n')).toEqual(['引子', '## 甲', '甲1', '### 甲小节', '甲2', '## 丙', '丙1', '## 乙', '乙1']);
  });
  it('不同级不动', () => {
    expect(moveSection(body, 1, 2)).toBeNull();
  });
});
