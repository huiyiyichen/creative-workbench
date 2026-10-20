import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { color, darkColor, lightColor } from './tokens';

const css = readFileSync(fileURLToPath(new URL('./tokens.css', import.meta.url)), 'utf8');
const lightStart = css.indexOf(":root[data-theme='light']");
const darkCss = css.slice(0, lightStart);
const lightCss = css.slice(lightStart);

function kebab(name: string): string {
  return name.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
}

describe('design tokens', () => {
  it('暗色 CSS 变量与 darkColor 同值', () => {
    for (const [name, value] of Object.entries(darkColor)) {
      const match = darkCss.match(new RegExp(`--cw-${kebab(name)}:\\s*(#[0-9a-f]{6});`));
      expect(match?.[1], name).toBe(value);
    }
  });

  it('亮色 CSS 变量与 lightColor 同值，且两套键一致', () => {
    expect(lightStart).toBeGreaterThan(0);
    expect(Object.keys(lightColor).sort()).toEqual(Object.keys(darkColor).sort());
    for (const [name, value] of Object.entries(lightColor)) {
      const match = lightCss.match(new RegExp(`--cw-${kebab(name)}:\\s*(#[0-9a-f]{6});`));
      expect(match?.[1], name).toBe(value);
    }
  });

  it('页面内联颜色是 CSS 变量引用，随主题切换', () => {
    expect(color.cy).toBe('var(--cw-cy)');
    expect(color.navBg).toBe('var(--cw-nav-bg)');
  });
});
