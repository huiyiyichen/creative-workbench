/**
 * 发现：今日（5.1）、条目详情（5.6）、热点 · 升温 / 追踪词（5.2）、专题（5.5）、报告（5.4）、评分说明。
 */
import { request } from './_core';

export type Verdict = 'worth' | 'watch' | 'skip';
export type TopicStatus = 'new' | 'rising' | 'steady' | 'peak' | 'cooling' | 'quiet';

export interface MetricView {
  metric: string | null;
  value?: number;
  delta?: number | null;
  since?: string | null;
  observed_at?: string;
  observations?: number;
  state?: string;
}

export interface ItemCard {
  id: number;
  title: string;
  url: string;
  summary: string | null;
  platform: string | null;
  source_id: number | null;
  source_name: string | null;
  media_type: string;
  author: string | null;
  published_at: string | null;
  crawled_at: string;
  cover_url: string | null;
  cover_asset_id: number | null;
  cover_color: string | null;
  duration: number | null;
  orientation: 'landscape' | 'portrait' | null;
  analysis_level: string;
  is_favorited: boolean;
  heat: number | null;
  metric: MetricView;
  verdict: Verdict | null;
  verdict_label: string | null;
  verdict_reason: string | null;
  key_points: string[];
  user_verdict: Verdict | null;
  event: { event_id: number; members: number; representative_id: number | null } | null;
}

export interface TodayFeed {
  view: 'all' | 'picks';
  total: number;
  items: ItemCard[];
  days: { date: string; items: ItemCard[] }[] | null;
}

export interface SignalClip {
  id: number;
  title: string;
  at: string;
  media_type: string;
  heat: number | null;
  verdict: Verdict | null;
}

export interface TodaySignals {
  range?: 'today' | '48h' | '7d';
  start: string;
  end: string;
  now: string;
  tracks: { platform: string; items: SignalClip[] }[];
}

export interface WatchTermPanel {
  source_id: number;
  term: string;
  enabled: boolean;
  platforms: string[];
  dots: number[];
  per_platform: Record<string, number>;
  total: number;
}

export interface ResonanceMatrix {
  platforms: string[];
  rows: { event_id: number; representative_id: number | null; title: string; cells: Record<string, number> }[];
}

export interface TodaySide {
  watch_terms: WatchTermPanel[];
  resonance: ResonanceMatrix;
  collection: {
    today_new: { value: number | null };
    success_rate_7d: { value: number | null };
    pending_analysis: { value: number | null };
    missed: { value: number | null };
    paused: boolean;
  };
}

export interface VerdictFull {
  verdict: Verdict;
  label: string;
  reason: string;
  basis: {
    heat: { metric?: string; value?: number; rank?: number; growth?: { metric: string; first: number; last: number; hours: number }; state?: string };
    timing: { age_hours?: number; topic_status?: TopicStatus | null; first_platform?: string };
    same_topic: { event_id: number | null; members: number; platforms: string[] };
    relevance: { keyword_hits: string[]; related_favorites: number; feedback: string | null };
    quality: number | null;
    analysis_level: string;
    risk: { score: number | null; rule_hits: string[]; notes: string[] };
  };
  missing: string[];
  key_points: string[];
  detail: { points: number; scored: { basis: string; points: number; why: string }[]; rules: Record<string, number>; formula: string };
  user_verdict: Verdict | null;
  computed?: Verdict;
  user_note?: string | null;
}

export interface JourneyStep {
  id: number;
  stage: string;
  summary: string | null;
  detail: Record<string, unknown> | null;
  sync_run_id: number | null;
  llm_request_id: string | null;
  at: string;
}

export interface ItemDetail extends ItemCard {
  raw_content: string | null;
  summary_full: string | null;
  author_url: string | null;
  media: Record<string, unknown>;
  triage_score: number | null;
  triage_signals: Record<string, unknown> | null;
  quick_result: Record<string, unknown> | null;
  comment_state: string;
  skip_reason: string | null;
  verdict_full: VerdictFull;
  series: Record<string, { at: string; value: number }[]>;
  event: null | (ItemCard['event'] & {
    id: number;
    representative_id: number;
    is_representative: boolean;
    others: { id: number; title: string; url: string; platform: string | null; media_type: string; published_at: string }[];
    dossier: { id: number; title: string } | null;
  });
  dossiers: { id: number; title: string }[];
  analysis: null | {
    id: number;
    inherited_from: number | null;
    summary: string | null;
    recommendation: string | null;
    risk_score: number | null;
    info_density: number | null;
    actionability: number | null;
    angles: { title: string; detail: string | null }[];
    created_at: string;
    final_model: string | null;
  };
  feedback: 'useful' | 'not_interested' | null;
  journey: JourneyStep[];
}

