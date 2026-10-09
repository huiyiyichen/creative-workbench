import { request } from './_core';
import type { ContentScoringResult, MotherTopic, MotherTopicMutation } from '@/types/trending';

export const motherTopicsApi = {
  list(active_only = false, scope: 'mine' | 'all' = 'mine'): Promise<MotherTopic[]> {
    return request(`/mother-topics?active_only=${active_only}&scope=${scope}`);
  },
  create(data: {
    name: string;
    description?: string;
    keywords: string[];
    weight?: number;
    content_type?: string;
    target_reader?: string;
    is_active?: boolean;
    display_order?: number;
  }): Promise<MotherTopic> {
    return request('/mother-topics', { method: 'POST', body: JSON.stringify(data) });
  },
  update(id: number, data: MotherTopicMutation): Promise<MotherTopic> {
    return request(`/mother-topics/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  },
  delete(id: number): Promise<{ ok: boolean; message: string }> {
    return request(`/mother-topics/${id}`, { method: 'DELETE' });
  },
  forkDefaults(): Promise<{ forked: number; skipped: number; message: string }> {
    return request('/mother-topics/fork-defaults', { method: 'POST' });
  },
  score(data: { title: string; summary?: string; source?: string; hot_value?: number }): Promise<ContentScoringResult> {
    return request('/mother-topics/score', { method: 'POST', body: JSON.stringify(data) });
  },
  scoreBatch(items: Array<{ title: string; summary?: string; hot_value?: number }>): Promise<{ results: ContentScoringResult[] }> {
    return request('/mother-topics/score-batch', { method: 'POST', body: JSON.stringify({ items }) });
  },
  matchContent(contentId: number): Promise<{
    content_id: number;
    title: string;
    top_topic: string | null;
    top_score: number;
    all_scores: Array<{ name: string; keyword_score: number; weight: number; final: number }>;
  }> {
    return request(`/mother-topics/match/${contentId}`);
  },
};
