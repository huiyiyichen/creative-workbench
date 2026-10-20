import { describe, expect, it } from 'vitest';
import { errorText } from './feedback';

describe('errorText', () => {
  it('取 Error.message，空的给兜底', () => {
    expect(errorText(new Error('网络断了'))).toBe('网络断了');
    expect(errorText('坏了')).toBe('坏了');
    expect(errorText(null)).toBe('操作失败');
    expect(errorText(new Error(''), '保存失败')).toBe('保存失败');
  });
});
