/**
 * 全局事件流（后端 /events/stream）：整个页面只开一条 SSE 连接，各处按主题订阅。
 * 主题：tasks（任务摘要）、notifications（未读数）、sources（信源告警）。
 * 新订阅者会立刻收到该主题最近一次的数据；没有订阅者时关闭连接。
 * 浏览器不支持 EventSource 时什么都不做，调用方保留低频轮询兜底。
 */

import { BASE_URL } from './api/_core';

export type EventTopic = 'tasks' | 'notifications' | 'sources';
type Listener = (data: unknown) => void;

export function createEventBus(open: (onEvent: (topic: string, data: unknown) => void) => () => void) {
  const listeners = new Map<string, Set<Listener>>();
  const latest = new Map<string, unknown>();
  let close: (() => void) | null = null;

  const emit = (topic: string, data: unknown) => {
    latest.set(topic, data);
    for (const fn of listeners.get(topic) ?? []) fn(data);
  };

  function subscribe<T>(topic: EventTopic, fn: (data: T) => void): () => void {
    const set = listeners.get(topic) ?? new Set<Listener>();
    listeners.set(topic, set);
    set.add(fn as Listener);
    if (latest.has(topic)) (fn as Listener)(latest.get(topic));
    if (!close) close = open(emit);
    return () => {
      set.delete(fn as Listener);
      const any = [...listeners.values()].some((s) => s.size > 0);
      if (!any && close) {
        close();
        close = null;
        latest.clear();
      }
    };
  }

  return { subscribe, emit, active: () => close !== null };
}

const TOPICS: EventTopic[] = ['tasks', 'notifications', 'sources'];

function openEventSource(url: string) {
  return (onEvent: (topic: string, data: unknown) => void) => {
    if (typeof EventSource === 'undefined') return () => {};
    const es = new EventSource(url, { withCredentials: true });
    for (const t of TOPICS) {
      es.addEventListener(t, (e) => {
        try {
          onEvent(t, JSON.parse((e as MessageEvent).data));
        } catch {
          /* 坏数据跳过 */
        }
      });
    }
    return () => es.close();
  };
}

let bus: ReturnType<typeof createEventBus> | null = null;

/** 订阅一个主题；返回取消函数。 */
export function onEvent<T>(topic: EventTopic, fn: (data: T) => void): () => void {
  if (!bus) {
    bus = createEventBus(openEventSource(`${BASE_URL}/events/stream`));
  }
  return bus.subscribe(topic, fn);
}

/**
 * 任务有变化时调用 fn（不含订阅时的补发）；用来替代「每 N 秒刷新一次」。
 * 返回取消函数。enabled 为 false 时不订阅。
 */
export function onTasksChanged(fn: () => void): () => void {
  let first = true;
  return onEvent('tasks', () => {
    if (first) {
      first = false;
      return;
    }
    fn();
  });
}
