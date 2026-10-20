'use client';

/**
 * 暗色 / 亮色主题切换：写在 <html data-theme>，存 localStorage「cw-theme」。
 * 首屏由 layout 里的内联脚本先设好，避免闪一下暗色。
 */
import { useSyncExternalStore } from 'react';
import type { CwTheme } from './tokens';

import { THEME_KEY } from './theme-boot';

export { THEME_KEY };

function read(): CwTheme {
  if (typeof document === 'undefined') return 'dark';
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

function subscribe(cb: () => void): () => void {
  const obs = new MutationObserver(cb);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  return () => obs.disconnect();
}

export function setCwTheme(mode: CwTheme): void {
  if (mode === 'light') document.documentElement.dataset.theme = 'light';
  else delete document.documentElement.dataset.theme;
  try {
    localStorage.setItem(THEME_KEY, mode);
  } catch {
    /* 无痕模式等写不进去时只在本页生效 */
  }
}

export function useCwTheme(): [CwTheme, (mode: CwTheme) => void] {
  const mode = useSyncExternalStore(subscribe, read, () => 'dark' as CwTheme);
  return [mode, setCwTheme];
}
