'use client';

/** 第二步：文稿（设计文档 5 节）——大纲 / 纸面编辑器或分镜表 / 侧面板；自动保存、版本、定稿。 */

import { MemeInsert } from '@/design/memes';
import Link from 'next/link';
import { Input, Modal, message } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/design/components';
import { BodyEditor, type BodyEditorHandle } from '@/design/body-editor';
import { LyricTimeline } from '@/design/lyric-timeline';
import { MODE_LABEL, RunStages, apiError, useProject, useRunWatch } from '@/design/studio';
import { AssistantPanel, OutlineTree, ScriptTable, SourcesPanel, SuggestionReview, VersionsPanel } from '@/design/studio-draft';
import {
  AutosaveQueue,
  countChars,
  fmtClock,
  joinNarration,
  outline,
  readSeconds,
  shotTotal,
  splitNarration,
  splitParagraphs,
  type AutosaveState,
} from '@/lib/projects';
import { projectsApi, type Draft, type DraftView, type Suggestion, type SuggestionScope } from '@/lib/api/_projects';

type SideTab = 'assist' | 'brief' | 'versions' | 'sources';

export default function DraftPage() {
  const { project, reload, setUnsaved } = useProject();
  const [view, setView] = useState<DraftView | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [save, setSave] = useState<{ state: AutosaveState; at?: number; error?: string }>({ state: 'idle' });
  const [conflictToken, setConflictToken] = useState<string | null>(null);
  const [side, setSide] = useState<SideTab>('assist');
  const [scriptTab, setScriptTab] = useState<'narration' | 'table'>('table');
  const [sel, setSel] = useState<number[]>([]);
  const [shotSel, setShotSel] = useState<number[]>([]);
  const [assistSeed, setAssistSeed] = useState<{ text: string; nonce: number } | null>(null);
  const [review, setReview] = useState<Suggestion | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [finalizeOpen, setFinalizeOpen] = useState(false);
  const [narration, setNarration] = useState('');
  const queueRef = useRef<AutosaveQueue<Draft> | null>(null);
  const composing = useRef(false);
  const bodyRef = useRef<BodyEditorHandle | null>(null);
  const pid = project?.id;

  const load = useCallback(async () => {
    if (!pid) return;
    const v = await projectsApi.draft(pid);
    setView(v);
    setDraft(v.draft);
    setNarration(joinNarration(v.draft.shots));
    queueRef.current?.dispose();
    queueRef.current = new AutosaveQueue<Draft>(v.draft_token, {
      save: (d, token) => projectsApi.saveDraft(pid, d, token),
      onState: (state, info) => {
        setSave({ state, at: info?.savedAt, error: info?.error });
        if (state === 'conflict') setConflictToken(info?.token || null);
      },
    });
  }, [pid]);

  useEffect(() => {
    void load().catch((err) => message.error(apiError(err, '文稿加载失败')));
    return () => queueRef.current?.dispose();
  }, [load]);

  useEffect(() => {
    setUnsaved(save.state === 'pending' || save.state === 'saving' || save.state === 'conflict');
  }, [save.state, setUnsaved]);

  // 离开页面前尽量存掉
  useEffect(() => {
    const onLeave = (e: BeforeUnloadEvent) => {
      if (queueRef.current?.busy) {
        void queueRef.current.flush();
        e.preventDefault();
      }
    };
    window.addEventListener('beforeunload', onLeave);
    return () => window.removeEventListener('beforeunload', onLeave);
  }, []);

  // 「AI 写初稿」的成稿流程：进行中显示阶段条，结束后载入新版本
  const aiRunId = project?.ai_draft?.run_id;
  const aiRun = useRunWatch(aiRunId, (d) => {
    if (d.run.status === 'done') message.success('AI 初稿已写入文稿');
    void reload();
    void load();
    setRefreshKey((k) => k + 1);
  });
  const aiActive = Boolean(aiRun && ['queued', 'running', 'waiting'].includes(aiRun.run.status));

  const locked = Boolean(project?.finalized_version);
  // 文稿页也能直接让 AI 写全文（之前只有选题页有「AI 写初稿」，按模板进来后就找不到了）
  const [aiStarting, setAiStarting] = useState(false);
  const startAiDraft = async () => {
    if (!project) return;
    setAiStarting(true);
    try {
      await flushed();
      await projectsApi.aiDraft(project.id);
      message.success('AI 开始写全文，写完会存成新版本；现在的内容留在「版本」里');
      await reload();
    } catch (err) {
      message.error(apiError(err, 'AI 写全文启动失败'));
    } finally {
      setAiStarting(false);
    }
  };
  const isVideo = view ? view.brief.mode !== 'article' : false;

  const change = (next: Draft) => {
    setDraft(next);
    if (!composing.current) queueRef.current?.change(next);
  };

  const flushed = async (): Promise<string | null> => {
    await queueRef.current?.flush();
    return queueRef.current?.currentToken ?? null;
  };

  const saveVersion = useCallback(async () => {
    if (!pid || locked) return;
    try {
      await queueRef.current?.flush();
      const r = await projectsApi.saveVersion(pid, 'manual');
      message.success(`已保存 v${r.version}`);
      setRefreshKey((k) => k + 1);
      await reload();
    } catch (err) {
      message.error(apiError(err));
    }
  }, [pid, locked, reload]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        void saveVersion();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [saveVersion]);

  const scope: SuggestionScope = useMemo(() => {
    if (isVideo && shotSel.length && scriptTab === 'table') return { type: 'shots', indexes: shotSel };
    if (!isVideo && draft && sel.length) return { type: 'paragraphs', ids: sel.map(String) };
    return { type: 'all' };
  }, [isVideo, shotSel, scriptTab, draft, sel]);

  /** 发 AI 指令前：先存工作副本，再用服务端段落 id 换算选区。 */
  const beforeSend = async () => {
    const token = await flushed();
    if (!pid) return { token, scope };
    const fresh = await projectsApi.draft(pid);
    setView(fresh);
    if (scope.type === 'paragraphs') {
      const ids = (scope.ids || []).map((i) => fresh.paragraphs[Number(i)]?.id).filter(Boolean) as string[];
      return { token: fresh.draft_token, scope: ids.length ? { type: 'paragraphs' as const, ids } : { type: 'all' as const } };
    }
    return { token: fresh.draft_token, scope };
  };

  const resolveConflict = async (mine: boolean) => {
    if (!pid || !draft) return;
    try {
      if (mine) {
        const r = await projectsApi.saveDraft(pid, queueRef.current?.pendingValue() || draft, queueRef.current?.currentToken ?? null, true);
        queueRef.current?.resolve(r.draft_token, false);
        setSave({ state: 'saved', at: Date.now() });
        setRefreshKey((k) => k + 1);
      } else {
        await load();
        setSave({ state: 'idle' });
      }
      setConflictToken(null);
    } catch (err) {
      message.error(apiError(err));
    }
  };

  const doFinalize = async () => {
    if (!pid) return;
    try {
      await queueRef.current?.flush();
      await projectsApi.finalize(pid);
      setFinalizeOpen(false);
      await reload();
      await load();
      setRefreshKey((k) => k + 1);
      message.success('已定稿');
    } catch (err) {
      message.error(apiError(err));
    }
  };
  const doUnlock = async () => {
    if (!pid) return;
    await projectsApi.unlock(pid);
    await reload();
    await load();
  };

  const insertAtCursor = (text: string) => {
    if (!draft || locked) return;
    if (bodyRef.current) bodyRef.current.insert(text);
    else change({ ...draft, body: `${draft.body}${text}` });
  };

  if (!project || !view || !draft) return <div className="cw-empty" style={{ padding: 24 }}>加载中…</div>;

  const chars = countChars(isVideo ? joinNarration(draft.shots) || draft.body : draft.body);
  const heads = outline(draft.body);
  const paras = splitParagraphs(draft.body);
  const saveText =
    save.state === 'saving'
      ? '保存中…'
      : save.state === 'pending'
        ? '有未保存修改'
        : save.state === 'saved' && save.at
          ? `已自动保存 ${new Date(save.at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
          : save.state === 'error'
            ? `保存失败：${save.error}`
            : view.dirty
              ? '已保存 · 还没存成版本'
              : '已是最新版本';

  return (
    <div className="cw-draft">
      {conflictToken !== null || save.state === 'conflict' ? (
        <div className="cw-banner" data-tone="warn" role="alert">
          这份文稿在另一个窗口改过。
          <Button onClick={() => resolveConflict(false)}>载入最新</Button>
          <Button onClick={() => resolveConflict(true)}>用我的覆盖</Button>
          <small className="cw-muted">覆盖前会先把对方的内容存成一个版本</small>
        </div>
      ) : null}
      {!locked && !aiActive && draft.provenance === 'compiled' ? (
        <div className="cw-banner">
          <span>这是按模板生成的结构，正文还是占位。点「AI 写全文」让 AI 按这个结构和来源写正文，或者直接自己改。</span>
          <Button variant="primary" onClick={() => void startAiDraft()} disabled={aiStarting}>
            {aiStarting ? '启动中…' : 'AI 写全文'}
          </Button>
        </div>
      ) : null}
      {aiRun && (aiActive || aiRun.run.status === 'failed') ? (
        <div className="cw-banner" data-tone={aiRun.run.status === 'failed' ? 'warn' : undefined}>
          <span>{aiActive ? 'AI 正在写初稿，完成后会写成新版本；现在的修改会被它覆盖（旧内容留在版本里）。' : 'AI 写初稿没有完成。'}</span>
          <div style={{ flexBasis: '100%' }}>
            <RunStages detail={aiRun} compact />
          </div>
        </div>
      ) : null}
      {locked ? (
        <div className="cw-banner" data-tone="final">
          已定稿 v{project.finalized_version}，文稿只读。视觉风格、配音、画幅在产出里随时可改。
          <Button onClick={doUnlock}>继续修改</Button>
          <Link className="cw-btn" data-variant="primary" href={`/projects/${project.id}/outputs`}>
            去产出
          </Link>
        </div>
      ) : null}
      <div className="cw-draft-grid">
        <aside className="cw-outline" aria-label="大纲">
          <h4 className="cw-detail-h">{isVideo ? '分镜' : '大纲'}</h4>
          {isVideo ? (
            <ol>
              {draft.shots.map((s, i) => (
                <li key={i}>
                  <button type="button" className="cw-link-btn" aria-pressed={shotSel.includes(i)} onClick={() => { setScriptTab('table'); setShotSel([i]); }}>
                    <span className="cw-num">{i + 1}</span> {s.beat || s.visual.slice(0, 12) || '未命名'}
                  </button>
                  <small className="cw-num">{fmtClock(s.seconds)}</small>
                </li>
              ))}
            </ol>
          ) : heads.length ? (
            <OutlineTree
              body={draft.body}
              heads={heads}
              readOnly={locked}
              onJump={(i) => bodyRef.current?.focusParagraph(i)}
              onChange={(body) => change({ ...draft, body })}
            />
          ) : (
            <p className="cw-muted">用「## 小标题」分节后这里会出现标题树。共 {paras.length} 段。</p>
          )}
          <div className="cw-outline-foot cw-num">
            {isVideo ? `总时长 ${fmtClock(shotTotal(draft.shots))} / 目标 ${fmtClock(view.brief.duration_seconds)}` : `${chars} 字`}
          </div>
        </aside>

        <main className="cw-editor">
          {review ? (
            <SuggestionReview
              suggestion={review}
              paragraphs={view.paragraphs}
              shots={draft.shots}
              onDone={async (res) => {
                setReview(null);
                setRefreshKey((k) => k + 1);
                if (res) {
                  await load();
                  await reload();
                }
              }}
            />
          ) : (
            <div className="cw-paper-wrap">
              <div className="cw-paper">
                <Input.TextArea
                  className="cw-paper-title"
                  variant="borderless"
                  value={draft.title}
                  onChange={(e) => change({ ...draft, title: e.target.value })}
                  autoSize={{ minRows: 1, maxRows: 4 }}
                  placeholder="标题"
                  readOnly={locked}
                  maxLength={500}
                  aria-label="标题"
                />
                <Input.TextArea
                  className="cw-paper-logline"
                  variant="borderless"
                  value={draft.logline}
                  onChange={(e) => change({ ...draft, logline: e.target.value })}
                  autoSize={{ minRows: 1, maxRows: 6 }}
                  placeholder="梗概（一段）"
                  readOnly={locked}
                  maxLength={2000}
                  aria-label="梗概"
                />
                {!isVideo ? (
                  <BodyEditor
                    ref={bodyRef}
                    value={draft.body}
                    readOnly={locked}
                    placeholder="正文。回车分段；「## 」开头是小标题；引用写 [1]。"
                    onChange={(body) => change({ ...draft, body })}
                    onSelectParagraphs={(idx, hasRange) => setSel(hasRange ? idx : [])}
                  />
                ) : null}
              </div>
              {isVideo && view.brief.mode === 'music_video' && pid ? (
                <LyricTimeline
                  projectId={pid}
                  shots={draft.shots}
                  cues={draft.cues}
                  readOnly={locked}
                  selected={shotSel}
                  onSelect={setShotSel}
                  onShots={(shots) => change({ ...draft, shots })}
                  onBefore={flushed}
                  onReload={load}
                />
              ) : null}
              {isVideo ? (
                <div className="cw-scriptwrap">
                  <div className="cw-tabs" role="tablist">
                    <button type="button" role="tab" aria-selected={scriptTab === 'narration'} onClick={() => { setNarration(joinNarration(draft.shots)); setScriptTab('narration'); }}>
                      旁白全文
                    </button>
                    <button type="button" role="tab" aria-selected={scriptTab === 'table'} onClick={() => setScriptTab('table')}>
                      分镜表
                    </button>
                    <span className="cw-grow" />
                    <span className="cw-muted">{MODE_LABEL[view.brief.mode]}</span>
                  </div>
                  {scriptTab === 'table' ? (
                    <ScriptTable shots={draft.shots} target={view.brief.duration_seconds} readOnly={locked} selected={shotSel} onSelect={setShotSel}
                      onChange={(shots) => change({ ...draft, shots })}
                      onRewrite={(i) => {
                        setShotSel([i]);
                        setSide('assist');
                        setAssistSeed({ text: `改写第 ${i + 1} 镜：`, nonce: Date.now() });
                      }}
                    />
                  ) : (
                    <div className="cw-paper">
                      <textarea
                        className="cw-paper-body"
                        value={narration}
                        readOnly={locked}
                        onChange={(e) => {
                          setNarration(e.target.value);
                          const next = splitNarration(e.target.value, draft.shots);
                          if (next) change({ ...draft, shots: next, body: e.target.value });
                        }}
                        aria-label="旁白全文"
                      />
                      {!splitNarration(narration, draft.shots) ? (
                        <p className="cw-notice">
                          段落数（{splitParagraphs(narration).length}）和分镜数（{draft.shots.length}）不一致，修改不会写回分镜。可以让 AI「按段落重新分镜」，或回到分镜表逐镜编辑。
                        </p>
                      ) : null}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          )}
        </main>

        <aside className="cw-side">
          <div className="cw-tabs" role="tablist">
            {(
              [
                ['assist', 'AI 助手'],
                ['brief', '设定'],
                ['versions', '版本'],
                ['sources', '来源'],
              ] as const
            ).map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={side === id} onClick={() => setSide(id)}>
                {label}
              </button>
            ))}
          </div>
          {side === 'assist' ? (
            <AssistantPanel
              projectId={project.id}
              scope={scope}
              disabled={locked ? '已定稿，点「继续修改」后才能让 AI 修改' : review ? '先处理当前这组建议' : null}
              beforeSend={beforeSend}
              onSuggestion={(s) => {
                if (s.status === 'pending' || s.status === 'partial') setReview(s);
              }}
              refreshKey={refreshKey}
              seed={assistSeed}
            />
          ) : side === 'brief' ? (
            <div className="cw-kv">
              <div>
                <dt>主题</dt>
                <dd>{view.brief.theme}</dd>
              </div>
              <div>
                <dt>内容形态</dt>
                <dd>{MODE_LABEL[view.brief.mode]}</dd>
              </div>
              {isVideo ? (
                <div>
                  <dt>时长</dt>
                  <dd className="cw-num">{view.brief.duration_seconds} 秒</dd>
                </div>
              ) : null}
              <div>
                <dt>受众</dt>
                <dd>{view.brief.audience || '—'}</dd>
              </div>
              <div>
                <dt>语气</dt>
                <dd>{view.brief.tone || '—'}</dd>
              </div>
              <div>
                <dt>创作思路</dt>
                <dd style={{ whiteSpace: 'pre-wrap' }}>{view.brief.intent || '—'}</dd>
              </div>
              <Link className="cw-btn" href={`/projects/${project.id}/idea`} style={{ marginTop: 10 }}>
                去改设定
              </Link>
            </div>
          ) : side === 'versions' ? (
            <VersionsPanel
              projectId={project.id}
              refreshKey={refreshKey}
              current={{ draft, paragraphs: view.paragraphs }}
              readOnly={locked}
              onRestored={async () => {
                await load();
                await reload();
                setRefreshKey((k) => k + 1);
              }}
            />
          ) : (
            <SourcesPanel sources={project.sources} onInsertCite={(n) => insertAtCursor(`[${n}]`)} onInsertQuote={(t) => insertAtCursor(`\n\n> ${t}\n\n`)} />
          )}
        </aside>
      </div>
      <footer className="cw-draftbar">
        <span className="cw-num">{chars.toLocaleString('zh-CN')} 字</span>
        <span className="cw-num">预计朗读 {fmtClock(readSeconds(chars))}</span>
        <span className="cw-savestate" data-state={save.state} aria-live="polite">
          {save.state === 'pending' ? <i aria-hidden /> : null}
          {saveText}
        </span>
        <span className="cw-grow" />
        <MemeInsert onInsert={(t) => insertAtCursor(t)} disabled={locked} />
        {locked ? null : (
          <Button onClick={() => void startAiDraft()} disabled={aiStarting || aiActive} title="写手 → 审校 → 写手修改，写完存成新版本">
            {aiActive ? 'AI 写作中…' : aiStarting ? '启动中…' : 'AI 写全文'}
          </Button>
        )}
        <Button onClick={saveVersion} disabled={locked}>
          保存版本 Ctrl S
        </Button>
        {/* 已定稿时「继续修改」只在顶部横幅出现一次（评审 #4 P1-5） */}
        {locked ? null : (
          <Button variant="primary" onClick={() => setFinalizeOpen(true)} disabled={!draft.body.trim() && !draft.shots.length}>
            定稿
          </Button>
        )}
      </footer>
      <Modal open={finalizeOpen} onCancel={() => setFinalizeOpen(false)} onOk={doFinalize} okText="定稿" title="定稿" destroyOnHidden>
        <p>将锁定：选题、内容形态、内容模板、受众、语气、创作思路{isVideo ? '、时长' : ''}、成稿。</p>
        <p className="cw-muted">视觉风格、配音、画幅在产出里随时可改，不影响定稿。之后可以「继续修改」解锁，下一次定稿生成新版本。</p>
      </Modal>
    </div>
  );
}
