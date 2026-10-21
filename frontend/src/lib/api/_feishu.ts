/** 飞书多维表格（改造方案 10.2）：设置、测试连接、记入飞书。 */
import { request } from './_core';

export interface FeishuSettings {
  app_id: string;
  has_secret: boolean;
  table_url: string;
  app_token: string | null;
  table_id: string | null;
  field_map: Record<string, string>;
  fields: { key: string; label: string }[];
  auto_on_worth: boolean;
  auto_on_project: boolean;
  configured: boolean;
}

export interface FeishuRecord {
  id: number;
  object_type: 'content' | 'project';
  object_id: number;
  record_id: string | null;
  status: 'pending' | 'synced' | 'failed';
  error: string | null;
  trigger: string;
  synced_at: string | null;
  updated_at: string | null;
  skipped_columns?: string[];
}

const j = (v: unknown) => JSON.stringify(v);

export const feishuApi = {
  settings(): Promise<FeishuSettings> {
    return request('/feishu/settings');
  },
  save(body: Partial<Pick<FeishuSettings, 'app_id' | 'table_url' | 'field_map' | 'auto_on_worth' | 'auto_on_project'>> & { app_secret?: string }): Promise<FeishuSettings> {
    return request('/feishu/settings', { method: 'PUT', body: j(body) });
  },
  /** 按字段映射在表格里建好缺的列（首列「文本」会改名为「标题」） */
  setupColumns(): Promise<{ ok: boolean; created: string[]; renamed: string | null }> {
    return request('/feishu/setup-columns', { method: 'POST', timeoutMs: 60_000 });
  },
  test(): Promise<{ ok: boolean; fields: { name: string; type: number }[]; missing: { key: string; column: string }[] }> {
    return request('/feishu/test', { method: 'POST', timeoutMs: 60_000 });
  },
  record(object_type: 'content' | 'project', object_id: number): Promise<FeishuRecord> {
    return request('/feishu/records', { method: 'POST', body: j({ object_type, object_id }), timeoutMs: 60_000 });
  },
  get(object_type: 'content' | 'project', object_id: number): Promise<{ record: FeishuRecord | null }> {
    return request(`/feishu/records?object_type=${object_type}&object_id=${object_id}`);
  },
};
