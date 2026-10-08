/**
 * Daily Report & Creation API — 日报与创作方案。
 *
 * 从 _domains.ts 拆出。
 */

import { request, type RequestOptions } from './_core';
import type { YesterdayTrackingData } from '@/types';

export interface WebhookDeliveryLogItem {
  id: number;
  alert_key: string;
  event_type: string;
  title: string;
  severity: string;
  webhook_url_preview: string;
  status_code: number | null;
  success: boolean;
  error_message: string | null;
  response_preview: string | null;
  duration_ms: number;
  created_at: string | null;
}

export const dailyReportApi = {
  /** 获取今日日报（不存在则自动生成） */
  getToday(): Promise<Record<string, unknown>> {
    return request('/daily-reports/today');
  },

  /** 按日期查询单个日报 */
  getByDate(date: string): Promise<Record<string, unknown>> {
    return request(`/daily-reports/by-date?date=${encodeURIComponent(date)}`);
  },

  /** 选题 sparkline 趋势数据（按标题关键词查询近 N 小时内容流入速率） */
  sparkline(title: string, hours: number = 48, bucketHours: number = 2): Promise<{
    points: Array<{ ts: string; count: number; baseline?: number }>;
    keywords: string[];
    total: number;
    window_hours: number;
  }> {
    return request(
      `/daily-reports/sparkline?title=${encodeURIComponent(title)}&hours=${hours}&bucket_hours=${bucketHours}`,
    );
  },

  /** 获取用户的选题标记 */
  listPickMarks(reportDate?: string): Promise<{
    marks: Array<{
      report_date: string;
      pick_title: string;
      action: 'write' | 'watch' | 'skip';
      pick_category: string | null;
      pick_source_url: string | null;
    }>;
    total: number;
  }> {
    return request(
      `/daily-reports/pick-marks${reportDate ? `?report_date=${reportDate}` : ''}`,
    );
  },

  /** 创建/更新选题标记 */
  markPick(body: {
    report_date: string;
    pick_title: string;
    action: 'write' | 'watch' | 'skip';
    pick_category?: string;
    pick_source_url?: string;
  }): Promise<{ status: string; action: string }> {
    return request('/daily-reports/pick-marks', { method: 'POST', body: JSON.stringify(body) });
  },

  /** 删除选题标记 */
  unmarkPick(reportDate: string, pickTitle: string): Promise<{ status: string }> {
    return request(
      `/daily-reports/pick-marks?report_date=${encodeURIComponent(reportDate)}&pick_title=${encodeURIComponent(pickTitle)}`,
      { method: 'DELETE' },
    );
  },

  /** 获取有日报的日期列表 */
  listDates(): Promise<{ dates: Array<{ report_date: string; weekday: string; takeaway: string | null; status: string }> }> {
    return request('/daily-reports/dates');
  },

  /** 获取最近一段时间的日报状态地图 */
  calendar(days: number = 30): Promise<{
    days: Array<{
      report_date: string;
      weekday: string;
      status: string;
      edition: string | null;
      generated_at: string | null;
      cutoff_at: string | null;
      takeaway: string | null;
      content_count: number;
      analyzed_count: number;
      topic_count: number;
      has_report: boolean;
      can_generate: boolean;
      is_today: boolean;
    }>;
    total_days: number;
    done_count: number;
    error_count: number;
    missing_count: number;
    generating_count: number;
  }> {
    return request(`/daily-reports/calendar?days=${days}`);
  },

  /** 日报列表 */
  list(limit: number = 7): Promise<{ items: Record<string, unknown>[]; total: number }> {
    return request(`/daily-reports?limit=${limit}`);
  },

  /** 强制重新生成今日日报 */
  regenerate(): Promise<Record<string, unknown>> {
    return request('/daily-reports/generate', { method: 'POST' });
  },

  /** 生成指定日报版本 */
  generateVersion(params: { target_date?: string; edition?: string; cutoff_at?: string; force?: boolean; scope?: 'public' | 'mine' } = {}): Promise<{ id: number; report_date: string; status: string }> {
    const query = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => [k, String(v)])
    ).toString();
    return request(`/daily-reports/generate-version${query ? `?${query}` : ''}`, { method: 'POST' });
  },

  getGenerationStatus(id: number): Promise<Record<string, unknown>> {
    return request(`/daily-reports/generation/${id}`);
  },

  /** 手动推送日报到 webhook（管理员） */
  pushWebhook(date: string, edition?: string): Promise<{ sent: boolean; message: string }> {
    const params = new URLSearchParams({ date });
    if (edition) params.set('edition', edition);
    return request(`/daily-reports/push-webhook?${params}`, { method: 'POST' });
  },

  /** 获取 webhook 推送日志（管理员） */
  listWebhookLogs(params?: { event_type?: string; limit?: number; offset?: number }): Promise<{
    items: WebhookDeliveryLogItem[];
    total: number;
    limit: number;
    offset: number;
  }> {
    const qs = new URLSearchParams();
    if (params?.event_type) qs.set('event_type', params.event_type);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return request(`/daily-reports/webhook-logs${query ? '?' + query : ''}`);
  },

  /** 昨日追踪（公共日报）：昨日 top picks 的 24h 热度 delta + lifecycle 验证 */
  getYesterdayTracking(reportDate: string): Promise<YesterdayTrackingData> {
    return request(`/daily-reports/yesterday-tracking?report_date=${encodeURIComponent(reportDate)}`);
  },

  // ── /me series: user-owned private daily reports (T2) ──

  /** 获取今日我的专属日报（不存在则自动生成；需 Pro+） */
  getMyToday(): Promise<Record<string, unknown>> {
    return request('/daily-reports/me/today');
  },

  /** 按日期查询我的日报 */
  getMyByDate(date: string): Promise<Record<string, unknown>> {
    return request(`/daily-reports/me/by-date?date=${encodeURIComponent(date)}`);
  },

  /** 获取我的日报日期列表 */
  listMyDates(): Promise<{ dates: Array<{ report_date: string; weekday: string; takeaway: string | null; status: string }> }> {
    return request('/daily-reports/me/dates');
  },

  /** 强制重新生成我的今日日报 */
  regenerateMy(): Promise<Record<string, unknown>> {
    return request('/daily-reports/me/generate', { method: 'POST' });
  },

  /** 昨日追踪（我的日报，Pro+）：额外返回 your_marked（昨日 write/watch 标记的今日进展） */
  getMyYesterdayTracking(reportDate: string): Promise<YesterdayTrackingData> {
    return request(`/daily-reports/me/yesterday-tracking?report_date=${encodeURIComponent(reportDate)}`);
  },
};

