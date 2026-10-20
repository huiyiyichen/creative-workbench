/** 全局跳转（Ctrl+K）的条目与匹配：纯函数，便于测试。 */

export interface CommandItem {
  id: string;
  label: string;
  group: '页面' | '操作' | '项目';
  href?: string;
  /** 额外的检索词（拼音首字母、英文别名等） */
  keywords?: string;
  hint?: string;
}

/** 子序列匹配打分：连续命中、开头命中加分；不命中返回 -1。 */
export function scoreMatch(text: string, query: string): number {
  const t = text.toLowerCase();
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  const direct = t.indexOf(q);
  if (direct >= 0) return 100 - direct + (direct === 0 ? 20 : 0);
  let score = 0;
  let last = -1;
  for (const ch of q) {
    if (ch === ' ') continue;
    const at = t.indexOf(ch, last + 1);
    if (at < 0) return -1;
    score += at === last + 1 ? 3 : 1;
    last = at;
  }
  return score;
}

export function filterCommands(items: CommandItem[], query: string, limit = 12): CommandItem[] {
  if (!query.trim()) return items.slice(0, limit);
  return items
    .map((it, i) => ({ it, i, s: Math.max(scoreMatch(it.label, query), scoreMatch(it.keywords || '', query) - 5) }))
    .filter((x) => x.s >= 0)
    .sort((a, b) => b.s - a.s || a.i - b.i)
    .slice(0, limit)
    .map((x) => x.it);
}

/** 快捷键说明（「?」面板与 Ctrl+K 底部共用） */
export const SHORTCUTS: { keys: string; desc: string }[] = [
  { keys: 'Ctrl K', desc: '全局跳转：页面、项目、常用操作' },
  { keys: '?', desc: '显示快捷键' },
  { keys: 'Ctrl S', desc: '文稿：保存版本' },
  { keys: 'Ctrl Enter', desc: 'AI 助手：发送指令' },
  { keys: 'Alt ↑ / ↓', desc: '分镜行 / 大纲标题：上下移动' },
  { keys: 'Shift 点击', desc: '分镜表：多选' },
];
