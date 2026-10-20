import { describe, expect, it } from 'vitest';
import { onboardingSteps } from '../onboarding';

describe('onboardingSteps', () => {
  it('按数量判定每一步', () => {
    expect(onboardingSteps({ models: 1, sources: 0, projects: null }).map((s) => s.done)).toEqual([true, false, false]);
  });
  it('顺序固定：模型 → 信源 → 项目', () => {
    expect(onboardingSteps({ models: 0, sources: 0, projects: 0 }).map((s) => s.key)).toEqual(['models', 'sources', 'projects']);
  });
});
