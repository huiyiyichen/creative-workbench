/** 灵感库（6）、随笔（6.4）、风格与模板（6.6）。 */
import { BASE_URL, request } from './_core';

export type LibraryKind = 'article' | 'video' | 'image' | 'post' | 'prompt' | 'repo' | 'asset' | 'generated' | 'link';
export type AssetKind = 'image' | 'palette' | 'font' | 'icon' | 'texture' | 'motion' | 'audio';
export type License = 'own' | 'commercial' | 'reference' | 'unknown' | 'ai';

export interface LibraryItem {
  id: number;
  kind: LibraryKind;
  asset_kind: AssetKind | null;
  title: string;
  url: string | null;
  platform: string | null;
  author: string | null;
  content_id: number | null;
  body: string | null;
  meta: Record<string, unknown> | null;
  file_name: string | null;
  mime: string | null;
  bytes: number | null;
  has_file: boolean;
  thumb: boolean;
  width: number | null;
  height: number | null;
  duration: number | null;
  dominant_color: string | null;
  palette: string[] | null;
  cover_url: string | null;
  license: License;
  import_method: string;
  source_url: string | null;
  tags: string[];
  ai_tags: string[];
  ai_description: string | null;
  my_notes: string | null;
  starred: boolean;
  obsidian_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface RelatedRef {
  type: 'item' | 'note' | 'content' | 'dossier' | 'project' | 'style' | 'template';
  id: number;
  relation: string;
  link_id?: number;
  title: string;
  kind?: string;
  thumb?: boolean;
  color?: string | null;
}

export interface LibraryItemDetail extends LibraryItem {
  related: RelatedRef[];
  boards: { id: number; name: string }[];
}

export interface LibraryFacets {
  kinds: Record<string, number>;
  asset_kinds: Record<string, number>;
  licenses: Record<string, number>;
  tags: [string, number][];
  storage: { bytes: number; files: number };
}

export interface Board {
  id: number;
  name: string;
  description: string | null;
  count: number;
  covers: { id: number; color: string | null; thumb: boolean }[];
  updated_at: string;
}

export interface NoteView {
  id: number;
  body: string;
  tags: string[];
  audio: boolean;
  transcript_status: string | null;
  image_item_ids: number[];
  source: string;
  created_at: string;
  updated_at: string;
  links: RelatedRef[];
}

export interface NoteRelated {
  favorites: { content_id: number; title: string; similarity: number | null }[];
  hot: { content_id: number; title: string; similarity: number | null }[];
}

export interface TemplateVersion {
  version: number;
  purpose: string | null;
  audience: string | null;
  structure: { title: string; points?: string[] }[];
  tone: string | null;
  forms: string[];
  note: string | null;
  created_at: string;
}

export interface StyleVersion {
  version: number;
  palette: { name?: string; hex: string }[];
  fonts: { role?: string; family?: string; item_id?: number }[];
  layout_rules: string | null;
  motion_rules: string | null;
  reference_item_ids: number[];
  forms: string[];
  note: string | null;
  created_at: string;
}

export interface StyleEntry<V> {
  id: number;
  key: string;
  name: string;
  builtin: boolean;
  current_version: number;
  current?: V | null;
  versions?: V[];
  copied_from?: string | null;
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const e = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '');
  return e.length ? `?${new URLSearchParams(e.map(([k, v]) => [k, String(v)])).toString()}` : '';
}

export function libraryFileUrl(id: number, size: 'small' | 'large' | 'original' = 'small'): string {
  return `${BASE_URL}/library/items/${id}/file?size=${size}`;
}

