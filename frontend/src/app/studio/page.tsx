'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  CheckCircle2,
  ChevronRight,
  CirclePlay,
  Copy,
  Download,
  Eye,
  FileAudio,
  FileText,
  Film,
  FolderOpen,
  History,
  Music2,
  PenLine,
  Plus,
  Save,
  Sparkles,
  RefreshCw,
  X,
  WandSparkles,
} from 'lucide-react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Divider,
  Empty,
  Input,
  List,
  Modal,
  Select,
  Space,
  Steps,
  Tag,
  Tabs,
  Typography,
  message,
} from 'antd';
import type { ContentItem } from '@/types';
import type { FavoriteItem } from '@/types';
import type { StudioArtifact, StudioBrief, StudioCatalog, StudioDraft, StudioProject, StudioShot } from '@/lib/api';
import { contentsApi, favoritesApi, studioApi } from '@/lib/api';
import { CreativePresetCard } from '@/components/CreativePresetCard';
import type { CreativePreset } from '@/components/CreativePresetCard';
import { ArtifactProgress } from '@/components/ProductionStatus';
import DraftComparison from '@/components/DraftComparison';
import StudioVoice from '@/components/StudioVoice';

const { Title, Text } = Typography;

const defaultBrief: StudioBrief = {
  theme: '',
  mode: 'animation_video',
  template_id: null,
  style_id: null,
  presentation: 'kinetic',
  production: 'code_animation',
  duration_seconds: 180,
  aspect_ratio: '16:9',
  audience: '',
  intent: '',
  bilingual: false,
};

const modeOptions = [
  { value: 'animation_video', label: '动画讲解', description: '旁白 + 图形动画分镜 + 可播放动画视频' },
  { value: 'video_prompt', label: '普通视频', description: '旁白 / 脚本 + 镜头分镜 + 视频模型提示词' },
  { value: 'music_video', label: '音乐 MV', description: '歌曲 / LRC + 段落节奏 + MV 画面' },
  { value: 'article', label: '文章成稿', description: '完整文章正文 · Markdown 文档' },
] as const;

function modeDescription(mode: StudioBrief['mode']): string {
  return modeOptions.find((item) => item.value === mode)?.description ?? '';
}

function productionOptions(mode: StudioBrief['mode']) {
  if (mode === 'music_video') {
    return [
      { value: 'native_mv', label: '歌词可视化' },
      { value: 'code_animation', label: 'DeepSeek 动画制作' },
    ];
  }
  if (mode === 'video_prompt' || mode === 'animation_video') {
    return [
      { value: 'code_animation', label: 'DeepSeek 动画制作' },
      { value: 'video_model', label: '导出分镜提示词' },
    ];
  }
  return [];
}

function modeLabel(mode: StudioBrief['mode']): string {
  return modeOptions.find((item) => item.value === mode)?.label ?? mode;
}

function productionLabel(production: StudioBrief['production']): string {
  if (production === 'native_mv') return '歌词可视化';
  if (production === 'code_animation') return 'DeepSeek · Remotion';
  if (production === 'video_model') return '导出分镜提示词';
  return '由创作者决定';
}

const stageItems = [
  { title: '选题', icon: <FileText size={16} /> },
  { title: '成稿', icon: <PenLine size={16} /> },
  { title: '成片', icon: <Film size={16} /> },
];

function patchShot(draft: StudioDraft, index: number, key: keyof StudioShot, value: string | number): StudioDraft {
  return { ...draft, shots: draft.shots.map((shot, shotIndex) => shotIndex === index ? { ...shot, [key]: value } : shot) };
}

function sourceTitle(project: StudioProject | null): string {
  return typeof project?.source?.title === 'string' ? project.source.title : '手动选题';
}

function formatTimecode(seconds: number): string {
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  const rest = safe - minutes * 60;
  return `${String(minutes).padStart(2, '0')}:${rest.toFixed(3).padStart(6, '0')}`;
}

function draftText(draft: StudioDraft): string {
  return [draft.title, draft.logline, draft.body, ...draft.shots.map((shot, index) => `镜头 ${index + 1} · ${shot.beat}\n${shot.visual}\n${shot.prompt}`)].filter(Boolean).join('\n\n');
}

