/**
 * 采集页 API（改造方案 3.8 / 3.9）。
 */

import { request } from './_core';

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

export interface SourceHealthRow {
  id: number;
  name: string;
  platform: string | null;
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
  key: 'fetched' | 'deduped' | 'prefilter' | 'quick' | 'full' | 'picked';
  label: string;
  value: number | null;
  removed?: number;
  removed_by_reason?: Record<string, number>;
}

export interface CollectionFunnel {
  days: number;
  stages: FunnelStage[];
  backlog: { pending: number; analyzing: number; error: number };
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

export const collectionApi = {
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
};
