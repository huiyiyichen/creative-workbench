/**
 * _trending API objects extracted from lib/api.ts.
 * Uses request from ./_core.
 */

import { request } from './_core';
import type { CrossPlatformCluster, PersistentTopic, TrendingAngleRecommendation, TrendingItem, TrendingSource } from '@/types/trending';

// ─── Trending Radar (趋势雷达) API ───

/** 今日梗雷达（GET /trending/memes）。 */
export interface Meme {
  word: string;
  meaning: string;
  origin: string;
  usage: string;
  fit: string;
  platforms: string[];
  heat: 1 | 2 | 3;
}
export interface MemeRadar {
  date: string;
  items: Meme[];
  at: string | null;
  reason?: string;
  stale?: boolean;
  basis?: { titles: number; comments: number };
}

export const trendingApi = {
  memes(refresh = false): Promise<MemeRadar> {
    return request(`/trending/memes${refresh ? '?refresh=true' : ''}`, { timeoutMs: 90_000 });
  },
  /** 获取趋势数据 */
  list(params?: {
    category?: string;
    source?: string;
    exclude_sources?: string[];
    limit?: number;
  }): Promise<TrendingItem[]> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0))
            .map(([k, v]) => [k, Array.isArray(v) ? v.join(',') : String(v)])
        ).toString()
      : '';
    return request(`/trending${query}`);
  },

  /** 获取可用信源列表 */
  async listSources(): Promise<TrendingSource[]> {
    const data = await request<TrendingSource[] | { sources?: TrendingSource[] }>('/trending/sources');
    return Array.isArray(data) ? data : data.sources || [];
  },

  /** 同步单个信源 */
  sync(source: string): Promise<{ fetched: number }> {
    return request(`/trending/sync/${encodeURIComponent(source)}`, { method: 'POST' });
  },

  /** 同步所有信源 */
  syncAll(): Promise<Record<string, { fetched: number }>> {
    return request('/trending/sync-all', { method: 'POST' });
  },

  /** 跨平台热点交叉发现 */
  crossPlatform(params?: { min_resonance?: number; limit?: number }): Promise<{
    total: number;
    clusters: CrossPlatformCluster[];
  }> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/trending/cross-platform${query}`);
  },

  /** 持续在榜话题分析 */
  persistent(params?: { min_days?: number; min_sources?: number; days_back?: number }): Promise<{
    total: number;
    topics: PersistentTopic[];
  }> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : '';
    return request(`/trending/persistent${query}`);
  },

  /** 为共振话题生成创作角度推荐 */
  angles(topic: string): Promise<TrendingAngleRecommendation> {
    return request(`/trending/angles?topic=${encodeURIComponent(topic)}`);
  },
};

// ─── Cross-Platform Clustering ───

