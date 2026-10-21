/** 创作工作台（阶段 4）：项目、来源、设定、文稿工作副本、版本、AI 建议、产出物、素材。 */
import type { PublishSchedule } from './_publishing';
import { BASE_URL, request } from './_core';

export type ProjectMode = 'article' | 'video_prompt' | 'animation_video' | 'music_video';
export type ProjectStage = 'idea' | 'draft' | 'outputs';
export type ProjectStatus = 'draft' | 'dirty' | 'finalized';
export type OutputKind = 'xhs' | 'zhihu' | 'wechat' | 'bilibili' | 'douyin' | 'video' | 'mv' | 'prompt_bundle';

export interface CopyBrief {
  theme: string;
  mode: ProjectMode;
  template_id: string | null;
  duration_seconds: number;
  audience: string;
  intent: string;
  tone: string;
}

export interface SourceSnapshot {
  kind: 'content' | 'library' | 'favorite';
  title: string | null;
  url: string | null;
  platform: string | null;
  author?: string | null;
  published_at: string | null;
  crawled_at: string | null;
  summary: string | null;
  cover_url: string | null;
  media_type?: string | null;
  metrics: Record<string, number | string>;
}

export interface ProjectSource {
  id: number;
  role: 'main' | 'reference';
  content_id: number | null;
  library_item_id: number | null;
  ref: string;
  snapshot: SourceSnapshot;
  added_at: string;
}

export interface ProjectSummary {
  id: number;
  title: string;
  theme: string;
  mode: ProjectMode;
  stage: ProjectStage;
  version: number;
  finalized_version: number | null;
  status: ProjectStatus;
  dirty: boolean;
  archived: boolean;
  created_at: string;
  updated_at: string;
  outputs?: number;
  main_source?: { title: string | null; cover_url: string | null; platform: string | null } | null;
}

export interface IdeaState {
  run_id?: number;
  chosen?: string | null;
  custom?: string;
}

export interface ProjectView extends ProjectSummary {
  brief: CopyBrief;
  idea: IdeaState;
  ai_draft?: { run_id?: number; status?: string; reason?: string | null };
  platform_rewrite?: { run_id?: number; status?: string; reason?: string | null; kinds?: string[] };
  pipeline?: PipelineView;
  sources: ProjectSource[];
  running_tasks: number;
  draft_token: string | null;
}

export interface Shot {
  seconds: number;
  beat: string;
  visual: string;
  camera: string;
  audio: string;
  transition: string;
  caption: string;
  prompt: string;
}

export interface Draft {
  title: string;
  logline: string;
  body: string;
  shots: Shot[];
  cues: { time: number; text: string }[];
  provenance: 'manual' | 'compiled' | 'ai';
}

export interface ProjectAudio {
  id: number;
  name: string;
  duration: number | null;
  url: string;
}

export interface Paragraph {
  id: string;
  text: string;
}

export interface DraftView {
  brief: CopyBrief;
  draft: Draft;
  paragraphs: Paragraph[];
  template: Record<string, unknown> | null;
  draft_token: string | null;
  version: number;
  finalized_version: number | null;
  dirty: boolean;
  updated_at: string;
}

export interface VersionItem {
  version: number;
  reason: string;
  created_at: string;
  finalized: boolean;
}

export interface VersionView {
  version: number;
  reason: string;
  created_at: string;
  brief: CopyBrief;
  draft: Draft;
  paragraphs: Paragraph[];
}

export type SuggestionOp =
  | { op_id: string; op: 'replace_paragraph' | 'insert_after'; id: string; text: string; reason?: string }
  | { op_id: string; op: 'delete_paragraph'; id: string; reason?: string }
  | { op_id: string; op: 'update_shot'; index: number; field: keyof Shot; value: string | number; reason?: string }
  | { op_id: string; op: 'insert_shot'; after: number; shot: Shot; reason?: string }
  | { op_id: string; op: 'delete_shot'; index: number; reason?: string }
  | { op_id: string; op: 'move_shot'; from: number; to: number; reason?: string };

export interface SuggestionScope {
  type: 'all' | 'paragraphs' | 'shots';
  ids?: string[];
  indexes?: number[];
  quick?: string | null;
}

export interface Suggestion {
  id: number;
  project_id: number;
  scope: SuggestionScope;
  instructions: string;
  ops: SuggestionOp[];
  status: 'pending' | 'applied' | 'partial' | 'rejected';
  applied_ops: string[];
  model: string | null;
  cost: number | null;
  created_at: string;
  conflicts?: string[];
}

