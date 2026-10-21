/** 短视频口播稿解析（抖音 / B站平台版本）：
 * - 抖音：一行一个镜头，行首【画面：…】是画面提示；
 * - B站：单独一行【弹幕】xxx 是弹幕互动点。
 */

export type ScriptLine = { text: string; shot?: string; danmaku?: string };

const SHOT = /^[【\[]\s*画面\s*[:：]\s*([^】\]]*)[】\]]\s*/;
const DANMAKU = /^[【\[]\s*弹幕\s*[】\]]\s*[:：]?\s*/;

export function parseScript(body: string | null | undefined): ScriptLine[] {
  const out: ScriptLine[] = [];
  for (const raw of (body || '').split(/\n+/)) {
    const line = raw.trim();
    if (!line) continue;
    const d = line.match(DANMAKU);
    if (d) {
      const text = line.slice(d[0].length).trim();
      if (text) out.push({ text: '', danmaku: text });
      continue;
    }
    const m = line.match(SHOT);
    if (m) out.push({ shot: m[1].trim() || undefined, text: line.slice(m[0].length).trim() });
    else out.push({ text: line });
  }
  return out;
}

/** 口播语速按每秒 4.5 字估算（含标点不计）。 */
export function estimateSeconds(lines: ScriptLine[]): number {
  const chars = lines.reduce((n, l) => n + l.text.replace(/[\s，。！？、,.!?：:；;“”"'…—-]/g, '').length, 0);
  return Math.round(chars / 4.5);
}

export function fmtDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}
