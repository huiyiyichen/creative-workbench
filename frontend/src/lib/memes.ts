import type { Meme } from './api/_trending';

/** 「拿它开稿」：新建项目，主题是梗，创作思路写清意思和示范用法。 */
export function memeProjectHref(m: Pick<Meme, 'word' | 'meaning' | 'usage' | 'origin'>): string {
  const intent = [`用今天的梗「${m.word}」写一篇`, m.meaning && `意思：${m.meaning}`, m.origin && `来源：${m.origin}`, m.usage && `示范用法：${m.usage}`]
    .filter(Boolean)
    .join('\n');
  return `/projects/new?theme=${encodeURIComponent(m.word)}&intent=${encodeURIComponent(intent)}`;
}

export function heatLabel(h: number): string {
  return h >= 3 ? '正火' : h === 2 ? '升温' : '冒头';
}
