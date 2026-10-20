'use client';

/** 产出物工作区（设计文档 6.1–6.4）：平台版本、视频提示词包、讲解视频 / MV 的制作参数与历史。 */

import { use, useCallback, useEffect, useMemo, useState } from 'react';
import { Input, Select, Switch, message } from 'antd';
import { Button, Card } from '@/design/components';
import { OUTPUT_STATUS, RunStages, apiError, useProject, useRunWatch } from '@/design/studio';
import { runsApi } from '@/lib/api/_runs';
import { ImageGenPanel } from '@/design/imagegen';
import { LineageDrawer } from '@/design/lineage';
import type { LineageQuery } from '@/lib/api/_runs';
import { libraryFileUrl } from '@/lib/api/_library';
import type { GenTarget } from '@/lib/api/_generations';
import type { ProjectAsset } from '@/lib/api/_projects';
import { libraryApi, type StyleEntry } from '@/lib/api/_library';
import { projectsApi, type OutputView } from '@/lib/api/_projects';
import { PLATFORM_LIMITS, fmtClock, platformIssues, qaMark, stripTags, textLen } from '@/lib/projects';
import { useOutputs } from '../_ctx';

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    message.success(`已复制${what}`);
  } catch {
    message.error('复制失败，浏览器不允许访问剪贴板');
  }
}

function Counter({ value, max }: { value: number; max?: number }) {
  return (
    <small className="cw-num" data-over={max !== undefined && value > max ? true : undefined}>
      {value}
      {max !== undefined ? ` / ${max}` : ''}
    </small>
  );
}

const PUBLISH_URL: Record<string, string> = {
  xhs: 'https://creator.xiaohongshu.com/publish/publish',
  zhihu: 'https://zhuanlan.zhihu.com/write',
  wechat: 'https://mp.weixin.qq.com/',
};

// ── 配图 / 封面（生图，设计 6.5）──

function useOutputAssets(projectId: number, outputId: number) {
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const load = useCallback(async () => {
    try {
      const r = await projectsApi.assets(projectId);
      setAssets(r.items.filter((a) => (a.target as { output_id?: number } | null)?.output_id === outputId));
    } catch {
      /* 素材加载失败不影响编辑 */
    }
  }, [projectId, outputId]);
  useEffect(() => {
    void load();
  }, [load]);
  return { assets, load };
}

function OutputImages({ output }: { output: OutputView }) {
  const { assets, load } = useOutputAssets(output.project_id, output.id);
  const [target, setTarget] = useState<GenTarget | null>(null);
  const [mood, setMood] = useState<number[]>([]);
  useEffect(() => {
    projectsApi
      .assets(output.project_id, 'moodboard')
      .then((r) => setMood(r.items.filter((a) => a.item?.thumb).map((a) => a.library_item_id).slice(0, 4)))
      .catch(() => {});
  }, [output.project_id]);
  const isXhs = output.kind === 'xhs';
  const slots = isXhs ? Math.max(3, Math.min(9, assets.length + 1)) : 1;
  const at = (i: number) =>
    assets.find((a) => (isXhs ? (a.target as { index?: number })?.index === i : a.role === 'cover'));
  return (
    <div className="cw-field">
      <span>{isXhs ? '配图（3–9 张）' : '封面'}</span>
      <div className="cw-outimgs">
        {Array.from({ length: slots }).map((_, k) => {
          const i = k + 1;
          const a = at(i);
          return (
            <button
              key={i}
              type="button"
              className="cw-outimg"
              data-wide={!isXhs || undefined}
              onClick={() => setTarget(isXhs ? { type: 'xhs', index: i } : { type: 'cover' })}
              title={a?.item?.title || '生图'}
            >
              {a?.item?.thumb ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={libraryFileUrl(a.library_item_id, 'small')} alt="" />
              ) : (
                <span className="cw-muted">{isXhs ? `第 ${i} 张` : '生成封面'}</span>
              )}
            </button>
          );
        })}
      </div>
      {target ? (
        <ImageGenPanel
          open
          onClose={() => setTarget(null)}
          projectId={output.project_id}
          outputId={output.id}
          target={target}
          defaultRefIds={mood}
          onKept={() => void load()}
        />
      ) : null}
    </div>
  );
}

