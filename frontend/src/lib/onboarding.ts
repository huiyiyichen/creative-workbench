/** 首页三步引导的步骤判定。null 表示没查到（接口失败），按未完成处理但不阻塞后续步骤。 */

export interface OnboardingCounts {
  models: number | null;
  sources: number | null;
  projects: number | null;
}

export interface OnboardingStep {
  key: 'models' | 'sources' | 'projects';
  title: string;
  desc: string;
  action: string;
  href: string;
  done: boolean;
}

export function onboardingSteps(c: OnboardingCounts): OnboardingStep[] {
  return [
    { key: 'models', title: '配置模型', desc: 'AI 写稿、日报、分析都要用到；填一个 API Key 就行', action: '去配置', href: '/admin/model-eval', done: (c.models ?? 0) > 0 },
    { key: 'sources', title: '添加信源', desc: 'RSS、B 站、抖音、小红书等，采集后出现在「今日」', action: '加信源', href: '/sources', done: (c.sources ?? 0) > 0 },
    { key: 'projects', title: '新建项目', desc: '从一条灵感或一个主题开始，写稿到成片', action: '新建项目', href: '/projects/new', done: (c.projects ?? 0) > 0 },
  ];
}
