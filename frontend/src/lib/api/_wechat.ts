/** 公众号草稿箱（后端 wechat_mp_service）。 */
import { request } from './_core';

export interface WechatSettings {
  app_id: string;
  has_secret: boolean;
  author: string;
  source_url: string;
  open_comment: boolean;
  configured: boolean;
  last_test: string | null;
}

export interface WechatDraftRecord {
  media_id: string;
  pushed_at: string;
  images: number;
  skipped: string[];
}

export const wechatApi = {
  settings(): Promise<WechatSettings> {
    return request('/wechat/settings');
  },
  save(body: Partial<WechatSettings> & { app_secret?: string }): Promise<WechatSettings> {
    return request('/wechat/settings', { method: 'PUT', body: JSON.stringify(body) });
  },
  test(): Promise<{ ok: boolean; message: string }> {
    return request('/wechat/test', { method: 'POST' });
  },
  pushDraft(outputId: number): Promise<WechatDraftRecord> {
    return request(`/outputs/${outputId}/wechat-draft`, { method: 'POST' });
  },
};