export default function StudioPage() {
  const [catalog, setCatalog] = useState<StudioCatalog | null>(null);
  const [items, setItems] = useState<ContentItem[]>([]);
  const [favoriteItems, setFavoriteItems] = useState<FavoriteItem[]>([]);
  const [projects, setProjects] = useState<StudioProject[]>([]);
  const [selectedId, setSelectedId] = useState<number>();
  const [brief, setBrief] = useState<StudioBrief>(defaultBrief);
  const [project, setProject] = useState<StudioProject | null>(null);
  const [stage, setStage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [topicsLoading, setTopicsLoading] = useState(true);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string>();
  const [prompt, setPrompt] = useState('');
  const [renderId, setRenderId] = useState<number>();
  const [audioName, setAudioName] = useState('');
  const [revisionInstructions, setRevisionInstructions] = useState('');
  const [productionJobs, setProductionJobs] = useState<StudioArtifact[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [comparison, setComparison] = useState<{ version: number; draft: StudioDraft }>();
  const [inlineComparison, setInlineComparison] = useState<{ before: StudioDraft; after: StudioDraft; version: number }>();
  const restored = useRef(false);
  const [presetModal, setPresetModal] = useState<'template' | 'style' | null>(null);
  const [presetCategory, setPresetCategory] = useState('全部');
  const [presetKeyword, setPresetKeyword] = useState('');
  const audioInput = useRef<HTMLInputElement>(null);
  const lrcInput = useRef<HTMLInputElement>(null);

  const selected = useMemo(() => items.find((item) => item.id === selectedId), [items, selectedId]);
  const selectedFavorite = useMemo(
    () => favoriteItems.find((item) => -item.id === selectedId),
    [favoriteItems, selectedId],
  );
  const templates = catalog?.templates ?? [];
  const styles = catalog?.styles ?? [];
  const presetOptions = presetModal === 'template'
    ? templates.filter((item) => item.modes.includes(brief.mode))
    : styles;
  const presetCategories = ['全部', ...Array.from(new Set(presetOptions.map((item) => item.category).filter(Boolean)))];
  const visiblePresets = presetOptions.filter((item) => (
    (presetCategory === '全部' || item.category === presetCategory)
    && `${item.name} ${item.description}`.toLowerCase().includes(presetKeyword.trim().toLowerCase())
  ));
  const audioAsset = project?.assets.find((asset) => asset.kind === 'audio');

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const options = { signal: controller.signal, timeoutMs: 10000 };
    const fail = (label: string, err: unknown) => {
      if (!cancelled) setError((current) => [
        current, `${label}：${err instanceof Error ? err.message : '加载失败'}`,
      ].filter(Boolean).join('；'));
    };
    setLoading(true);
    setTopicsLoading(true);
    setError(undefined);
    void studioApi.catalog(options)
      .then((value) => { if (!cancelled) setCatalog(value); })
      .catch((err) => fail('模板与风格', err))
      .finally(() => { if (!cancelled) setLoading(false); });
    void contentsApi.list({ page: 1, page_size: 40, hours: 168 }, options)
      .then((value) => { if (!cancelled) setItems(value.items ?? []); })
      .catch((err) => fail('选题', err))
      .finally(() => { if (!cancelled) setTopicsLoading(false); });
    void favoritesApi.list({ page: 1, page_size: 200 }, options)
      .then((value) => { if (!cancelled) setFavoriteItems(value.items ?? []); })
      .catch((err) => fail('收藏资产', err));
    void studioApi.listProjects(options)
      .then((value) => { if (!cancelled) setProjects(value.items ?? []); })
      .catch((err) => fail('创作历史', err));
    void studioApi.jobs()
      .then((value) => { if (!cancelled) setProductionJobs(value.items ?? []); })
      .catch((err) => fail('制作任务', err));
    return () => { cancelled = true; controller.abort(); };
  }, [loadAttempt]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedContentId = Number(params.get('content_id'));
    const requestedFavoriteId = Number(params.get('favorite_id'));
    const requestedTemplateId = params.get('template_id');
    const requestedStyleId = params.get('style_id');
    if (requestedTemplateId || requestedStyleId) {
      setBrief((current) => ({
        ...current,
        template_id: requestedTemplateId || current.template_id,
        style_id: requestedStyleId || current.style_id,
      }));
    }
    const favorite = favoriteItems.find((item) => item.id === requestedFavoriteId);
    if (favorite) {
      setSelectedId(-requestedFavoriteId);
      setBrief((current) => ({ ...current, theme: current.theme || favorite.title }));
      return;
    }
    if (requestedContentId > 0 && items.some((item) => item.id === requestedContentId)) {
      setSelectedId(requestedContentId);
    }
  }, [favoriteItems, items]);

  useEffect(() => {
    if (restored.current || !projects.length) return;
    restored.current = true;
    const params = new URLSearchParams(window.location.search);
    if (['favorite_id', 'content_id', 'style_id', 'template_id'].some((key) => params.has(key))) return;
    let saved: { project_id?: number; stage?: number } = {};
    try { saved = JSON.parse(localStorage.getItem('creative-studio:open-project') || '{}'); } catch {}
    const id = Number(params.get('project_id')) || saved.project_id;
    const next = projects.find((item) => item.id === id);
    if (next) {
      setProject(next);
      setBrief(next.brief);
      setInlineComparison(next.previous_revision ? { before: next.previous_revision.draft, after: next.draft, version: next.version } : undefined);
      setAudioName(next.assets.find((asset) => asset.kind === 'audio')?.name || '');
      setStage(Number(params.get('stage')) || saved.stage || (next.finalized_version ? 2 : 1));
    }
  }, [projects]);

  useEffect(() => {
    if (project) localStorage.setItem('creative-studio:open-project', JSON.stringify({ project_id: project.id, stage }));
  }, [project?.id, stage]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void studioApi.jobs().then((value) => {
        setProductionJobs(value.items ?? []);
        setProject((current) => {
          if (!current) return current;
          const projectJobs = (value.items ?? []).filter((job) => job.project_id === current.id);
          if (!projectJobs.length) return current;
          const artifacts = [...current.artifacts];
          for (const job of projectJobs) {
            const index = artifacts.findIndex((item) => item.id === job.id);
            if (index >= 0) artifacts[index] = job;
            else artifacts.unshift(job);
          }
          return { ...current, artifacts };
        });
      }).catch(() => {});
    }, 2500);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!renderId) return;
    const timer = window.setInterval(() => {
      void studioApi.artifact(renderId).then((artifact) => {
        if (artifact.status !== 'done' && artifact.status !== 'error') return;
        window.clearInterval(timer);
        setProject((current) => current ? {
          ...current,
          artifacts: current.artifacts.map((item) => item.id === renderId ? { ...item, ...artifact } : item),
        } : current);
        if (artifact.status === 'done') {
          setError(undefined);
          message.success('成片已完成');
        }
        else setError(artifact.error ?? '渲染失败');
      }).catch(() => {});
    }, 2000);
    return () => window.clearInterval(timer);
  }, [renderId]);

  const setBriefField = <K extends keyof StudioBrief>(key: K, value: StudioBrief[K]) => {
    setBrief((current) => ({ ...current, [key]: value }));
  };

  const openPresetPicker = (kind: 'template' | 'style') => {
    setPresetCategory('全部');
    setPresetKeyword('');
    setPresetModal(kind);
    void studioApi.catalog().then(setCatalog).catch((err) => setError(err instanceof Error ? err.message : '收藏加载失败'));
  };

  const create = async () => {
    const theme = brief.theme.trim() || selected?.title?.trim() || selectedFavorite?.title?.trim();
    if (!theme) {
      setError('先选择选题或填写主题');
      return;
    }
    setWorking(true);
    setError(undefined);
    try {
      const next = await studioApi.createProject({
        brief: {
          ...brief,
          theme,
        },
        content_id: selectedFavorite?.target_type === 'content' ? selectedFavorite.target_id ?? selected?.id : selected?.id,
        favorite_id: selectedFavorite?.id,
      });
      setProject(next);
      setBrief(next.brief);
      setInlineComparison(undefined);
      setRevisionInstructions('');
      setStage(1);
      setProjects((current) => [next, ...current.filter((item) => item.id !== next.id)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建工程失败');
    } finally {
      setWorking(false);
    }
  };

  const loadProject = async (id: number) => {
    setWorking(true);
    try {
      const next = await studioApi.getProject(id);
      setProject(next);
      setBrief(next.brief);
      setInlineComparison(next.previous_revision ? { before: next.previous_revision.draft, after: next.draft, version: next.version } : undefined);
      setStage(next.finalized_version ? 2 : 1);
      const active = next.artifacts.find((item) => item.status === 'queued' || item.status === 'rendering');
      if (active) setRenderId(active.id);
      setAudioName(next.assets.find((asset) => asset.kind === 'audio')?.name ?? '');
    } catch (err) {
      setError(err instanceof Error ? err.message : '工程加载失败');
    } finally {
      setWorking(false);
    }
  };

  const save = async () => {
    if (!project) return;
    setWorking(true);
    try {
      const next = await studioApi.saveProject(project.id, {
        expected_version: project.version,
        brief,
        draft: project.draft,
      });
      setProject(next);
      setBrief(next.brief);
      setProjects((current) => current.map((item) => item.id === next.id ? next : item));
      message.success('已保存新版本');
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setWorking(false);
    }
  };

  const compile = async (engine: 'rules' | 'ai', action: 'generate' | 'refine' = 'generate') => {
    if (!project) return;
    const beforeDraft = project.draft;
    setWorking(true);
    try {
      const saved = await studioApi.saveProject(project.id, {
        expected_version: project.version,
        brief,
        draft: project.draft,
      });
      setProject(saved);
      const next = await studioApi.generateDraft(saved.id, saved.version, engine, action, revisionInstructions);
      setProject(next);
      setBrief(next.brief);
      setProjects((current) => current.map((item) => item.id === next.id ? next : item));
      setInlineComparison(beforeDraft.body || beforeDraft.shots.length
        ? { before: beforeDraft, after: next.draft, version: next.version }
        : undefined);
      setRevisionInstructions('');
      message.success(engine === 'ai' ? 'AI 成稿已生成，可继续编辑' : '已生成规则草稿');
    } catch (err) {
      setError(err instanceof Error ? err.message : '编稿失败');
    } finally {
      setWorking(false);
    }
  };

  const updateMode = (mode: StudioBrief['mode']) => {
    setBrief((current) => ({
      ...current,
      mode,
      template_id: current.template_id && templates.find((item) => item.id === current.template_id)?.modes.includes(mode) ? current.template_id : null,
      presentation: mode === 'article' ? null : mode === 'animation_video' ? 'kinetic' : 'cinematic',
      production: mode === 'article' ? null : mode === 'music_video' ? 'native_mv' : 'code_animation',
    }));
  };

  const adoptComparison = async () => {
    if (!project || !comparison) return;
    setWorking(true);
    try {
      const next = await studioApi.saveProject(project.id, { expected_version: project.version, brief, draft: comparison.draft });
      setProject(next);
      setComparison(undefined);
      setHistoryOpen(false);
      setStage(1);
      message.success('已采用此稿');
    } catch (err) { setError(err instanceof Error ? err.message : '版本保存失败'); }
    finally { setWorking(false); }
  };

  const openRevision = async (version: number) => {
    if (!project) return;
    try {
      const revision = await studioApi.revision(project.id, version);
      setComparison({ version: revision.version, draft: revision.draft });
    } catch (err) {
      setError(err instanceof Error ? err.message : '版本读取失败');
    }
  };

  const loadPrompt = async () => {
    if (!project) return;
    try {
      const result = await studioApi.productionPrompt(project.id);
      setPrompt(result.prompt);
    } catch (err) {
      setError(err instanceof Error ? err.message : '提示词生成失败');
    }
  };

  const uploadAudio = async (file: File) => {
    if (!project) return;
    setWorking(true);
    try {
      const asset = await studioApi.uploadAudio(project.id, file);
      setAudioName(asset.name);
      const next = await studioApi.getProject(project.id);
      setProject(next);
      setBrief(next.brief);
      message.success(`音频已加入，${asset.duration.toFixed(1)} 秒`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '音频上传失败');
    } finally {
      setWorking(false);
    }
  };

  const uploadLrc = async (file: File) => {
    if (!project) return;
    setWorking(true);
    try {
      const next = await studioApi.uploadLrc(project.id, file);
      setProject(next);
      setBrief(next.brief);
      message.success(`已解析 ${next.draft.cues.length} 条歌词`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'LRC 解析失败');
    } finally {
      setWorking(false);
    }
  };

  const finalize = async () => {
    if (!project) return;
    setWorking(true);
    try {
      const saved = await studioApi.saveProject(project.id, {
        expected_version: project.version,
        brief,
        draft: project.draft,
      });
      setProject(saved);
      const next = await studioApi.finalize(saved.id, saved.version);
      setProject(next);
      setStage(2);
      message.success('版本已确认');
    } catch (err) {
      setError(err instanceof Error ? err.message : '确认版本失败');
    } finally {
      setWorking(false);
    }
  };

  const render = async () => {
    if (!project) return;
    setError(undefined);
    setWorking(true);
    try {
      const result = await studioApi.render(project.id);
      setRenderId(result.artifact_id);
      setProductionJobs((current) => [{ id: result.artifact_id, project_id: project.id, version: project.version, kind: project.brief.production === 'native_mv' ? 'native_mv' : 'remotion_video', status: result.status, progress: { stage: '等待制作', percent: 0 }, preview_path: null, storage_path: null, download_path: null, error: null }, ...current.filter((item) => item.id !== result.artifact_id)]);
      setProject(await studioApi.getProject(project.id));
      message.info('已开始制作');
    } catch (err) {
      setError(err instanceof Error ? err.message : '制作失败');
    } finally {
      setWorking(false);
    }
  };

  const renderShots = () => {
    if (!project?.draft.shots.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="先生成分镜" />;
    const musicClock = brief.mode === 'music_video';
    const draftDuration = project.draft.shots.reduce((sum, shot) => sum + shot.seconds, 0);
    const timelineDuration = musicClock ? (audioAsset?.duration ?? project.brief.duration_seconds) : draftDuration;
    const timelineScale = musicClock && audioAsset?.duration && draftDuration > 0
      ? audioAsset.duration / draftDuration
      : 1;
    let cursor = 0;
    return (
      <div className="space-y-3">
        {project.draft.shots.map((shot, index) => (
          (() => {
            const start = cursor * timelineScale;
            cursor += shot.seconds;
            const end = Math.min(timelineDuration, cursor * timelineScale);
            return (
          <Card key={`${index}-${shot.beat}`} size="small" title={`段落 ${String(index + 1).padStart(2, '0')} · ${musicClock ? `${formatTimecode(start)} – ${formatTimecode(end)}` : `${shot.seconds}s`}`} extra={<Tag>{shot.beat}</Tag>}>
            <div className="grid gap-3 md:grid-cols-2">
              <Input.TextArea value={shot.visual} autoSize={{ minRows: 2, maxRows: 5 }} placeholder="画面" onChange={(event) => setProject((current) => current ? { ...current, draft: patchShot(current.draft, index, 'visual', event.target.value) } : current)} />
              <Input.TextArea value={shot.prompt} autoSize={{ minRows: 2, maxRows: 5 }} placeholder="视频生成提示词" onChange={(event) => setProject((current) => current ? { ...current, draft: patchShot(current.draft, index, 'prompt', event.target.value) } : current)} />
              <Input.TextArea value={shot.camera} autoSize={{ minRows: 2, maxRows: 4 }} placeholder="镜头与运动" onChange={(event) => setProject((current) => current ? { ...current, draft: patchShot(current.draft, index, 'camera', event.target.value) } : current)} />
              <Input.TextArea value={shot.audio} autoSize={{ minRows: 2, maxRows: 4 }} placeholder="音乐与音效" onChange={(event) => setProject((current) => current ? { ...current, draft: patchShot(current.draft, index, 'audio', event.target.value) } : current)} />
            </div>
          </Card>
            );
          })()
        ))}
      </div>
    );
  };

  const renderLyrics = () => {
    if (!project || brief.mode !== 'music_video') {
      return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无歌词" />;
    }
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Button icon={<FileAudio size={15} />} disabled={working} onClick={() => audioInput.current?.click()}>
            {audioName ? '更换歌曲音频' : '上传歌曲音频'}
          </Button>
          <Button icon={<Music2 size={15} />} disabled={working} onClick={() => lrcInput.current?.click()}>
            上传 LRC · {project.draft.cues.length} 条歌词
          </Button>
          <input ref={audioInput} type="file" accept=".mp3,.wav,.m4a,.ogg,.flac" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadAudio(file); event.currentTarget.value = ''; }} />
          <input ref={lrcInput} type="file" accept=".lrc,text/plain" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadLrc(file); event.currentTarget.value = ''; }} />
        </div>
        {project.assets.filter((asset) => asset.kind === 'audio').map((asset) => (
          <div key={asset.id} className="border-b border-gray-100 pb-3 text-xs text-gray-500">
            <span className="min-w-0 break-all">{asset.name} · {asset.duration?.toFixed(3) ?? '未知'} 秒</span>
          </div>
        ))}
        {project.draft.cues.length ? (
          <List size="small" dataSource={project.draft.cues} renderItem={(cue) => (
            <List.Item><Text code>{cue.time.toFixed(3)}s</Text><span>{cue.text}</span></List.Item>
          )} />
        ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无歌词" />}
      </div>
    );
  };

  if (loading) return <div className="p-10 text-sm text-gray-500">加载工作台…</div>;

  return (
    <div className="mx-auto max-w-[1560px] px-5 pb-12 pt-6 lg:px-8">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <Title level={2} className="!mb-1">创作工作台</Title>
          <Text type="secondary">选题 → 成稿 → 成片 → 作品</Text>
        </div>
        <Space>
          {project && <Tag color="blue">版本 {project.version}</Tag>}
          <Button icon={<History size={15} />} onClick={() => setHistoryOpen(true)}>创作历史</Button>
        </Space>
      </div>
      {error && <Alert className="mb-4" type="error" showIcon closable message={error} onClose={() => setError(undefined)}
        action={<Button size="small" icon={<RefreshCw size={14} />} onClick={() => setLoadAttempt((current) => current + 1)}>重试</Button>} />}
      <Steps
        current={stage}
        items={stageItems}
        className="mb-6"
        responsive
        onChange={(value) => {
          if (value === 0 || (value === 1 && project) || (value === 2 && project?.finalized_version)) setStage(value);
        }}
      />
      {productionJobs.some((job) => ['queued', 'rendering'].includes(job.status)) && <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-y border-primary-border bg-primary-light px-4 py-3">
        <span className="text-sm font-bold text-primary-text">制作中 {productionJobs.filter((job) => ['queued', 'rendering'].includes(job.status)).length} 个任务</span>
        {productionJobs.filter((job) => ['queued', 'rendering'].includes(job.status)).map((job) => <Button key={job.id} size="small" onClick={() => void loadProject(job.project_id)}>{job.title || `工程 ${job.project_id}`} · {job.progress?.stage || '制作中'}</Button>)}
      </div>}

      {stage === 0 && (
        <div className="space-y-5">
          <Card className="!border-0 !bg-[#17212b] !text-white" styles={{ body: { padding: 26 } }}>
            <div className="grid gap-5 lg:grid-cols-[1fr_280px] lg:items-end">
              <div>
                <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.16em] text-blue-200">01 · 选择一个主题</div>
                <h2 className="!mb-2 !text-3xl !font-black !text-white">先决定你要说什么。</h2>
                <p className="!mb-0 max-w-2xl !text-sm !leading-6 !text-white/65">从真实内容里挑一个切口，或直接写下此刻脑中的想法。视觉、媒介和模板会在下一步再决定。</p>
              </div>
              <Input.TextArea
                value={brief.theme}
                onChange={(event) => { setBriefField('theme', event.target.value); setSelectedId(undefined); }}
                placeholder="写下你的主题或想法…"
                autoSize={{ minRows: 3, maxRows: 5 }}
                className="!border-white/15 !bg-white/10 !text-white placeholder:!text-white/35"
              />
            </div>
          </Card>
          <div className="flex items-center justify-between gap-3">
            <div>
              <Title level={4} className="!mb-0">选题来源</Title>
              <Text type="secondary">收藏内容与今日内容分开展示，点卡片即可选中</Text>
            </div>
            <Space>
              <Tag color="orange">收藏 {favoriteItems.filter((item) => item.target_type === 'content' || item.target_type === 'video').length}</Tag>
              <Tag color="blue">今日 {items.length}</Tag>
            </Space>
          </div>
          {favoriteItems.some((item) => item.target_type === 'content' || item.target_type === 'video') && (
            <section>
              <div className="mb-3 flex items-center gap-2 text-sm font-bold text-gray-800"><Sparkles size={15} className="text-primary" />收藏内容</div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {favoriteItems.filter((item) => item.target_type === 'content' || item.target_type === 'video').map((item) => {
                  const active = selectedFavorite?.id === item.id;
                  const cover = item.cover_url || (typeof item.snapshot?.cover_url === 'string' ? item.snapshot.cover_url : '');
                  return (
                    <button key={`favorite-${item.id}`} type="button" onClick={() => { setSelectedId(-item.id); setBriefField('theme', item.title); }} className={`group overflow-hidden rounded-xl border text-left transition ${active ? 'border-primary-border bg-primary-light shadow-[0_14px_35px_rgba(37,99,235,.15)]' : 'border-blue-100 bg-white hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-lg'}`}>
                      <div className="relative h-32 overflow-hidden bg-primary-light">
                        {cover ? <img src={cover} alt="" className="h-full w-full object-cover transition duration-500 group-hover:scale-105" /> : <div className="flex h-full items-end justify-between p-4"><Sparkles size={34} className="text-primary/30" /><span className="font-mono text-xs text-primary/50">收藏</span></div>}
                        <span className="absolute left-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-bold text-primary-text">收藏</span>
                        {active && <span className="absolute right-3 top-3 rounded-full bg-primary text-white px-2.5 py-1 text-[11px] font-black">已选</span>}
                      </div>
                      <div className="p-4">
                        <div className="mb-2 text-[11px] text-gray-400">{item.source_name || '我的收藏'}</div>
                        <div className="line-clamp-2 min-h-[48px] text-[15px] font-black leading-6 text-gray-900">{item.title}</div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </section>
          )}
          <section>
            <div className="mb-3 flex items-center gap-2 text-sm font-bold text-gray-800"><FileText size={15} className="text-blue-500" />今日内容</div>
          {topicsLoading ? <div className="py-16 text-center text-gray-400">正在整理内容流…</div> : items.length === 0 ? (
            <Empty description="还没有可选内容，可以直接输入你的想法" />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {items.map((item, index) => {
                const active = selectedId === item.id;
                return (
                  <button key={item.id} type="button" onClick={() => { setSelectedId(item.id); setBriefField('theme', item.title); }} className={`group overflow-hidden rounded-xl border text-left transition ${active ? 'border-primary-border bg-primary-light shadow-[0_14px_35px_rgba(37,99,235,.15)]' : 'border-gray-200 bg-white hover:-translate-y-0.5 hover:border-gray-300 hover:shadow-lg'}`}>
                    <div className="relative h-36 overflow-hidden bg-[#e8edf1]">
                      {item.cover_url ? <img src={item.cover_url} alt="" className="h-full w-full object-cover transition duration-500 group-hover:scale-105" /> : <div className="flex h-full items-end justify-between p-4" style={{ background: `linear-gradient(135deg, ${index % 3 === 0 ? '#dce7f4' : index % 3 === 1 ? '#f4e4d4' : '#dcefe8'}, #ffffff)` }}><FileText size={38} className="text-black/20" /><span className="font-mono text-xs text-black/35">{String(index + 1).padStart(2, '0')}</span></div>}
                      {active && <span className="absolute right-3 top-3 rounded-full bg-primary px-2.5 py-1 text-[11px] font-black text-white">已选</span>}
                    </div>
                    <div className="p-4">
                      <div className="mb-2 flex items-center gap-2 text-[11px] text-gray-400"><span className="font-bold text-gray-600">{item.source_name}</span><span>·</span><span>{item.content_type || item.category || '内容'}</span></div>
                      <div className="line-clamp-3 min-h-[66px] text-[15px] font-black leading-6 text-gray-900">{item.title}</div>
                      <div className="mt-3 flex items-center justify-between text-xs text-gray-400"><span>{item.author || '未知作者'}</span><span>{item.published_at ? new Date(item.published_at).toLocaleDateString('zh-CN') : '时间未知'}</span></div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
          </section>
          <div className="sticky bottom-3 z-20 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white/95 p-3 shadow-[0_12px_35px_rgba(15,23,42,.12)] backdrop-blur">
            <div className="min-w-0">
              <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-gray-400">当前主题</div>
              <div className="max-w-[min(70vw,720px)] truncate text-sm font-bold text-gray-900">{brief.theme.trim() || '还没有主题'}</div>
            </div>
            <Button type="primary" size="large" icon={<Plus size={15} />} loading={working} disabled={!catalog || (!brief.theme.trim() && !selected)} onClick={() => void create()}>开始成稿</Button>
          </div>
        </div>
      )}

      {stage === 1 && project && (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
          <Card title={<span className="flex items-center gap-2"><PenLine size={16} /> {project.title}</span>} extra={<Space wrap>
            <Button icon={<Save size={15} />} loading={working} onClick={() => void save()}>保存</Button>
            <Button icon={<WandSparkles size={15} />} loading={working} onClick={() => void compile('rules')}>规则草稿 · 快速结构</Button>
            <Button type="primary" icon={<Sparkles size={15} />} loading={working} onClick={() => void compile('ai')}>
              {project.draft.body || project.draft.shots.length
                ? '重新生成'
                : brief.mode === 'article' ? '生成文章'
                  : brief.mode === 'music_video' ? '生成 MV 方案'
                    : brief.mode === 'animation_video' ? '生成动画讲解' : '生成视频方案'}
            </Button>
          </Space>}>
            <div className="mb-5 space-y-3 border-b border-gray-100 pb-5">
              <label className="block text-sm font-bold">我的创作思路</label>
              <Input.TextArea aria-label="我的创作思路" value={brief.intent} placeholder="故事顺序、关键画面、表达方式、你想保留的内容…" autoSize={{ minRows: 3, maxRows: 8 }} onChange={(event) => setBriefField('intent', event.target.value)} />
              <div className="flex flex-wrap items-end gap-2">
                <Input.TextArea aria-label="改稿要求" value={revisionInstructions} placeholder="填写这一次的修改要求…" autoSize={{ minRows: 2, maxRows: 5 }} className="!flex-1" onChange={(event) => setRevisionInstructions(event.target.value)} />
                <Button icon={<PenLine size={15} />} loading={working} disabled={!revisionInstructions.trim()} onClick={() => void compile('ai', 'refine')}>按要求修改</Button>
              </div>
              <Button type="link" className="!p-0" icon={<History size={14} />} onClick={() => setHistoryOpen(true)}>版本对比 · {project.revisions.length}</Button>
            </div>
            {inlineComparison && (
              <Card size="small" className="mb-5 !border-primary-border !bg-primary-light/30" title={`本次修改 · 版本 ${inlineComparison.version}`}>
                <DraftComparison before={inlineComparison.before} after={inlineComparison.after} beforeLabel="修改前" afterLabel="修改后" />
                <div className="mt-4 flex flex-wrap gap-2 text-xs text-gray-600">
                  <Tag color="red">修改前分镜 {inlineComparison.before.shots.length}</Tag>
                  <Tag color="green">修改后分镜 {inlineComparison.after.shots.length}</Tag>
                  <Tag>歌词 {inlineComparison.after.cues.length}</Tag>
                </div>
              </Card>
            )}
            <Tabs items={[
              { key: 'draft', label: brief.mode === 'article' ? '文章正文' : brief.mode === 'music_video' ? 'MV 方案' : '旁白 / 脚本', children: (
                <div className="space-y-3">
                  <Input value={project.draft.title} placeholder="标题" onChange={(event) => setProject((current) => current ? { ...current, draft: { ...current.draft, title: event.target.value } } : current)} />
                  <Input.TextArea value={project.draft.logline} placeholder="一句话梗概" autoSize={{ minRows: 2, maxRows: 4 }} onChange={(event) => setProject((current) => current ? { ...current, draft: { ...current.draft, logline: event.target.value } } : current)} />
                  <Input.TextArea value={project.draft.body} placeholder={brief.mode === 'article' ? '文章正文' : brief.mode === 'music_video' ? '歌曲视觉方案' : '完整旁白与脚本'} autoSize={{ minRows: 10, maxRows: 22 }} onChange={(event) => setProject((current) => current ? { ...current, draft: { ...current.draft, body: event.target.value } } : current)} />
                </div>
              ) },
              ...(brief.mode !== 'article' ? [{ key: 'shots', label: `分镜 ${project.draft.shots.length}`, children: renderShots() }] : []),
              ...(brief.mode === 'music_video' ? [{ key: 'lyrics', label: `歌词 ${project.draft.cues.length}`, children: renderLyrics() }] : []),
            ]} />
            <Divider />
            <div className="flex flex-wrap justify-between gap-2">
              <Tag color={project.draft.provenance === 'ai' ? 'green' : project.draft.provenance === 'compiled' ? 'blue' : 'default'}>{project.draft.provenance === 'ai' ? 'AI 成稿' : project.draft.provenance === 'compiled' ? '规则草稿' : '人工稿'}</Tag>
              <Button type="primary" icon={<Check size={15} />} loading={working} onClick={() => void finalize()}>{brief.mode === 'article' ? '确认文章' : '确认版本并进入成片'}</Button>
            </div>
          </Card>
          <Card title="创作设定" extra={<Tag color="orange">现在决定</Tag>}>
            <div className="space-y-3">
              <div className="rounded-lg bg-[#f7f8fa] p-3"><Text type="secondary">选题</Text><div className="mt-1 font-bold">{sourceTitle(project)}</div></div>
              <div>
                <div className="mb-2 text-xs font-bold text-gray-500">内容形态</div>
                <Select aria-label="内容形态" className="w-full" value={brief.mode} options={[...modeOptions]} onChange={updateMode} />
                <div className="mt-1 text-xs leading-5 text-gray-500">{modeDescription(brief.mode)}</div>
              </div>
              <div>
                <div className="mb-1 text-xs font-bold text-gray-500">内容模板</div>
                <Button block aria-label="选择内容模板" onClick={() => openPresetPicker('template')} className="!flex !items-center !justify-between !text-left">
                  <span className="truncate">{templates.find((item) => item.id === brief.template_id)?.name ?? '自由发挥'}</span>
                  <ChevronRight size={14} />
                </Button>
              </div>
              {brief.mode !== 'article' && <div>
                <div className="mb-1 text-xs font-bold text-gray-500">视觉风格</div>
                <Button block aria-label="选择视觉风格" onClick={() => openPresetPicker('style')} className="!flex !items-center !justify-between !text-left">
                  <span className="truncate">{styles.find((item) => item.id === brief.style_id)?.name ?? '自由发挥'}</span>
                  <ChevronRight size={14} />
                </Button>
              </div>}
              {brief.mode !== 'article' && (
                <>
                  <div>
                    <div className="mb-1 text-xs font-bold text-gray-500">表现方案</div>
                    <Select className="w-full" value={brief.presentation} options={[
                      { value: 'kinetic', label: '动态图形' },
                      { value: 'cinematic', label: brief.mode === 'animation_video' ? '场景动画' : '电影镜头' },
                      { value: 'ascii', label: 'ASCII 视觉' },
                      { value: 'tui', label: 'TUI 界面' },
                    ]} onChange={(value) => setBriefField('presentation', value)} />
                  </div>
                  <div>
                    <div className="mb-1 text-xs font-bold text-gray-500">制作方式</div>
                    <Select className="w-full" value={brief.production} options={productionOptions(brief.mode).map((option) => ({ value: option.value, label: option.label }))} onChange={(value) => setBriefField('production', value)} />
                  </div>
                </>
              )}
              <Input value={brief.audience} placeholder="受众（可选）" onChange={(event) => setBriefField('audience', event.target.value)} />
              {brief.mode !== 'article' && <Checkbox checked={brief.bilingual} onChange={(event) => setBriefField('bilingual', event.target.checked)}>中英字幕卡</Checkbox>}
              <Button block icon={<Save size={15} />} loading={working} onClick={() => void save()}>保存设定</Button>
            </div>
          </Card>
        </div>
      )}

      <Modal
        open={Boolean(presetModal)}
        onCancel={() => setPresetModal(null)}
        footer={null}
        width={980}
        title={presetModal === 'style' ? '选择视觉风格' : '选择内容模板'}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <Input placeholder="搜索名称或描述" value={presetKeyword} allowClear className="!w-[240px]" onChange={(event) => setPresetKeyword(event.target.value)} />
          <Button size="small" icon={<X size={13} />} onClick={() => { setBriefField(presetModal === 'style' ? 'style_id' : 'template_id', null); setPresetModal(null); }}>清除选择</Button>
        </div>
        <div className="mb-4 flex flex-wrap gap-2">
          {presetCategories.map((category) => <Button key={category} size="small" type={category === presetCategory ? 'primary' : 'text'} onClick={() => setPresetCategory(category!)}>{category}</Button>)}
        </div>
        <div className="grid max-h-[65vh] gap-4 overflow-y-auto p-1 sm:grid-cols-2 xl:grid-cols-3">
          {visiblePresets.map((preset) => {
            const selected = presetModal === 'style' ? brief.style_id === preset.id : brief.template_id === preset.id;
            return (
              <CreativePresetCard
                key={preset.id}
                preset={preset as CreativePreset}
                selected={selected}
                onClick={() => {
                  setBriefField(presetModal === 'style' ? 'style_id' : 'template_id', preset.id);
                  setPresetModal(null);
                }}
              />
            );
          })}
        </div>
      </Modal>

      {stage === 2 && project?.brief.mode === 'article' && (
        <Card title="定稿文章">
          <Title level={3}>{project.draft.title || project.title}</Title>
          {project.draft.logline && <p className="mb-5 text-gray-500">{project.draft.logline}</p>}
          <div className="whitespace-pre-wrap text-sm leading-8">{project.draft.body}</div>
          <div className="mt-5 flex justify-end gap-2">
            <Button icon={<PenLine size={15} />} onClick={() => setStage(1)}>继续编辑</Button>
            <Button type="primary" icon={<Download size={15} />} onClick={() => {
              const blob = new Blob([`# ${project.draft.title || project.title}\n\n${project.draft.body}`], { type: 'text/markdown;charset=utf-8' });
              const url = URL.createObjectURL(blob);
              const anchor = document.createElement('a');
              anchor.href = url; anchor.download = `${project.title}.md`; anchor.click();
              URL.revokeObjectURL(url);
            }}>下载文章</Button>
          </div>
        </Card>
      )}

      {stage === 2 && project && project.brief.mode !== 'article' && (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
          <Card title="成片">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <Space><Tag color="blue">版本 {project.finalized_version ?? project.version}</Tag><Tag>{modeLabel(project.brief.mode)}</Tag><Tag>{productionLabel(project.brief.production)}</Tag></Space>
              <Button icon={<FileText size={15} />} onClick={() => void loadPrompt()}>查看制作提示词</Button>
            </div>
            {project.brief.production === 'code_animation' && project.brief.mode !== 'music_video' && <StudioVoice />}
            {project.artifacts.length ? project.artifacts.map((artifact) => (
              <div key={artifact.id} className="mb-4 space-y-3 rounded-lg border border-gray-200 bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="font-bold">作品 {artifact.id}</span>
                  <Space>
                    {artifact.download_path && <Button size="small" icon={<Download size={14} />} href={artifact.download_path}>下载</Button>}
                    {artifact.preview_path && <Button size="small" icon={<Eye size={14} />} href={artifact.preview_path} target="_blank">打开预览</Button>}
                    {artifact.source_path && <Button size="small" icon={<FolderOpen size={14} />} href={artifact.source_path}>下载工程</Button>}
                    {artifact.status === 'done' && <Button size="small" icon={<FolderOpen size={14} />} href="/favorites">作品库</Button>}
                  </Space>
                </div>
                {artifact.status === 'done' && artifact.preview_path && <video src={artifact.preview_path} controls className="max-h-[520px] w-full rounded-lg bg-black" />}
                <ArtifactProgress artifact={artifact} />
                {artifact.storage_path && <div className="flex items-start gap-2 break-all text-xs text-gray-500"><FolderOpen size={13} className="mt-0.5 shrink-0" />保存位置：{artifact.storage_path}</div>}
              </div>
            )) : <div className="border border-dashed border-gray-300 bg-gray-50 p-6 text-center"><Text type="secondary">确认版本后开始制作</Text></div>}
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              {prompt && <Button icon={<Copy size={15} />} onClick={() => { void navigator.clipboard.writeText(prompt); message.success('已复制制作提示词'); }}>复制提示词</Button>}
              {prompt && <Button icon={<Download size={15} />} onClick={() => { const blob = new Blob([prompt], { type: 'text/markdown;charset=utf-8' }); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${project.title}.md`; anchor.click(); URL.revokeObjectURL(url); }}>下载提示词</Button>}
              {project.brief.production === 'native_mv' && <Button type="primary" icon={<CirclePlay size={15} />} loading={working} onClick={() => void render()}>生成 MV</Button>}
              {project.brief.production === 'code_animation' && <Button type="primary" icon={<CirclePlay size={15} />} loading={working} disabled={project.artifacts.some((item) => ['queued', 'rendering'].includes(item.status))} onClick={() => void render()}>生成动画视频</Button>}
              <Button icon={<ChevronRight size={15} />} onClick={() => setStage(1)}>回到成稿</Button>
            </div>
          </Card>
          <Card title="制作提示词">
            {prompt ? <Input.TextArea value={prompt} onChange={(event) => setPrompt(event.target.value)} autoSize={{ minRows: 20, maxRows: 32 }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="生成后的提示词会显示在这里" />}
          </Card>
        </div>
      )}

      {stage === 2 && (
        <Card className="mt-5" title="历史工程">
          {projects.length ? <List size="small" dataSource={projects} renderItem={(item) => <List.Item actions={[<Button key="open" type="link" onClick={() => void loadProject(item.id)}>打开</Button>]}><List.Item.Meta title={item.title} description={`版本 ${item.version} · ${item.brief.mode}`} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有工程" />}
        </Card>
      )}

      <Modal title="稿件版本" open={historyOpen} onCancel={() => { setHistoryOpen(false); setComparison(undefined); }} footer={null} width={980}>
        <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
          <List
            size="small"
            dataSource={project?.revisions ?? []}
            renderItem={(revision) => (
              <List.Item actions={[<Button key="view" type="link" onClick={() => void openRevision(revision.version)}>查看</Button>]}>
                <List.Item.Meta title={`版本 ${revision.version}`} description={revision.reason} />
              </List.Item>
            )}
          />
          {comparison ? (
            <div className="grid gap-4 md:grid-cols-2">
              <Card size="small" title={`版本 ${comparison.version}`}>
                <Input.TextArea value={draftText(comparison.draft)} readOnly autoSize={{ minRows: 18, maxRows: 30 }} />
              </Card>
              <Card size="small" title="当前版本">
                <Input.TextArea value={project ? draftText(project.draft) : ''} readOnly autoSize={{ minRows: 18, maxRows: 30 }} />
                <Button className="mt-3" type="primary" icon={<CheckCircle2 size={14} />} onClick={() => void adoptComparison()}>采用此稿</Button>
              </Card>
            </div>
          ) : <Empty description="选择一个版本查看差异" />}
        </div>
      </Modal>
    </div>
  );
}