export interface PlatformContent {
  title?: string;
  body?: string;
  tags?: string[];
  cover_text?: string;
  hook?: string;
  summary?: string;
  image_suggestions?: string[];
  warnings?: string[];
  model?: string | null;
}

export interface OutputArtifact {
  id: number;
  version: number;
  kind: string;
  status: string;
  progress: Record<string, unknown>;
  created_at: string | null;
  download_path: string | null;
  preview_path: string | null;
  source_path: string | null;
  error: string | null;
  settings: Record<string, unknown> | null;
}

export interface OutputView {
  id: number;
  project_id: number;
  kind: OutputKind;
  title: string;
  status: 'draft' | 'rendering' | 'done' | 'failed' | 'exported' | 'published';
  based_on_version: number | null;
  latest_finalized: number | null;
  stale: boolean;
  content: PlatformContent & Record<string, unknown>;
  settings: Record<string, unknown>;
  published_url: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  can_start: boolean;
  artifacts?: OutputArtifact[];
}

export interface ProjectAsset {
  id: number;
  role: 'moodboard' | 'illustration' | 'cover' | 'keyframe' | 'bgm';
  target: Record<string, unknown> | null;
  library_item_id: number;
  added_at: string;
  item: {
    id: number;
    kind: string;
    asset_kind: string | null;
    title: string;
    thumb: boolean;
    color: string | null;
    license: string;
    body: string | null;
  } | null;
}

export type ApiError = Error & { status?: number; code?: string; data?: Record<string, unknown> };

const j = (body: unknown) => JSON.stringify(body);

export type PipelineStage = 'research' | 'draft' | 'awaiting_finalize' | 'producing' | 'done' | 'failed' | 'stopped';
export interface PipelineView {
  stage?: PipelineStage;
  stage_label?: string;
  outputs?: string[];
  gates?: { choose?: boolean; accept?: boolean };
  runs?: { research?: number; draft?: number; produce?: number[]; platforms?: number };
  direction?: { title: string; intent?: string };
  reason?: string | null;
  problems?: string[];
  partial?: boolean;
}

export interface Delivery {
  artifact_id: number;
  source: 'upload' | 'agent' | string;
  source_label: string;
  file_name: string;
  size: number;
  duration: number | null;
  note: string | null;
  at: string;
}

export interface WorkItem {
  key: string;
  type: 'output' | 'legacy';
  id: number;
  kind: string;
  title: string;
  status: string;
  based_on_version: number | null;
  excerpt: string;
  chars: number | null;
  copy_text: string | null;
  cover: string | null;
  preview_path: string | null;
  download_path: string | null;
  published_url: string | null;
  schedule?: PublishSchedule | null;
  metrics?: Record<string, number>;
  manual: boolean;
  href: string;
  updated_at: string | null;
}
export interface WorksView {
  groups: { project: { id: number; title: string; archived: boolean }; items: WorkItem[] }[];
  total: number;
}

/** 作品库收录规则（与后端 works_service.included 一致） */
export function inWorks(o: Pick<OutputView, 'status' | 'settings'>): boolean {
  const flag = o.settings?.in_works;
  if (flag === false) return false;
  return flag === true || ['done', 'exported', 'published'].includes(o.status);
}

