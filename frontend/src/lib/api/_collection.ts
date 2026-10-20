/**
 * 采集页 API（改造方案 3.8 / 3.9）。
 */

import { BASE_URL, request } from './_core';

export interface MetricPair {
  value: number | null;
  previous: number | null;
}

export interface CollectionOverview {
  today_new: MetricPair;
  success_rate_7d: MetricPair;
  pending_analysis: MetricPair;
  analysis_cost_today: MetricPair;
  missed: MetricPair;
  paused: boolean;
}

export type HealthState = 'paused' | 'error' | 'stale' | 'empty' | 'idle' | 'ok' | 'disabled';

export type SourceKind = 'subscription' | 'keyword' | 'list';

export interface SourceHealthRow {
  id: number;
  name: string;
  platform: string | null;
  kind?: SourceKind;
  query?: string | null;
  platforms?: string[] | null;
  source_type: string;
  url: string;
  enabled: boolean;
  state: HealthState;
  interval_minutes: number;
  base_interval_minutes: number | null;
  auto_paused_at: string | null;
  auto_pause_reason: string | null;
  consecutive_failures: number;
  last_success_at: string | null;
  next_run_at: string | null;
  success_rate_7d: number | null;
  runs_7d: number;
  last_error: { kind: string | null; message: string | null; at: string; http_status: number | null } | null;
  daily_new: number[];
}

export interface FunnelStage {
  key: 'fetched' | 'deduped' | 'prefilter' | 'triage' | 'quick' | 'full' | 'picked';
  label: string;
  value: number | null;
  removed?: number;
  removed_by_reason?: Record<string, number>;
  threshold?: number;
  passed?: number;
}

export interface BudgetStatus {
  budget: number;
  spent: number;
  remaining: number;
}

export interface CollectionFunnel {
  days: number;
  stages: FunnelStage[];
  backlog: { pending: number; analyzing: number; error: number };
  budget?: BudgetStatus;
}

export interface FunnelSettings {
  daily_budget: number;
  triage_threshold: number;
  quick_routing_group: string | null;
  budget: BudgetStatus;
}

export interface RecognizedSource {
  kind: SourceKind;
  source_type: string;
  url: string;
  platform: string | null;
  platforms?: string[];
  query: string | null;
  keyword?: string | null;
  name: string;
}

export interface CreateSourceBody extends RecognizedSource {
  interval_minutes?: number;
  sync_now?: boolean;
}

export interface PlatformInfo {
  platform: string;
  label: string;
  capabilities: Record<string, boolean>;
  needs_key: boolean;
  has_key: boolean;
  /** 抖音、小红书：本机浏览器采集 */
  browser?: boolean;
  browser_status?: { profile: boolean; login_at?: number; last_ok_at?: number; last_error?: string | null; last_error_at?: number };
}

export interface ObservationPoint {
  at: string;
  value: number;
}

export interface RecentItem {
  id: number;
  title: string;
  url: string;
  platform: string | null;
  media_type: string | null;
  author: string | null;
  published_at: string | null;
  crawled_at: string;
  cover_url: string | null;
  cover_asset_id: number | null;
  cover_color: string | null;
  duration: number | null;
  orientation: 'landscape' | 'portrait' | null;
  triage_score: number | null;
  analysis_level: 'none' | 'quick' | 'full';
  full_eligible: boolean | null;
  latest: Record<string, number>;
  series: Record<string, ObservationPoint[]>;
}

export interface AutoActionItem {
  id: number;
  action_type: 'pause_source' | 'pause_platform' | 'backoff_source' | 'flag_stale' | 'resume_source' | string;
  target_type: string;
  target_id: string;
  target_label: string | null;
  reason: string;
  executed_at: string;
  undone_at: string | null;
  undoable: boolean;
}

export interface SyncRunResult {
  status: string;
  fetched: number | null;
  new: number | null;
  duplicates: number | null;
  error_kind: string | null;
  error_message: string | null;
}