export const libraryApi = {
  list(params: {
    kind?: string;
    asset_kind?: string;
    license?: string;
    tag?: string;
    q?: string;
    color?: string;
    board_id?: number;
    limit?: number;
    offset?: number;
  } = {}): Promise<{ total: number; items: LibraryItem[] }> {
    return request(`/library/items${qs(params)}`);
  },
  facets(): Promise<LibraryFacets> {
    return request('/library/facets');
  },
  item(id: number): Promise<LibraryItemDetail> {
    return request(`/library/items/${id}`);
  },
  fromContent(content_id: number): Promise<LibraryItem> {
    return request('/library/items/from-content', { method: 'POST', body: JSON.stringify({ content_id }) });
  },
  fromLink(url: string, note?: string): Promise<LibraryItem> {
    return request('/library/items/from-link', { method: 'POST', body: JSON.stringify({ url, note }), timeoutMs: 60_000 });
  },
  text(text: string, kind: 'prompt' | 'link' | 'article' = 'prompt', title?: string): Promise<LibraryItem> {
    return request('/library/items/text', { method: 'POST', body: JSON.stringify({ text, kind, title }) });
  },
  upload(files: File[], method: 'file' | 'clipboard' = 'file'): Promise<{ items: LibraryItem[]; errors: { file: string; error: string }[] }> {
    const form = new FormData();
    for (const f of files) form.append('files', f, f.name || 'paste.png');
    form.append('method', method);
    return request('/library/items/upload', { method: 'POST', body: form, timeoutMs: 300_000 });
  },
  frame(body: { content_id?: number; image_url?: string; item_id?: number; at?: number }): Promise<LibraryItem> {
    return request('/library/items/frame', { method: 'POST', body: JSON.stringify(body), timeoutMs: 60_000 });
  },
  update(id: number, body: Partial<Pick<LibraryItem, 'title' | 'tags' | 'license' | 'my_notes' | 'starred' | 'body'>>): Promise<LibraryItem> {
    return request(`/library/items/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
  },
  remove(id: number): Promise<{ ok: boolean }> {
    return request(`/library/items/${id}`, { method: 'DELETE' });
  },
  bulkLicense(ids: number[], license: License): Promise<{ updated: number }> {
    return request('/library/items/bulk-license', { method: 'POST', body: JSON.stringify({ ids, license }) });
  },
  link(id: number, to_type: RelatedRef['type'], to_id: number): Promise<{ ok: boolean }> {
    return request(`/library/items/${id}/links`, { method: 'POST', body: JSON.stringify({ to_type, to_id }) });
  },
  unlink(linkId: number): Promise<{ ok: boolean }> {
    return request(`/library/links/${linkId}`, { method: 'DELETE' });
  },
  boards(): Promise<{ items: Board[] }> {
    return request('/library/boards');
  },
  createBoard(name: string): Promise<{ id: number; name: string }> {
    return request('/library/boards', { method: 'POST', body: JSON.stringify({ name }) });
  },
  addToBoard(boardId: number, item_ids: number[]): Promise<{ added: number }> {
    return request(`/library/boards/${boardId}/items`, { method: 'POST', body: JSON.stringify({ item_ids }) });
  },
  removeFromBoard(boardId: number, itemId: number): Promise<{ ok: boolean }> {
    return request(`/library/boards/${boardId}/items/${itemId}`, { method: 'DELETE' });
  },
  inbox(): Promise<{ path: string | null; imported_dir: string }> {
    return request('/library/inbox');
  },
  setInbox(path: string | null): Promise<{ path: string | null }> {
    return request('/library/inbox', { method: 'PUT', body: JSON.stringify({ path }) });
  },
  scanInbox(): Promise<{ imported: number; failed: number }> {
    return request('/library/inbox/scan', { method: 'POST' });
  },
  notes(params: { tag?: string; q?: string; linked_type?: string; linked_id?: number; before?: string; days?: number } = {}): Promise<{
    days: { date: string; notes: NoteView[] }[];
    tags: [string, number][];
    total: number;
  }> {
    return request(`/notes${qs(params)}`);
  },
  createNote(body: string, image_item_ids?: number[]): Promise<NoteView & { related: NoteRelated }> {
    return request('/notes', { method: 'POST', body: JSON.stringify({ body, image_item_ids }) });
  },
  updateNote(id: number, body: string): Promise<NoteView> {
    return request(`/notes/${id}`, { method: 'PATCH', body: JSON.stringify({ body }) });
  },
  deleteNote(id: number): Promise<{ ok: boolean }> {
    return request(`/notes/${id}`, { method: 'DELETE' });
  },
  noteAudio(id: number, blob: Blob): Promise<NoteView & { transcript_error?: string }> {
    const form = new FormData();
    form.append('file', blob, 'voice.webm');
    return request(`/notes/${id}/audio`, { method: 'POST', body: form, timeoutMs: 180_000 });
  },
  noteImage(file: File): Promise<LibraryItem> {
    const form = new FormData();
    form.append('file', file, file.name || 'paste.png');
    return request('/notes/images', { method: 'POST', body: form });
  },
  templates(mine = false): Promise<{ items: StyleEntry<TemplateVersion>[] }> {
    return request(`/templates${mine ? '?mine=true' : ''}`);
  },
  styles(mine = false): Promise<{ items: StyleEntry<StyleVersion>[] }> {
    return request(`/styles${mine ? '?mine=true' : ''}`);
  },
  style(key: string): Promise<StyleEntry<StyleVersion>> {
    return request(`/styles/${encodeURIComponent(key)}`);
  },
  template(key: string): Promise<StyleEntry<TemplateVersion>> {
    return request(`/templates/${encodeURIComponent(key)}`);
  },
  distill(kind: 'style' | 'template', name: string, item_ids?: number[]): Promise<StyleEntry<unknown> & { reference_count: number }> {
    return request(`/${kind === 'style' ? 'styles' : 'templates'}/distill`, { method: 'POST', body: JSON.stringify({ name, item_ids }), timeoutMs: 120_000 });
  },
  copy(kind: 'style' | 'template', key: string): Promise<StyleEntry<unknown>> {
    return request(`/${kind === 'style' ? 'styles' : 'templates'}/${encodeURIComponent(key)}/copy`, { method: 'POST' });
  },
  addVersion(kind: 'style' | 'template', key: string, body: Record<string, unknown> & { name: string }): Promise<StyleEntry<unknown>> {
    return request(`/${kind === 'style' ? 'styles' : 'templates'}/${encodeURIComponent(key)}/versions`, { method: 'POST', body: JSON.stringify(body) });
  },
  create(kind: 'style' | 'template', body: Record<string, unknown> & { name: string }): Promise<StyleEntry<unknown>> {
    return request(`/${kind === 'style' ? 'styles' : 'templates'}`, { method: 'POST', body: JSON.stringify(body) });
  },
  extensionPing(): Promise<Record<string, unknown>> {
    return request('/library/extension/ping');
  },
  migrateFavorites(): Promise<Record<string, number>> {
    return request('/library/migrate-favorites', { method: 'POST', timeoutMs: 120_000 });
  },
  archive(kind: 'style' | 'template', key: string): Promise<{ ok: boolean }> {
    return request(`/${kind === 'style' ? 'styles' : 'templates'}/${encodeURIComponent(key)}`, { method: 'DELETE' });
  },
};

export const LICENSE_LABEL: Record<License, string> = { own: '自有', commercial: '可商用', reference: '仅参考', unknown: '未知', ai: 'AI 生成' };
export const KIND_LABEL: Record<string, string> = {
  article: '文章',
  video: '视频',
  image: '图文',
  post: '帖子',
  prompt: '提示词',
  repo: '仓库',
  asset: '素材',
  generated: '生成图',
  link: '链接',
};
export const ASSET_LABEL: Record<AssetKind, string> = {
  image: '图片',
  palette: '配色',
  font: '字体',
  icon: '图标贴纸',
  texture: '纹理',
  motion: '动图视频',
  audio: '音乐音效',
};
