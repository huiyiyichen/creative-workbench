import { describe, expect, it, vi } from 'vitest';
import { createEventBus } from './events';

describe('事件总线', () => {
  it('一条连接、按主题分发、新订阅者补发最近一次、没人订阅时关闭', () => {
    let push: ((t: string, d: unknown) => void) | null = null;
    const close = vi.fn();
    const open = vi.fn((on: (t: string, d: unknown) => void) => {
      push = on;
      return close;
    });
    const bus = createEventBus(open);
    const a = vi.fn();
    const b = vi.fn();
    const offA = bus.subscribe('tasks', a);
    const offB = bus.subscribe('notifications', b);
    expect(open).toHaveBeenCalledTimes(1);
    push!('tasks', { active: 1 });
    push!('notifications', { count: 2 });
    expect(a).toHaveBeenCalledWith({ active: 1 });
    expect(b).toHaveBeenCalledWith({ count: 2 });
    const c = vi.fn();
    const offC = bus.subscribe('tasks', c);
    expect(c).toHaveBeenCalledWith({ active: 1 });
    offA();
    offC();
    expect(close).not.toHaveBeenCalled();
    offB();
    expect(close).toHaveBeenCalledTimes(1);
    expect(bus.active()).toBe(false);
    // 重新订阅会重新连接，缓存已清
    const d = vi.fn();
    bus.subscribe('tasks', d);
    expect(open).toHaveBeenCalledTimes(2);
    expect(d).not.toHaveBeenCalled();
  });
});
