/** 旧工作台 /studio 的地址 → 新的 /projects 地址（阶段 4 收尾，设计文档 11.2）。 */
export function studioRedirect(search: string): string {
  const p = new URLSearchParams(search);
  const pid = Number(p.get('project_id'));
  if (pid > 0) {
    const stage = Number(p.get('stage')) || 0;
    const step = stage >= 3 ? 'outputs' : stage === 2 ? 'draft' : 'idea';
    return `/projects/${pid}/${step}`;
  }
  const sources: string[] = [];
  for (const [key, kind] of [
    ['content_id', 'content'],
    ['library', 'library'],
    ['notes', 'note'],
  ] as const) {
    for (const v of p.getAll(key)) if (/^\d+$/.test(v)) sources.push(`${kind}:${v}`);
  }
  if (sources.length) return `/projects/new?${sources.map((s) => `source=${encodeURIComponent(s)}`).join('&')}`;
  return '/projects';
}
