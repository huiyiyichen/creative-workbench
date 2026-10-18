import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { color } from './tokens';

const css = readFileSync(fileURLToPath(new URL('./tokens.css', import.meta.url)), 'utf8');

function kebab(name: string): string {
  return name.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
}

describe('design tokens', () => {
  it('CSS 变量与 tokens.ts 同值', () => {
    for (const [name, value] of Object.entries(color)) {
      const match = css.match(new RegExp(`--cw-${kebab(name)}:\\s*(#[0-9a-f]{6});`));
      expect(match?.[1], name).toBe(value);
    }
  });
});
