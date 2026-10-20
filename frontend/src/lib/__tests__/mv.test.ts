import { describe, expect, it } from 'vitest';
import { boundaries, moveBoundary, shotAt, snapToCue } from '../mv';

const shots = [{ seconds: 3 }, { seconds: 4 }, { seconds: 5 }];
const cues = [
  { time: 2.5, text: '一' },
  { time: 6.2, text: '二' },
];

describe('mv timeline', () => {
  it('computes boundaries', () => {
    expect(boundaries(shots)).toEqual([0, 3, 7, 12]);
    expect(shotAt(shots, 3.1)).toBe(1);
    expect(shotAt(shots, 99)).toBe(2);
  });

  it('snaps to nearby cue', () => {
    expect(snapToCue(2.8, cues)).toBe(2.5);
    expect(snapToCue(4, cues)).toBe(4);
  });

  it('moves a boundary keeping total and minimum length', () => {
    const out = moveBoundary(shots, 1, 2.7, cues);
    expect(out.map((s) => s.seconds)).toEqual([2.5, 4.5, 5]);
    expect(moveBoundary(shots, 2, 6.0, cues).map((s) => s.seconds)).toEqual([3, 3.2, 5.8]);
    expect(moveBoundary(shots, 1, 0.1, []).map((s) => s.seconds)).toEqual([0.5, 6.5, 5]);
    expect(moveBoundary(shots, 0, 1, cues)).toBe(shots);
  });
});