export interface CollectionInsights {
  suggestions: {
    kind: 'disable' | 'stale' | 'subscribe' | 'structure';
    text: string;
    action: string;
    source_id?: number;
    author?: string;
    author_url?: string;
    platform?: string;
  }[];
  coverage: { event_id: number; content_id: number | null; title: string; seen_in: string[]; text: string; content_ids: number[] }[];
  completeness: {
    source_id: number;
    name: string;
    items: number;
    cover: number | null;
    published_at: number | null;
    author: number | null;
    metrics: number | null;
    body: number | null;
    delay_hours_median: number | null;
  }[];
  value: {
    days: number;
    sources: {
      source_id: number;
      name: string;
      kind: string | null;
      enabled: boolean | null;
      items: number;
      analyzed: number;
      worth: number;
      worth_rate: number | null;
      favorited: number;
      used_in_projects: number | null;
      duplicate_rate: number | null;
      first_reports: number;
      cost: number;
    }[];
    favorite_trend: { week_end: string; favorites: number }[];
  };
  structure: Record<'platform' | 'language' | 'media_type', { key: string; count: number }[]>;
}

export const collectionApi = {
  insights(): Promise<CollectionInsights> {
    return request('/collection/insights');
  },
  overview(): Promise<CollectionOverview> {
    return request('/collection/overview');
  },
  health(): Promise<{ sources: SourceHealthRow[] }> {
    return request('/collection/health');
  },
  funnel(days = 7): Promise<CollectionFunnel> {
    return request(`/collection/funnel?days=${days}`);
  },
  autoActions(limit = 50): Promise<{ items: AutoActionItem[] }> {
    return request(`/collection/auto-actions?limit=${limit}`);
  },
  undo(id: number): Promise<{ id: number; undone_at: string }> {
    return request(`/collection/auto-actions/${id}/undo`, { method: 'POST' });
  },
  setPaused(paused: boolean): Promise<{ paused: boolean }> {
    return request('/collection/pause', { method: 'PUT', body: JSON.stringify({ paused }) });
  },
  syncSource(id: number): Promise<SyncRunResult> {
    return request(`/collection/sources/${id}/sync`, { method: 'POST', timeoutMs: 330_000 });
  },
  updateSource(id: number, body: { enabled?: boolean; interval_minutes?: number }): Promise<{ id: number }> {
    return request(`/collection/sources/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
  },
  recognize(text: string): Promise<RecognizedSource> {
    return request('/collection/sources/recognize', { method: 'POST', body: JSON.stringify({ text }) });
  },
  createSource(body: CreateSourceBody): Promise<{ id: number; name: string; kind: SourceKind; sync?: SyncRunResult }> {
    return request('/collection/sources', { method: 'POST', body: JSON.stringify(body), timeoutMs: 330_000 });
  },
  recent(sourceId: number, limit = 12): Promise<{ items: RecentItem[] }> {
    return request(`/collection/sources/${sourceId}/recent?limit=${limit}`);
  },
  funnelSettings(): Promise<FunnelSettings> {
    return request('/collection/funnel/settings');
  },
  saveFunnelSettings(body: Partial<Pick<FunnelSettings, 'daily_budget' | 'triage_threshold' | 'quick_routing_group'>>): Promise<FunnelSettings> {
    return request('/collection/funnel/settings', { method: 'PUT', body: JSON.stringify(body) });
  },
  platforms(): Promise<{ items: PlatformInfo[] }> {
    return request('/collection/platforms');
  },
  /** 在本机打开有界面的 Edge 窗口登录（抖音 / 小红书），关窗后登录态保存在该平台的浏览器配置目录 */
  openPlatformLogin(platform: string): Promise<{ platform: string; opened: boolean; already?: boolean }> {
    return request(`/collection/platforms/${platform}/login`, { method: 'POST' });
  },
  setPlatformKey(platform: string, value: string | null): Promise<{ platform: string; has_key: boolean }> {
    return request(`/collection/platforms/${platform}/key`, { method: 'PUT', body: JSON.stringify({ value }) });
  },
};

export function mediaUrl(assetId: number, size: 'thumb' | 'full' = 'thumb'): string {
  return `${BASE_URL}/media/${assetId}?size=${size}`;
}
