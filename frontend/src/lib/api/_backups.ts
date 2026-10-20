/** 一键备份（后端 backup_service）。 */
import { BASE_URL, request } from './_core';

export interface BackupItem {
  name: string;
  status: 'running' | 'done' | 'failed';
  created_at: string;
  include_files?: boolean;
  db_format?: 'pg_dump' | 'jsonl';
  files?: string[];
  size?: number;
  seconds?: number;
  error?: string;
}

export const backupsApi = {
  list(): Promise<{ items: BackupItem[]; keep: number; root: string }> {
    return request('/backups');
  },
  create(includeFiles = true): Promise<{ name: string; status: string }> {
    return request('/backups', { method: 'POST', body: JSON.stringify({ include_files: includeFiles }) });
  },
  remove(name: string): Promise<{ ok: boolean }> {
    return request(`/backups/${encodeURIComponent(name)}`, { method: 'DELETE' });
  },
  downloadUrl(name: string): string {
    return `${BASE_URL}/backups/${encodeURIComponent(name)}/download`;
  },
};

export function fmtBytes(n: number | undefined): string {
  if (!n) return '—';
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}
