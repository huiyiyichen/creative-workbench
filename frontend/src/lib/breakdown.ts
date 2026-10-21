import type { Breakdown } from './api/_library';

/** 「照这个结构写」带进新项目创作思路的文字（与后端 breakdown_service.intent_from 一致）。 */
export function breakdownIntent(b: Pick<Breakdown, 'title' | 'verdict' | 'hook' | 'template'>): string {
  const lines = [`参考爆款：${b.title}`];
  if (b.verdict) lines.push(`它为什么火：${b.verdict}`);
  if (b.hook?.text) lines.push(`钩子（${b.hook.type || '—'}）：${b.hook.text}`);
  if (b.template) lines.push('', '照这个结构写：', b.template);
  return lines.join('\n').slice(0, 5000);
}

/** 评论热词的字号档位：按出现条数线性映射到 0–3 档。 */
export function wordTier(count: number, max: number): 0 | 1 | 2 | 3 {
  if (!max || count <= 0) return 0;
  return Math.min(3, Math.round((count / max) * 3)) as 0 | 1 | 2 | 3;
}

export function isUrl(text: string): boolean {
  return /^https?:\/\/\S+$/i.test(text.trim());
}
