/** 侧栏「创作」回到上次的创作现场：项目内页每次切换都记下路径。 */

const KEY = 'cw:last-project';

export type LastProject = { id: number; path: string };

export function rememberProject(id: number, path: string): void {
  if (typeof window === 'undefined' || !Number.isFinite(id)) return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify({ id, path }));
  } catch {
    /* 隐私模式等写不进去就算了 */
  }
}

export function lastProject(): LastProject | null {
  if (typeof window === 'undefined') return null;
  try {
    const v = JSON.parse(window.localStorage.getItem(KEY) || 'null');
    if (v && Number.isFinite(v.id) && typeof v.path === 'string' && v.path.startsWith(`/projects/${v.id}`)) return v;
  } catch {
    /* 坏数据当没有 */
  }
  return null;
}

export function forgetProject(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