export interface TopicRow {
  id: number;
  kind: 'event' | 'watch_term';
  title: string;
  event_id: number | null;
  watch_source_id: number | null;
  status: TopicStatus;
  status_label: string;
  signal: number | null;
  signal_prev: number | null;
  signal_peak: number | null;
  series: (number | null)[];
  platforms: Record<string, number>;
  first_platform: string | null;
  content_count: number;
  source_count: number | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  streak_days: number | null;
  representative_id: number | null;
  computed_at: string | null;
}

export interface RisingBoard {
  computed_at: string | null;
  status_counts: Partial<Record<TopicStatus, number>>;
  items: (TopicRow & { representative: ItemCard | null; dossier_id: number | null })[];
}

export interface WatchTermCurve {
  source_id: number;
  term: string;
  name: string;
  platforms: string[];
  enabled: boolean;
  interval_minutes: number;
  last_sync_at: string | null;
  trend: TopicRow | null;
}

export interface DossierSummary {
  id: number;
  kind: 'event' | 'watch_term' | 'manual';
  title: string;
  event_id: number | null;
  watch_source_id: number | null;
  query: string | null;
  followed: boolean;
  status: TopicStatus | null;
  status_label: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  archived_at: string | null;
  series: (number | null)[];
  platforms: Record<string, number>;
  content_count: number | null;
}

export interface DossierDetail extends DossierSummary {
  timeline: ItemCard[];
  first_by_platform: { platform: string; at: string }[];
  reports: { kind: string; id: number; date: string; label: string }[];
  favorites: ItemCard[];
  verdict: { verdict: Verdict; label: string; reason: string } | null;
  trend_computed_at: string | null;
}

export interface Completeness {
  pending_analysis: number;
  failed_sources: string[];
  trending_missing_days: string[];
  uncollected_days: string[];
  computed_at: string;
}

export interface PeriodSummary {
  id: number;
  kind: 'gap' | 'range';
  title: string;
  start_date: string;
  end_date: string;
  version: number;
  status: string;
  generated_at: string;
  completeness: Completeness | null;
  error: string | null;
}

export interface PeriodSections {
  big_events: { event_id: number; title: string; content_id: number | null; items: number; platforms: number; verdict: Verdict | null }[];
  rising_topics: { title: string; kind: string; event_id: number | null; status: TopicStatus; status_label: string; platforms: Record<string, number>; content_id: number | null; peak_signal: number }[];
  cooling_topics: { title: string; kind: string; event_id: number | null; status_label: string; content_id: number | null }[];
  watch_terms: { source_id: number; term: string; count: number; previous: number; delta: number }[];
  missed_worth: { content_id: number; title: string; platform: string | null; reason: string | null; key_points: string[] }[];
  followed_updates: { event_id: number; title: string; new_items: number; latest: { content_id: number; title: string; platform: string | null } }[];
  daily_items: { date: string; items: number; collected: boolean }[];
  overview: { items: number; collected_days: number; days: number };
}

export interface PeriodDetail extends PeriodSummary {
  sections: PeriodSections | null;
  versions: { id: number; version: number; generated_at: string }[];
}

export type CalendarState = 'report' | 'collected' | 'uncollected' | 'future';

export interface ReportCalendar {
  year: number;
  month: number;
  days: { date: string; state: CalendarState; report_id: number | null; edition: string | null; status: string | null; headline: string | null; items: number }[];
  weeklies: { id: number; key: string; label: string; start: string }[];
  monthly_id: number | null;
  gaps: PeriodSummary[];
}

export interface ReportHit {
  kind: string;
  id: number;
  key: string;
  label: string;
  snippet: string | null;
}

export interface ScoringGroup {
  values: Record<string, number>;
  defaults: Record<string, number>;
}