// ── 平台版本 ──

function PlatformWorkspace({ output, onSaved }: { output: OutputView; onSaved: (o: OutputView) => void }) {
  const [c, setC] = useState(() => ({
    title: output.content.title || '',
    body: output.content.body || '',
    tags: (output.content.tags || []).join(' '),
    cover_text: output.content.cover_text || '',
    summary: output.content.summary || '',
  }));
  const [busy, setBusy] = useState<string | null>(null);
  const [lin, setLin] = useState<LineageQuery | null>(null);
  const [url, setUrl] = useState(output.published_url || '');
  useEffect(() => {
    setC({
      title: output.content.title || '',
      body: output.content.body || '',
      tags: (output.content.tags || []).join(' '),
      cover_text: output.content.cover_text || '',
      summary: output.content.summary || '',
    });
    setUrl(output.published_url || '');
  }, [output]);
  const lim = PLATFORM_LIMITS[output.kind] || {};
  const tags = c.tags.split(/[\s,，#]+/).filter(Boolean);
  const issues = platformIssues(output.kind, { ...c, tags });
  const run = async (key: string, fn: () => Promise<OutputView>, ok?: string) => {
    setBusy(key);
    try {
      onSaved(await fn());
      if (ok) message.success(ok);
    } catch (err) {
      message.error(apiError(err));
    } finally {
      setBusy(null);
    }
  };
  const save = () =>
    run('save', () => projectsApi.patchOutput(output.id, { content: { ...output.content, ...c, tags, warnings: [] } }), '已保存');
  const isWechat = output.kind === 'wechat';
  const previewDoc = useMemo(
    () =>
      `<!doctype html><meta charset="utf-8"><style>body{font:16px/1.8 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#222;margin:0;padding:20px 18px;}h1{font-size:22px}img{max-width:100%}blockquote{border-left:3px solid #ddd;margin:0;padding-left:12px;color:#666}</style><h1>${escapeHtml(c.title)}</h1>${c.body}`,
    [c.title, c.body],
  );
  return (
    <div className="cw-platform">
      <div className="cw-platform-edit">
        <div className="cw-row">
          <Button variant="primary" onClick={() => run('gen', () => projectsApi.generateOutput(output.id), '已从定稿改写')} disabled={busy !== null}>
            {busy === 'gen' ? '改写中…' : output.content.body ? '重新改写' : 'AI 从定稿改写'}
          </Button>
          <Button onClick={save} disabled={busy !== null}>
            保存
          </Button>
          <span className="cw-grow" />
          {output.content.model ? <small className="cw-muted">{String(output.content.model)}</small> : null}
        </div>
        {(output.content.warnings || []).length ? (
          <div className="cw-notice">{(output.content.warnings || []).join('；')}</div>
        ) : null}
        {issues.length ? <div className="cw-notice" data-tone="warn">{issues.join('；')}</div> : null}
        <label className="cw-field">
          <span>
            标题 <Counter value={textLen(c.title)} max={lim.title} />
          </span>
          <Input value={c.title} onChange={(e) => setC({ ...c, title: e.target.value })} />
        </label>
        {output.kind === 'wechat' ? (
          <label className="cw-field">
            <span>
              摘要 <Counter value={textLen(c.summary)} max={lim.summary} />
            </span>
            <Input.TextArea value={c.summary} onChange={(e) => setC({ ...c, summary: e.target.value })} autoSize={{ minRows: 2, maxRows: 4 }} />
          </label>
        ) : null}
        <label className="cw-field">
          <span>
            正文{isWechat ? '（HTML，保存时清洗）' : output.kind === 'zhihu' ? '（Markdown）' : ''}{' '}
            <Counter value={textLen(isWechat ? stripTags(c.body) : c.body)} max={lim.body} />
          </span>
          <Input.TextArea value={c.body} onChange={(e) => setC({ ...c, body: e.target.value })} autoSize={{ minRows: 12, maxRows: 30 }} />
        </label>
        {output.kind === 'xhs' ? (
          <>
            <label className="cw-field">
              <span>
                话题（空格分隔） <Counter value={tags.length} max={lim.tags?.[1]} />
              </span>
              <Input value={c.tags} onChange={(e) => setC({ ...c, tags: e.target.value })} />
            </label>
            <label className="cw-field">
              <span>
                封面文案 <Counter value={textLen(c.cover_text)} max={lim.cover_text} />
              </span>
              <Input value={c.cover_text} onChange={(e) => setC({ ...c, cover_text: e.target.value })} />
            </label>
            {(output.content.image_suggestions || []).length ? (
              <div className="cw-field">
                <span>配图建议</span>
                <ol className="cw-muted">
                  {(output.content.image_suggestions || []).map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ol>
              </div>
            ) : null}
          </>
        ) : null}
        {output.kind === 'xhs' || output.kind === 'wechat' ? <OutputImages output={output} /> : null}
        <div className="cw-row">
          <Button onClick={() => copy(c.title, '标题')}>复制标题</Button>
          <Button onClick={() => copy(isWechat ? stripTags(c.body) : c.body, '正文')}>复制正文</Button>
          {output.kind === 'xhs' ? <Button onClick={() => copy(tags.map((t) => `#${t}`).join(' '), '话题')}>复制话题</Button> : null}
          <a className="cw-btn" href={projectsApi.exportUrl(output.id, 'md')} target="_blank" rel="noreferrer">
            导出 Markdown
          </a>
          <a className="cw-btn" href={projectsApi.exportUrl(output.id, 'html')} target="_blank" rel="noreferrer">
            导出 HTML
          </a>
          <a className="cw-btn" data-variant="ghost" href={PUBLISH_URL[output.kind]} target="_blank" rel="noreferrer">
            打开发布页 ↗
          </a>
          {output.based_on_version ? <Button onClick={() => setLin({ target: 'platform', output_id: output.id })}>溯源</Button> : null}
        </div>
        <LineageDrawer query={lin} onClose={() => setLin(null)} title="溯源：平台稿" />
        <label className="cw-field">
          <span>发布链接（填入后状态变为「已发布」）</span>
          <div className="cw-row">
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" style={{ flex: 1 }} />
            <Button onClick={() => run('pub', () => projectsApi.patchOutput(output.id, { published_url: url }), url ? '已标记为已发布' : '已清除')} disabled={busy !== null}>
              保存
            </Button>
          </div>
        </label>
      </div>
      <div className="cw-platform-preview" aria-label="平台预览">
        {output.kind === 'xhs' ? (
          <div className="cw-phone">
            <div className="cw-phone-cover">{c.cover_text || '封面文案'}</div>
            <h4>{c.title || '标题'}</h4>
            <p>{c.body}</p>
            <p className="cw-phone-tags">{tags.map((t) => `#${t} `)}</p>
          </div>
        ) : isWechat ? (
          <iframe title="公众号预览" sandbox="" srcDoc={previewDoc} className="cw-preview-frame" />
        ) : (
          <article className="cw-zhihu">
            <h2>{c.title}</h2>
            {c.body.split(/\n\s*\n/).map((p, i) =>
              /^##\s/.test(p) ? <h3 key={i}>{p.replace(/^##\s*/, '')}</h3> : <p key={i}>{p}</p>,
            )}
          </article>
        )}
      </div>
    </div>
  );
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── 提示词包 ──

const TARGETS = [
  { value: 'generic', label: '通用' },
  { value: 'claude_code', label: 'Claude Code' },
  { value: 'codex', label: 'Codex' },
  { value: 'deepseek_harness', label: 'DeepSeek Harness' },
];
const SECTIONS = [
  { value: 'script', label: '定稿脚本' },
  { value: 'storyboard', label: '分镜表' },
  { value: 'style', label: '风格规范' },
  { value: 'assets', label: '素材清单' },
  { value: 'delivery', label: '交付要求' },
];

function useStyles() {
  const [styles, setStyles] = useState<StyleEntry<unknown>[]>([]);
  useEffect(() => {
    libraryApi
      .styles()
      .then((r) => setStyles(r.items))
      .catch(() => setStyles([]));
  }, []);
  return styles;
}

function BundleWorkspace({ output, onSaved }: { output: OutputView; onSaved: (o: OutputView) => void }) {
  const [md, setMd] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const settings = output.settings as { target?: string; include?: string[]; style_id?: string | null; aspect_ratio?: string };
  const styles = useStyles();
  const refresh = useCallback(async () => {
    try {
      setMd(await projectsApi.bundleMarkdown(output.id));
      setError(null);
    } catch (err) {
      setError(apiError(err, '预览失败'));
    }
  }, [output.id]);
  useEffect(() => {
    void refresh();
  }, [refresh, output.updated_at]);
  const patch = async (s: Record<string, unknown>) => {
    try {
      onSaved(await projectsApi.patchOutput(output.id, { settings: s }));
    } catch (err) {
      message.error(apiError(err));
    }
  };
  const include = settings.include || SECTIONS.map((s) => s.value);
  return (
    <div className="cw-platform">
      <div className="cw-platform-edit">
        <label className="cw-field">
          <span>目标</span>
          <Select value={settings.target || 'generic'} options={TARGETS} onChange={(v) => patch({ target: v })} />
        </label>
        <div className="cw-field">
          <span>内容</span>
          <div className="cw-seg" role="group" aria-label="提示词包内容">
            {SECTIONS.map((s) => (
              <button
                key={s.value}
                type="button"
                aria-pressed={include.includes(s.value)}
                onClick={() => patch({ include: include.includes(s.value) ? include.filter((x) => x !== s.value) : [...include, s.value] })}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        <label className="cw-field">
          <span>视觉风格</span>
          <Select allowClear value={settings.style_id || undefined} placeholder="不指定" options={styles.map((s) => ({ value: s.key, label: s.name }))} onChange={(v) => patch({ style_id: v ?? null })} />
        </label>
        <label className="cw-field">
          <span>画幅</span>
          <Select value={settings.aspect_ratio || '16:9'} options={['16:9', '9:16', '1:1'].map((v) => ({ value: v, label: v }))} onChange={(v) => patch({ aspect_ratio: v })} />
        </label>
        <div className="cw-row">
          <Button onClick={() => copy(md, '提示词包')} disabled={!md}>
            复制
          </Button>
          <a className="cw-btn" href={projectsApi.bundleUrl(output.id, 'md')}>
            下载 .md
          </a>
          <a className="cw-btn" data-variant="primary" href={projectsApi.bundleUrl(output.id, 'zip')}>
            下载 .zip（含素材）
          </a>
        </div>
        <p className="cw-muted" style={{ fontSize: 12 }}>
          提示词包由模板确定性生成，不调用模型。外部 agent 可用设置 · 工作台里的 MCP 令牌连接工作台工具，项目 id：{output.project_id}。
        </p>
      </div>
      <div className="cw-platform-preview">
        {error ? <div className="cw-error">{error}</div> : <pre className="cw-bundle-md">{md}</pre>}
      </div>
    </div>
  );
}

// ── 讲解视频 / MV ──

const PRESENTATIONS = [
  { value: 'kinetic', label: '动态图形' },
  { value: 'ascii', label: 'ASCII 动画' },
  { value: 'tui', label: '终端界面' },
  { value: 'cinematic', label: '电影镜头' },
];
const EXECUTORS = [
  { value: 'deepseek_harness', label: 'DeepSeek Harness（默认）' },
  { value: 'claude_code', label: 'Claude Code' },
  { value: 'codex', label: 'Codex' },
];

interface QaReport {
  passed: boolean;
  checks: { key: string; label: string; ok: boolean | null; detail: string }[];
  issues: { id: string; check: string; shot?: number; problem: string }[];
}

function QaView({ qa }: { qa: QaReport }) {
  return (
    <div>
      <dl className="cw-qa">
        {qa.checks.map((c) => {
          const m = qaMark(c.ok);
          return (
            <div key={c.key} style={{ display: 'contents' }}>
              <dt>{c.label}</dt>
              <dd>{c.detail}</dd>
              <dd data-tone={m.tone}>{m.text}</dd>
            </div>
          );
        })}
      </dl>
      {qa.issues.length ? (
        <ul className="cw-muted" style={{ fontSize: 12, margin: '6px 0 0', paddingLeft: 18 }}>
          {qa.issues.slice(0, 8).map((i) => (
            <li key={i.id}>{i.shot ? `第 ${i.shot} 镜：` : ''}{i.problem}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** 分镜关键帧：美术节点优先用这里指定的图；也可以先在这里生图。 */
function KeyframesCard({ output, locked }: { output: OutputView; locked: boolean }) {
  const version = output.based_on_version ?? output.latest_finalized;
  const [shots, setShots] = useState<{ beat: string; visual: string; seconds: number }[]>([]);
  const { assets, load } = useOutputAssets(output.project_id, output.id);
  const [shot, setShot] = useState<number | null>(null);
  const styleId = (output.settings as { style_id?: string | null }).style_id;
  useEffect(() => {
    if (!version) return;
    projectsApi
      .version(output.project_id, version)
      .then((v) => setShots(v.draft.shots || []))
      .catch(() => setShots([]));
  }, [output.project_id, version]);
  if (!shots.length || output.kind !== 'video') return null;
  return (
    <Card title="分镜关键帧" extra={<small>没指定的镜头由美术出提示词，生成服务可用时自动生图</small>}>
      <div className="cw-keyframes">
        {shots.map((s, k) => {
          const i = k + 1;
          const a = assets.find((x) => x.role === 'keyframe' && (x.target as { shot?: number })?.shot === i);
          return (
            <button key={i} type="button" className="cw-keyframe" onClick={() => setShot(i)} disabled={locked} title={s.visual}>
              {a?.item?.thumb ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={libraryFileUrl(a.library_item_id, 'small')} alt="" />
              ) : (
                <span className="cw-muted">生图</span>
              )}
              <small>
                <b className="cw-num">{i}</b> {s.beat || s.visual.slice(0, 12)}
              </small>
            </button>
          );
        })}
      </div>
      {shot ? (
        <ImageGenPanel
          open
          onClose={() => setShot(null)}
          projectId={output.project_id}
          outputId={output.id}
          target={{ type: 'shot', shot }}
          styleId={styleId}
          onKept={() => void load()}
        />
      ) : null}
    </Card>
  );
}

function ProductionWorkspace({ output, onSaved }: { output: OutputView; onSaved: (o: OutputView) => void }) {
  const s = output.settings as { style_id?: string | null; presentation?: string | null; aspect_ratio?: string; bilingual?: boolean; executor?: string };
  const styles = useStyles();
  const [executors, setExecutors] = useState<{ key: string; label: string; available: boolean; hint: string | null }[]>([]);
  const [lin, setLin] = useState<LineageQuery | null>(null);
  const [busy, setBusy] = useState(false);
  const runId = (output.content?.run_id as number | undefined) || null;
  const refresh = useCallback(async () => onSaved(await projectsApi.output(output.id)), [output.id, onSaved]);
  const run = useRunWatch(runId, () => void refresh());
  const active = Boolean(run && ['queued', 'running', 'waiting'].includes(run.run.status));
  // 制作中每 3 秒刷新一次产出物，拿到制作阶段与百分比
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => void refresh().catch(() => {}), 3000);
    return () => clearInterval(t);
  }, [active, refresh]);
  useEffect(() => {
    projectsApi.executors().then((r) => setExecutors(r.items)).catch(() => {});
  }, []);
  const patch = async (v: Record<string, unknown>) => {
    try {
      onSaved(await projectsApi.patchOutput(output.id, { settings: v }));
    } catch (err) {
      message.error(apiError(err));
    }
  };
  const start = async () => {
    setBusy(true);
    try {
      const r = await projectsApi.render(output.id);
      onSaved(r.output);
      message.success('已开始制作');
    } catch (err) {
      message.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };
  const resume = async () => {
    if (!runId) return;
    setBusy(true);
    try {
      await runsApi.continue(runId);
      await refresh();
    } catch (err) {
      message.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };
  const stop = async () => {
    if (!runId || !window.confirm('停止这次制作？')) return;
    await runsApi.stop(runId).catch((err) => message.error(apiError(err)));
    await refresh();
  };
  const current = output.artifacts?.find((a) => a.id === output.content?.artifact_id) || output.artifacts?.[0];
  const prog = (current?.progress || {}) as { stage?: string; percent?: number | null; elapsed_seconds?: number; qa?: QaReport };
  const execOptions = EXECUTORS.map((e) => {
    const st = executors.find((x) => x.key === e.value);
    return { ...e, label: st && !st.available ? `${e.label}（未安装）` : e.label, title: st?.hint || undefined };
  });
  const execHint = executors.find((x) => x.key === (s.executor || 'deepseek_harness'));
  return (
    <div className="cw-production">
      <Card title="制作参数" extra={<small>属于制作层：修改不影响定稿</small>}>
        <div className="cw-brief">
          <label>
            <span>视觉风格</span>
            <Select allowClear value={s.style_id || undefined} placeholder="不指定" options={styles.map((x) => ({ value: x.key, label: x.name }))} onChange={(v) => patch({ style_id: v ?? null })} disabled={active} />
          </label>
          {output.kind === 'video' ? (
            <label>
              <span>表现方案</span>
              <Select value={s.presentation || 'kinetic'} options={PRESENTATIONS} onChange={(v) => patch({ presentation: v })} disabled={active} />
            </label>
          ) : null}
          <label>
            <span>画幅</span>
            <Select value={s.aspect_ratio || '16:9'} options={['16:9', '9:16', '1:1'].map((v) => ({ value: v, label: v }))} onChange={(v) => patch({ aspect_ratio: v })} disabled={active} />
          </label>
          <label>
            <span>执行者</span>
            <Select value={s.executor || 'deepseek_harness'} options={execOptions} onChange={(v) => patch({ executor: v })} disabled={active} />
          </label>
          <label className="cw-inline">
            <Switch size="small" checked={Boolean(s.bilingual)} onChange={(v) => patch({ bilingual: v })} disabled={active} /> 中英字幕卡
          </label>
        </div>
        {execHint && !execHint.available ? <p className="cw-error" style={{ fontSize: 12 }}>{execHint.hint}</p> : null}
        <div className="cw-row" style={{ marginTop: 12 }}>
          <span className="cw-muted">基于 v{output.based_on_version ?? output.latest_finalized ?? '—'}</span>
          <span className="cw-grow" />
          {active ? (
            <Button onClick={stop}>停止</Button>
          ) : run && ['failed', 'paused'].includes(run.run.status) ? (
            <Button onClick={resume} disabled={busy}>从失败处继续</Button>
          ) : null}
          <Button variant="primary" onClick={start} disabled={!output.can_start || active || busy} title={output.can_start ? '分镜 → 美术 → 制作 → 质检' : '定稿后可制作'}>
            {active ? '制作中…' : output.status === 'done' || output.status === 'failed' ? '重新制作' : '开始制作'}
          </Button>
        </div>
      </Card>
      <KeyframesCard output={output} locked={active} />
      {run ? (
        <Card title="本次制作" extra={<small className="cw-num">#{run.run.id}</small>}>
          <RunStages detail={run} />
          {active && prog.stage ? (
            <div className="cw-prodbar" style={{ marginTop: 10 }}>
              <span>{prog.stage}</span>
              <progress max={100} value={prog.percent ?? undefined} />
              <span className="cw-num">{prog.percent != null ? `${prog.percent}%` : ''}</span>
              <span className="cw-num cw-muted">{prog.elapsed_seconds != null ? fmtClock(prog.elapsed_seconds) : ''}</span>
            </div>
          ) : null}
          {prog.qa ? (
            <div style={{ marginTop: 10 }}>
              <h4 style={{ margin: '0 0 6px', fontSize: 13 }}>质检报告 {prog.qa.passed ? '· 通过' : '· 未通过'}</h4>
              <QaView qa={prog.qa} />
            </div>
          ) : null}
          {current?.preview_path && current.status === 'done' ? (
            <video src={current.preview_path} controls style={{ width: '100%', marginTop: 10, borderRadius: 8, background: '#000' }} />
          ) : null}
        </Card>
      ) : null}
      <Card title="历史成片">
        {output.artifacts?.length ? (
          <ul className="cw-hist">
            {output.artifacts.map((a) => {
              const [label, c] = OUTPUT_STATUS[a.status === 'error' ? 'failed' : a.status] || [a.status, 'var(--cw-dim)'];
              const qa = (a.progress as { qa?: QaReport })?.qa;
              return (
                <li key={a.id}>
                  <span className="cw-num">#{a.id} v{a.version}</span>
                  <span style={{ color: c }}>{label}</span>
                  {a.settings?.style_id ? <span className="cw-muted">{String(a.settings.style_id)}</span> : null}
                  {a.settings?.executor ? <span className="cw-muted">{String(a.settings.executor)}</span> : null}
                  {qa ? <span style={{ color: qa.passed ? 'var(--cw-gr)' : 'var(--cw-rd)' }}>质检{qa.passed ? '通过' : '未通过'}</span> : null}
                  {a.preview_path ? (
                    <a className="cw-link-btn" href={a.preview_path} target="_blank" rel="noreferrer">
                      预览
                    </a>
                  ) : null}
                  {a.download_path ? (
                    <a className="cw-link-btn" href={a.download_path}>
                      下载
                    </a>
                  ) : null}
                  {a.status === 'done' && a.settings?.run_id ? (
                    <button type="button" className="cw-link-btn" onClick={() => setLin({ target: 'video', output_id: output.id, studio_artifact_id: a.id })}>
                      溯源
                    </button>
                  ) : null}
                  {a.error ? <small className="cw-muted">{a.error.slice(0, 80)}</small> : null}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="cw-empty">还没有成片</p>
        )}
      </Card>
      <LineageDrawer query={lin} onClose={() => setLin(null)} title="溯源：成片" />
    </div>
  );
}

export default function OutputWorkspace({ params }: { params: Promise<{ outputId: string }> }) {
  const { outputId } = use(params);
  const { project } = useProject();
  const { reload } = useOutputs();
  const [output, setOutput] = useState<OutputView | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    projectsApi
      .output(Number(outputId))
      .then(setOutput)
      .catch((err) => setError(apiError(err, '产出物加载失败')));
  }, [outputId]);
  if (error) return <div className="cw-error">{error}</div>;
  if (!output || !project) return <div className="cw-empty">加载中…</div>;
  const saved = (o: OutputView) => {
    setOutput(o);
    void reload();
  };
  const remove = async () => {
    if (!window.confirm(`删除「${output.title}」？`)) return;
    await projectsApi.deleteOutput(output.id);
    await reload();
    window.location.assign(`/projects/${project.id}/outputs`);
  };
  return (
    <div className="cw-outworkspace">
      <header className="cw-outhead">
        <h2>{output.title}</h2>
        <span className="cw-muted">{output.based_on_version ? `基于 v${output.based_on_version}` : '基于工作副本'}</span>
        {output.stale ? <span className="cw-outstale">文稿已更新到 v{output.latest_finalized}，可重新生成</span> : null}
        <span className="cw-grow" />
        <button type="button" className="cw-link-btn" onClick={remove}>
          删除
        </button>
      </header>
      {['xhs', 'zhihu', 'wechat'].includes(output.kind) ? (
        <PlatformWorkspace output={output} onSaved={saved} />
      ) : output.kind === 'prompt_bundle' ? (
        <BundleWorkspace output={output} onSaved={saved} />
      ) : (
        <ProductionWorkspace output={output} onSaved={saved} />
      )}
    </div>
  );
}
