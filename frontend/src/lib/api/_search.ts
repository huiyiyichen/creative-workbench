/** 全局搜索：库内检索 + 按关键词去平台现抓（后端 /search）。 */
import { request } from './_core';
import { decodeTextDeep } from '../text';
import type { RecentItem } from './_collection';

export type SearchGroup = 'contents' | 'library' | 'notes' | 'projects' | 'outputs' | 'reports';

export interface SearchHit {
  id: number;
  title: string;
  snippet: string | null;
  href: string;
  at?: string | null;
  platform?: string | null;
  kind?: string | null;
  stage?: string | null;
  status?: string | null;
}

export interface SearchResult {
  q: string;
  groups: Partial<Record<SearchGroup, SearchHit[]>>;
  total: number;
}

export interface CrawlPlatform {
  platform: string;
  label: string;
  needs_key: boolean;
  has_key: boolean;
}

export interface CrawlResult {
  q: string;
  status: string;
  fetched: number;
  new: number;
  duplicates: number;
  error_message: string | null;
  source_id: number;
  created: boolean;
  tracking: boolean;
  platforms: string[];
  items: RecentItem[];
}

export const SEARCH_GROUP_LABEL: Record<SearchGroup, string> = {
  contents: '采集内容',
  library: '灵感库',
  notes: '随笔',
  projects: '项目',
  outputs: '产出',
  reports: '报告',
};

export const SEARCH_GROUP_ORDER: SearchGroup[] = ['contents', 'library', 'notes', 'projects', 'outputs', 'reports'];

export const searchApi = {
  search(q: string, opts: { limit?: number; groups?: SearchGroup[] } = {}): Promise<SearchResult> {
    const p = new URLSearchParams({ q });
    if (opts.limit) p.set('limit', String(opts.limit));
    if (opts.groups?.length) p.set('groups', opts.groups.join(','));
    return request<SearchResult>(`/search?${p.toString()}`).then(decodeTextDeep);
  },
  platforms(): Promise<{ items: CrawlPlatform[] }> {
    return request('/search/platforms');
  },
  tracking(q: string): Promise<{ source_id: number | null; tracking: boolean; platforms?: string[] | null }> {
    return request(`/search/tracking?q=${encodeURIComponent(q)}`);
  },
  crawl(body: { q: string; platforms?: string[]; track?: boolean }): Promise<CrawlResult> {
    return request('/search/crawl', { method: 'POST', body: JSON.stringify(body), timeoutMs: 330_000 });
  },
};