export interface ScoringSettings {
  triage_weights: ScoringGroup;
  verdict_rules: ScoringGroup;
  status_rules: ScoringGroup;
  agreement: {
    days: number;
    marks: number;
    corrected: number;
    mark_agreement: number | null;
    favorites: number;
    favorites_worth: number;
    favorite_agreement: number | null;
  };
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '');
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()}` : '';
}

/** 评论（3.5）：none 未采集 / collected 已采集 / unavailable 无评论来源 / failed 采集失败 */
export type CommentState = 'none' | 'collected' | 'unavailable' | 'failed';

export interface CommentDigest {
  points: { text: string; comment_ids: number[] }[];
  based_on: number;
  generated_at: string;
}

export interface CommentList {
  state: CommentState;
  crawled_at: string | null;
  source: string | null;
  items: { id: number; author: string | null; text: string; likes: number | null; replies: number | null; published_at: string | null }[];
  digest: CommentDigest | null;
  error?: string;
}

export const discoverApi = {
  feed(params: { view?: 'all' | 'picks'; media?: string; platform?: string; limit?: number; offset?: number } = {}): Promise<TodayFeed> {
    return request(`/today/feed${qs(params)}`);
  },
  signals(range: 'today' | '48h' | '7d' = 'today'): Promise<TodaySignals> {
    return request(`/today/signals?range=${range}`);
  },
  side(): Promise<TodaySide> {
    return request('/today/side');
  },
  seen(): Promise<{ previous: string | null; away_days: number | null; gap_start: string | null; gap_end: string | null }> {
    return request('/today/seen', { method: 'POST' });
  },
  item(id: number): Promise<ItemDetail> {
    return request(`/items/${id}`);
  },
  setVerdict(id: number, verdict: Verdict | null, note?: string): Promise<VerdictFull> {
    return request(`/items/${id}/verdict`, { method: 'PUT', body: JSON.stringify({ verdict, note: note || null }) });
  },
  setFeedback(id: number, kind: 'useful' | 'not_interested' | null): Promise<{ feedback: string | null; verdict: VerdictFull }> {
    return request(`/items/${id}/feedback`, { method: 'PUT', body: JSON.stringify({ kind }) });
  },
  leaveEvent(id: number): Promise<{ removed: boolean; event_id?: number }> {
    return request(`/items/${id}/leave-event`, { method: 'POST' });
  },
  comments(id: number): Promise<CommentList> {
    return request(`/items/${id}/comments`);
  },
  loadComments(id: number, refresh = false): Promise<CommentList> {
    return request(`/items/${id}/comments/load${refresh ? '?refresh=true' : ''}`, { method: 'POST', timeoutMs: 60_000 });
  },
  digestComments(id: number): Promise<CommentDigest> {
    return request(`/items/${id}/comments/digest`, { method: 'POST', timeoutMs: 120_000 });
  },
  analyze(id: number): Promise<{ analyzed: boolean; reason?: string }> {
    return request(`/items/${id}/analyze`, { method: 'POST', timeoutMs: 180_000 });
  },
  rising(params: { status?: TopicStatus; kind?: 'event' | 'watch_term'; limit?: number } = {}): Promise<RisingBoard> {
    return request(`/hot/rising${qs(params)}`);
  },
  watchTerms(): Promise<{ items: WatchTermCurve[] }> {
    return request('/hot/watch-terms');
  },
  dossiers(params: { archived?: boolean; q?: string } = {}): Promise<{ items: DossierSummary[] }> {
    return request(`/dossiers${qs(params)}`);
  },
  dossier(id: number): Promise<DossierDetail> {
    return request(`/dossiers/${id}`);
  },
  follow(body: { event_id?: number; watch_source_id?: number; title?: string; query?: string }): Promise<{ id: number; followed: boolean }> {
    return request('/dossiers/follow', { method: 'POST', body: JSON.stringify(body) });
  },
  setFollowed(id: number, followed: boolean): Promise<{ id: number; followed: boolean }> {
    return request(`/dossiers/${id}/followed`, { method: 'PUT', body: JSON.stringify({ followed }) });
  },
  calendar(year: number, month: number): Promise<ReportCalendar> {
    return request(`/reports/calendar${qs({ year, month })}`);
  },
  searchReports(q: string): Promise<{ items: ReportHit[] }> {
    return request(`/reports/search${qs({ q })}`);
  },
  periods(kind?: 'gap' | 'range'): Promise<{ items: PeriodSummary[] }> {
    return request(`/reports/periods${qs({ kind })}`);
  },
  period(id: number): Promise<PeriodDetail> {
    return request(`/reports/periods/${id}`);
  },
  createPeriod(start_date: string, end_date: string): Promise<PeriodSummary> {
    return request('/reports/periods', { method: 'POST', body: JSON.stringify({ start_date, end_date }) });
  },
  regeneratePeriod(id: number): Promise<PeriodSummary> {
    return request(`/reports/periods/${id}/regenerate`, { method: 'POST' });
  },
  continuity(date: string): Promise<{ previous_date: string | null; continued: string[]; new: string[]; dropped: string[] }> {
    return request(`/reports/daily/${date}/continuity`);
  },
  scoring(): Promise<ScoringSettings> {
    return request('/settings/scoring');
  },
  saveScoring(body: Partial<Record<'triage_weights' | 'verdict_rules' | 'status_rules', Record<string, number>>>): Promise<Omit<ScoringSettings, 'agreement'>> {
    return request('/settings/scoring', { method: 'PUT', body: JSON.stringify(body) });
  },
};