export interface StudioCatalog {
  templates: Array<{
    id: string;
    name: string;
    category?: string;
    description?: string;
    image?: string;
    modes: string[];
    beats: string[];
    custom?: boolean;
    favorite_id?: number;
  }>;
  styles: Array<{
    id: string;
    name: string;
    category?: string;
    description?: string;
    image?: string;
    colors: string[];
    background: string;
    foreground: string;
    accent: string;
    secondary: string;
    rules: string[];
    native_mv: boolean;
    custom?: boolean;
    favorite_id?: number;
  }>;
}

export interface StudioShot {
  seconds: number;
  beat: string;
  visual: string;
  camera: string;
  audio: string;
  transition: string;
  caption: string;
  prompt: string;
}

export interface StudioCue {
  time: number;
  text: string;
}

export interface StudioBrief {
  theme: string;
  mode: 'article' | 'video_prompt' | 'animation_video' | 'music_video';
  template_id: string | null;
  style_id: string | null;
  presentation: 'cinematic' | 'kinetic' | 'ascii' | 'tui' | null;
  production: 'video_model' | 'code_animation' | 'native_mv' | null;
  duration_seconds: number;
  aspect_ratio: '16:9' | '9:16' | '1:1';
  audience: string;
  intent: string;
  bilingual: boolean;
}

