/** 发布排期、发布日历、发布后数据回收（后端 publishing_service）。 */
import { request } from './_core';

export interface PublishSchedule {
  at: string;
  platform: string | null;
  note: string;
  notified: boolean;
}

export interface MetricState {
  latest?: Record<string, number>;
  checked_at?: string;
  error?: string;
}

export interface CalendarItem {
  id: number;
  project_id: number;
  project_title: string;
  kind: string;
  kind_label: string;
  title: string;
  status: string;
  scheduled_at: string | null;
  schedule_platform: string | null;
  schedule_note: string;
  published_at: string | null;
  published_url: string | null;
  platform: string | null;
  metrics: Record<string, number>;
  at?: string;
}

export interface PublishCalendar {
  start: string;
  end: string;
  items: CalendarItem[];
  backlog: CalendarItem[];
}

export interface PerfGroup {
  key: string;
  label: string;
  count: number;
  median: Record<string, number>;
}

export interface Performance {
  published: number;
  tracked: number;
  by_kind: PerfGroup[];
  by_platform: PerfGroup[];
  top: CalendarItem[];
}

export const publishingApi = {
  schedule(outputId: number, body: { at: string | null; platform?: string | null; note?: string }): Promise<{ id: number; schedule: PublishSchedule | null }> {
    return request(`/outputs/${outputId}/schedule`, { method: 'PUT', body: JSON.stringify(body) });
  },
  refreshMetrics(outputId: number): Promise<{ id: number; metrics: MetricState }> {
    return request(`/outputs/${outputId}/metrics/refresh`, { method: 'POST' });
  },
  metrics(outputId: number): Promise<{ series: Record<string, { at: string; value: number }[]> }> {
    return request(`/outputs/${outputId}/metrics`);
  },
  calendar(start: string, end: string): Promise<PublishCalendar> {
    return request(`/publishing/calendar?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
  },
  performance(): Promise<Performance> {
    return request('/publishing/performance');
  },
};

export const METRIC_LABEL: Record<string, string> = {
  views: '播放 / 阅读',
  likes: '点赞',
  comments: '评论',
  favorites: '收藏',
  shares: '转发',
  coins: '投币',
  danmaku: '弹幕',
  stars: 'Star',
  score: '分数',
};

export const PUBLISH_PLATFORMS = [
  { value: 'xiaohongshu', label: '小红书' },
  { value: 'bilibili', label: 'B站' },
  { value: 'douyin', label: '抖音' },
  { value: 'wechat', label: '公众号' },
  { value: 'zhihu', label: '知乎' },
  { value: 'youtube', label: 'YouTube' },
];
