/** 生成服务与生图（改造方案第 8 节、创作工作台设计 6.5）。 */
import { BASE_URL, request } from './_core';

export type Aspect = '1:1' | '3:4' | '4:3' | '16:9' | '9:16';
export type GenTarget =
  | { type: 'moodboard' }
  | { type: 'paragraph'; paragraph_id: string }
  | { type: 'xhs'; index: number }
  | { type: 'cover' }
  | { type: 'shot'; shot: number }
  | { type: 'mv'; time: number };

export interface GenService {
  id: number;
  name: string;
  kind: 'image' | 'video' | 'music';
  api_format: 'openai_images';
  base_url: string;
  model: string;
  capabilities: { refs?: boolean; max_n?: number; sizes?: Record<string, string> };
  unit_price: number;
  daily_limit: number | null;
  enabled: boolean;
  is_default: boolean;
  has_key: boolean;
  key_hint: string | null;
  spent_today: number;
}

export interface GenJob {
  id: number;
  service_id: number | null;
  model: string | null;
  prompt: string;
  ref_item_ids: number[];
  params: { aspect?: Aspect; size?: string; n?: number; estimate?: number };
  target: GenTarget | null;
  project_id: number | null;
  output_id: number | null;
  status: 'queued' | 'running' | 'done' | 'failed';
  results: { index: number; file: string; library_item_id: number | null; url: string }[];
  cost: number;
  error: string | null;
  created_at: string | null;
}

const j = (v: unknown) => JSON.stringify(v);

export const genApi = {
  services(kind?: string): Promise<{ items: GenService[] }> {
    return request(`/generation/services${kind ? `?kind=${kind}` : ''}`);
  },
  createService(body: Partial<GenService> & { api_key?: string }): Promise<GenService> {
    return request('/generation/services', { method: 'POST', body: j(body) });
  },
  updateService(id: number, body: Partial<GenService> & { api_key?: string }): Promise<GenService> {
    return request(`/generation/services/${id}`, { method: 'PATCH', body: j(body) });
  },
  deleteService(id: number): Promise<void> {
    return request(`/generation/services/${id}`, { method: 'DELETE' });
  },
  testService(id: number): Promise<{ ok: boolean; error: string | null; job_id: number }> {
    return request(`/generation/services/${id}/test`, { method: 'POST', timeoutMs: 200_000 });
  },
  generate(body: {
    prompt: string;
    ref_item_ids?: number[];
    aspect?: Aspect;
    n?: number;
    service_id?: number;
    project_id?: number;
    output_id?: number;
    target?: GenTarget;
    parent_job_id?: number;
    parent_index?: number;
  }): Promise<GenJob> {
    return request('/generations/images', { method: 'POST', body: j(body) });
  },
  job(id: number): Promise<GenJob> {
    return request(`/generations/${id}`);
  },
  keep(id: number, indexes: number[], role?: string): Promise<{ job: GenJob; library_item_ids: number[] }> {
    return request(`/generations/${id}/keep`, { method: 'POST', body: j({ indexes, role }) });
  },
  draftPrompt(projectId: number | null, body: { target?: GenTarget; style_id?: string | null; ref_item_ids?: number[] }): Promise<{ prompt: string }> {
    return request(projectId ? `/projects/${projectId}/image-prompt` : '/generations/image-prompt', {
      method: 'POST',
      body: j(body),
      timeoutMs: 60_000,
    });
  },
  fileUrl(path: string): string {
    return path.startsWith('/api/v1') ? `${BASE_URL}${path.slice('/api/v1'.length)}` : path;
  },
};

/** 目标决定默认画幅（与后端 TARGET_DEFAULTS 一致） */
export function defaultAspect(target: GenTarget | null | undefined): Aspect {
  switch (target?.type) {
    case 'xhs':
      return '3:4';
    case 'paragraph':
    case 'cover':
    case 'shot':
    case 'mv':
      return '16:9';
    default:
      return '1:1';
  }
}

export function targetLabel(target: GenTarget | null | undefined): string {
  switch (target?.type) {
    case 'paragraph':
      return '文稿插图';
    case 'xhs':
      return `小红书配图 第 ${target.index} 张`;
    case 'cover':
      return '公众号封面';
    case 'shot':
      return `分镜 ${target.shot} 关键帧`;
    case 'mv':
      return 'MV 画面';
    default:
      return '情绪板';
  }
}