export interface StudioDraft {
  title: string;
  logline: string;
  body: string;
  shots: StudioShot[];
  cues: StudioCue[];
  provenance: 'manual' | 'compiled' | 'ai';
}

export interface StudioProject {
  id: number;
  title: string;
  version: number;
  brief: StudioBrief;
  draft: StudioDraft;
  previous_revision?: { version: number; draft: StudioDraft } | null;
  source: Record<string, unknown>;
  finalized_version: number | null;
  revisions: Array<{ version: number; reason: string; created_at: string }>;
  assets: Array<{ id: number; kind: string; name: string; duration: number | null }>;
  artifacts: StudioArtifact[];
  updated_at: string | null;
}

export interface StudioArtifact {
  id: number;
  project_id: number;
  version: number;
  kind: string;
  status: string;
  title?: string;
  progress: {
    percent?: number | null;
    stage?: string;
    logs?: Array<{ at: string; stage: string }>;
    started_at?: string;
    elapsed_seconds?: number;
    last_heartbeat?: string;
    workspace_files?: number;
    last_file_at?: string | null;
  };
  preview_path: string | null;
  source_path?: string | null;
  storage_path: string | null;
  download_path: string | null;
  error: string | null;
  created_at?: string | null;
}

export const studioApi = {
  catalog(options?: RequestOptions): Promise<StudioCatalog> {
    return request('/studio/catalog', options);
  },
  listProjects(options?: RequestOptions): Promise<{ items: StudioProject[]; total: number }> {
    return request('/studio/projects', options);
  },
  createProject(body: { brief: StudioBrief; content_id?: number; favorite_id?: number }): Promise<StudioProject> {
    return request('/studio/projects', { method: 'POST', body: JSON.stringify(body) });
  },
  getProject(id: number): Promise<StudioProject> {
    return request(`/studio/projects/${id}`);
  },
  jobs(): Promise<{ items: StudioArtifact[] }> {
    return request('/studio/jobs');
  },
  revision(id: number, version: number): Promise<{ version: number; brief: StudioBrief; draft: StudioDraft }> {
    return request(`/studio/projects/${id}/revisions/${version}`);
  },
  saveProject(id: number, body: { expected_version: number; brief: StudioBrief; draft: StudioDraft }): Promise<StudioProject> {
    return request(`/studio/projects/${id}`, { method: 'PUT', body: JSON.stringify(body) });
  },
  generateDraft(id: number, expectedVersion: number, engine: 'rules' | 'ai' = 'rules', action: 'generate' | 'refine' = 'generate', instructions = ''): Promise<StudioProject> {
    return request(`/studio/projects/${id}/draft`, {
      method: 'POST',
      body: JSON.stringify({ expected_version: expectedVersion, engine, action, instructions }),
    });
  },
  productionPrompt(id: number): Promise<{ project_id: number; version: number; prompt: string }> {
    return request(`/studio/projects/${id}/production-prompt`);
  },
  uploadAudio(id: number, file: File): Promise<{ id: number; kind: string; name: string; duration: number }> {
    const form = new FormData();
    form.append('file', file);
    return request(`/studio/projects/${id}/audio`, { method: 'POST', body: form, headers: {} });
  },
  uploadLrc(id: number, file: File): Promise<StudioProject> {
    const form = new FormData();
    form.append('file', file);
    return request(`/studio/projects/${id}/lrc`, { method: 'POST', body: form, headers: {} });
  },
  finalize(id: number, expectedVersion: number): Promise<StudioProject> {
    return request(`/studio/projects/${id}/finalize`, {
      method: 'POST',
      body: JSON.stringify({ expected_version: expectedVersion }),
    });
  },
  render(id: number): Promise<{ artifact_id: number; status: string }> {
    return request(`/studio/projects/${id}/render`, { method: 'POST' });
  },
  artifact(id: number): Promise<StudioArtifact> {
    return request(`/studio/artifacts/${id}`);
  },
  harnessProduction(id: number): Promise<{ artifact_id: number; status: string; kind: string }> {
    return request(`/studio/projects/${id}/harness-production`, { method: 'POST' });
  },
};
