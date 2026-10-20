import { describe, expect, it } from 'vitest';
import { studioRedirect } from '../studio-redirect';

describe('/studio 跳转', () => {
  it('打开项目按步骤', () => {
    expect(studioRedirect('?project_id=12&stage=2')).toBe('/projects/12/draft');
    expect(studioRedirect('?project_id=12&stage=3')).toBe('/projects/12/outputs');
    expect(studioRedirect('?project_id=12')).toBe('/projects/12/idea');
  });
  it('用于新项目', () => {
    expect(studioRedirect('?content_id=5')).toBe('/projects/new?source=content%3A5');
    expect(studioRedirect('?notes=7&library=3')).toBe('/projects/new?source=library%3A3&source=note%3A7');
  });
  it('其他回到项目列表', () => {
    expect(studioRedirect('')).toBe('/projects');
    expect(studioRedirect('?content_id=abc')).toBe('/projects');
  });
});