export const projectsApi = {
  list(params: { stage?: ProjectStage; q?: string; archived?: boolean } = {}): Promise<{ items: ProjectSummary[] }> {
    const sp = new URLSearchParams();
    if (params.stage) sp.set('stage', params.stage);
    if (params.q) sp.set('q', params.q);
    if (params.archived) sp.set('archived', 'true');
    const q = sp.toString();
    return request(`/projects${q ? `?${q}` : ''}`);
  },
  create(body: { theme?: string; mode?: ProjectMode; sources?: string[]; intent?: string }): Promise<ProjectView> {
    return request('/projects', { method: 'POST', body: j(body) });
  },
  get(id: number): Promise<ProjectView> {
    return request(`/projects/${id}`);
  },
  rename(id: number, title: string): Promise<ProjectView> {
    return request(`/projects/${id}`, { method: 'PATCH', body: j({ title }) });
  },
  duplicate(id: number): Promise<{ id: number } & Record<string, unknown>> {
    return request(`/projects/${id}/duplicate`, { method: 'POST' });
  },
  batch(ids: number[], action: 'archive' | 'unarchive' | 'delete'): Promise<{ done: number; skipped: number[]; missing: number[] }> {
    return request('/projects/batch', { method: 'POST', body: JSON.stringify({ ids, action }) });
  },
  archive(id: number, restore = false): Promise<ProjectSummary> {
    return request(`/projects/${id}/archive${restore ? '?restore=true' : ''}`, { method: 'POST' });
  },
  addSource(id: number, body: { content_id?: number; library_item_id?: number; role: 'main' | 'reference' }): Promise<ProjectSource> {
    return request(`/projects/${id}/sources`, { method: 'POST', body: j(body) });
  },
  setSourceRole(id: number, sid: number, role: 'main' | 'reference'): Promise<ProjectSource> {
    return request(`/projects/${id}/sources/${sid}`, { method: 'PATCH', body: j({ role }) });
  },
  removeSource(id: number, sid: number): Promise<void> {
    return request(`/projects/${id}/sources/${sid}`, { method: 'DELETE' });
  },
  saveBrief(id: number, brief: CopyBrief, idea?: IdeaState, draft_token?: string | null): Promise<ProjectView> {
    return request(`/projects/${id}/brief`, { method: 'PUT', body: j({ brief, idea, draft_token: draft_token ?? undefined }) });
  },
  directions(id: number): Promise<{ run_id: number }> {
    return request(`/projects/${id}/directions`, { method: 'POST', timeoutMs: 60_000 });
  },
  draft(id: number): Promise<DraftView> {
    return request(`/projects/${id}/draft`);
  },
  saveDraft(id: number, draft: Draft, draft_token: string | null, force = false): Promise<{ draft_token: string; version: number; saved_at: string }> {
    return request(`/projects/${id}/draft`, { method: 'PUT', body: j({ draft, draft_token, force }) });
  },
  generate(id: number, mode: 'blank' | 'template'): Promise<DraftView> {
    return request(`/projects/${id}/draft/generate`, { method: 'POST', body: j({ mode }), timeoutMs: 120_000 });
  },
  /** AI 写初稿：启动成稿流程（写手 → 审校 → 写手修改），返回运行 id */
  aiDraft(id: number): Promise<{ run_id: number; status: string }> {
    return request(`/projects/${id}/draft/generate`, { method: 'POST', body: j({ mode: 'ai' }), timeoutMs: 60_000 });
  },
  /** 一键全流程：选题研究 → 成稿 →〔定稿〕→ 讲解视频 + 平台改写 */
  startPipeline(id: number, body: { outputs: string[]; choose_gate: boolean; accept_gate: boolean }): Promise<PipelineView> {
    return request(`/projects/${id}/pipeline`, { method: 'POST', body: j(body), timeoutMs: 60_000 });
  },
  stopPipeline(id: number): Promise<PipelineView> {
    return request(`/projects/${id}/pipeline/stop`, { method: 'POST' });
  },
  /** 生成平台版本：启动平台改写流程（平台编辑按平台并行 → 规则校验），返回运行 id */
  rewritePlatforms(id: number, kinds: string[], outputIds: Record<string, number> = {}): Promise<{ run_id: number; status: string }> {
    return request(`/projects/${id}/platforms/rewrite`, { method: 'POST', body: j({ kinds, output_ids: outputIds }), timeoutMs: 60_000 });
  },
  /** 讲解视频 / MV：启动成片流程（分镜 → 美术 → 制作 → 质检） */
  render(oid: number): Promise<{ run_id: number; output: OutputView }> {
    return request(`/outputs/${oid}/render`, { method: 'POST', timeoutMs: 60_000 });
  },
  executors(): Promise<{ items: { key: string; label: string; available: boolean; hint: string | null }[] }> {
    return request('/production/executors');
  },
  versions(id: number): Promise<{ finalized_version: number | null; items: VersionItem[] }> {
    return request(`/projects/${id}/versions`);
  },
  saveVersion(id: number, reason = 'manual'): Promise<{ version: number; draft_token: string }> {
    return request(`/projects/${id}/versions`, { method: 'POST', body: j({ reason }) });
  },
  version(id: number, v: number): Promise<VersionView> {
    return request(`/projects/${id}/versions/${v}`);
  },
  restore(id: number, v: number): Promise<{ version: number; draft_token: string }> {
    return request(`/projects/${id}/versions/${v}/restore`, { method: 'POST' });
  },
  finalize(id: number): Promise<ProjectView> {
    return request(`/projects/${id}/finalize`, { method: 'POST', body: j({}) });
  },
  unlock(id: number): Promise<ProjectView> {
    return request(`/projects/${id}/unlock`, { method: 'POST' });
  },
  suggest(id: number, body: { scope: SuggestionScope; instructions?: string; quick?: string; n?: number; draft_token?: string | null }): Promise<Suggestion> {
    return request(`/projects/${id}/suggestions`, { method: 'POST', body: j(body), timeoutMs: 180_000 });
  },
  suggestions(id: number): Promise<{ items: Suggestion[] }> {
    return request(`/projects/${id}/suggestions`);
  },
  applySuggestion(sid: number, op_ids?: string[]): Promise<Suggestion & { draft: DraftView; version: number; draft_token: string }> {
    return request(`/suggestions/${sid}/apply`, { method: 'POST', body: j({ op_ids }) });
  },
  rejectSuggestion(sid: number): Promise<Suggestion> {
    return request(`/suggestions/${sid}/reject`, { method: 'POST' });
  },
  outputs(id: number): Promise<{ finalized_version: number | null; items: OutputView[] }> {
    return request(`/projects/${id}/outputs`);
  },
  createOutput(id: number, kind: OutputKind): Promise<OutputView> {
    return request(`/projects/${id}/outputs`, { method: 'POST', body: j({ kind }) });
  },
  output(oid: number): Promise<OutputView> {
    return request(`/outputs/${oid}`);
  },
  works(params: { q?: string; kind?: string; project?: number } = {}): Promise<WorksView> {
    const sp = new URLSearchParams();
    if (params.q) sp.set('q', params.q);
    if (params.kind) sp.set('kind', params.kind);
    if (params.project) sp.set('project', String(params.project));
    const q = sp.toString();
    return request(`/works${q ? `?${q}` : ''}`);
  },
  /** 音乐 MV：项目音频（最新一条） */
  audio(pid: number): Promise<{ audio: ProjectAudio | null }> {
    return request(`/projects/${pid}/audio`);
  },
  uploadAudio(pid: number, file: File): Promise<{ audio: ProjectAudio; draft: DraftView }> {
    const form = new FormData();
    form.append('file', file, file.name);
    return request(`/projects/${pid}/audio`, { method: 'POST', body: form, timeoutMs: 300_000 });
  },
  audioUrl(audio: ProjectAudio): string {
    return `${BASE_URL}${audio.url}`;
  },
  /** LRC 歌词：歌词时间的唯一来源 */
  setLrc(pid: number, text: string): Promise<DraftView> {
    return request(`/projects/${pid}/lrc`, { method: 'PUT', body: JSON.stringify({ text }) });
  },
  /** 回传成片：上传外部 agent 做好的视频 */
  uploadDelivery(oid: number, file: File, note?: string): Promise<{ delivery: Delivery; output: OutputView }> {
    const form = new FormData();
    form.append('file', file, file.name);
    if (note) form.append('note', note);
    return request(`/outputs/${oid}/deliveries`, { method: 'POST', body: form, timeoutMs: 1_800_000 });
  },
  setInWorks(oid: number, value: boolean): Promise<OutputView> {
    return request(`/outputs/${oid}/works`, { method: value ? 'POST' : 'DELETE' });
  },
  patchOutput(oid: number, body: { title?: string; content?: Record<string, unknown>; settings?: Record<string, unknown>; published_url?: string; status?: string }): Promise<OutputView> {
    return request(`/outputs/${oid}`, { method: 'PATCH', body: j(body) });
  },
  deleteOutput(oid: number): Promise<void> {
    return request(`/outputs/${oid}`, { method: 'DELETE' });
  },
  generateOutput(oid: number): Promise<OutputView> {
    return request(`/outputs/${oid}/generate`, { method: 'POST', timeoutMs: 180_000 });
  },
  bundleUrl(oid: number, format: 'md' | 'zip'): string {
    return `${BASE_URL}/outputs/${oid}/bundle?format=${format}`;
  },
  exportUrl(oid: number, format: 'md' | 'html'): string {
    return `${BASE_URL}/outputs/${oid}/export?format=${format}`;
  },
  async bundleMarkdown(oid: number): Promise<string> {
    const res = await fetch(`${BASE_URL}/outputs/${oid}/bundle?format=md`, { credentials: 'include' });
    if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.error || '导出失败');
    return res.text();
  },
  assets(id: number, role?: string): Promise<{ items: ProjectAsset[] }> {
    return request(`/projects/${id}/assets${role ? `?role=${role}` : ''}`);
  },
  addAsset(id: number, library_item_id: number, role: ProjectAsset['role'] = 'moodboard'): Promise<ProjectAsset> {
    return request(`/projects/${id}/assets`, { method: 'POST', body: j({ library_item_id, role }) });
  },
  removeAsset(id: number, aid: number): Promise<void> {
    return request(`/projects/${id}/assets/${aid}`, { method: 'DELETE' });
  },
};
