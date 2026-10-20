'use client';

/**
 * 采集页阶段 1 部件：添加信源、漏斗设置、平台接入、最近采到。
 * 外观用 cw-* 自建组件；antd 只用于 Modal / Drawer / Input / Select / InputNumber / Checkbox。
 */

import { Checkbox, Drawer, Input, InputNumber, Modal, Select } from 'antd';
import { KeyRound, Plus, Search } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Button, Chip, Cover, Num, Sparkline, StatusDot } from '@/design/components';
import { mediaColor } from '@/design/tokens';
import {
  collectionApi,
  mediaUrl,
  type FunnelSettings,
  type PlatformInfo,
  type RecentItem,
  type RecognizedSource,
  type SourceHealthRow,
  type SourceKind,
} from '@/lib/api/_collection';
import {
  KIND_LABEL,
  METRIC_LABEL,
  PLATFORM_LABEL,
  analysisLabel,
  compactNumber,
  formatDuration,
  primarySeries,
  relativeTime,
} from '@/lib/collection';

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

const CAPABILITY_LABEL: Record<string, string> = {
  list_posts: '订阅',
  search: '搜索',
  list_ranking: '榜单',
  fetch_comments: '评论',
  fetch_subtitles: '字幕',
};

// ── 添加信源 ─────────────────────────────────────────────────────

export function AddSourceModal({
  open,
  onClose,
  onAdded,
  searchable,
}: {
  open: boolean;
  onClose: () => void;
  onAdded: (message: string) => void;
  searchable: PlatformInfo[];
}) {
  const [text, setText] = useState('');
  const [draft, setDraft] = useState<RecognizedSource | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) {
      setText('');
      setDraft(null);
      setError(null);
    }
  }, [open]);

  const recognize = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setDraft(await collectionApi.recognize(text.trim()));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const res = await collectionApi.createSource({ ...draft, sync_now: true });
      const sync = res.sync;
      onAdded(
        sync
          ? sync.status === 'failed'
            ? `已添加「${res.name}」，首次同步失败：${sync.error_message ?? '未知原因'}`
            : `已添加「${res.name}」，首次同步新增 ${sync.new ?? 0} 条`
          : `已添加「${res.name}」`,
      );
      onClose();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const searchOptions = searchable.filter((p) => p.capabilities.search);

  return (
    <Modal
      title="添加信源"
      open={open}
      onCancel={onClose}
      footer={null}
      width={560}
      destroyOnHidden
    >
      <div className="cw-form">
        <label>
          粘贴链接或输入关键词
          <Input.Search
            value={text}
            onChange={(e) => setText(e.target.value)}
            onSearch={recognize}
            enterButton={<Search size={14} />}
            placeholder="例如 https://space.bilibili.com/946974 或「Opus 5.5 视频」"
            loading={busy && !draft}
            autoFocus
          />
        </label>
        {draft ? (
          <>
            <label>
              类型
              <Select<SourceKind>
                value={draft.kind}
                onChange={(kind) => setDraft({ ...draft, kind })}
                options={(['subscription', 'keyword', 'list'] as SourceKind[]).map((k) => ({ value: k, label: KIND_LABEL[k] }))}
              />
            </label>
            <label>
              名称
              <Input value={draft.name} maxLength={255} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </label>
            {draft.kind === 'keyword' ? (
              <label>
                在这些平台搜索
                <Checkbox.Group
                  value={draft.platforms ?? []}
                  onChange={(v) => setDraft({ ...draft, platforms: v as string[] })}
                  options={searchOptions.map((p) => ({
                    value: p.platform,
                    // YouTube 搜索必须有 Key；GitHub 的 Token 只是提高限额
                    label: `${p.label}${p.platform === 'youtube' && !p.has_key ? '（需填 Key）' : ''}`,
                  }))}
                />
              </label>
            ) : (
              <div className="cw-cell-sub">
                {PLATFORM_LABEL[draft.platform ?? ''] ?? draft.platform ?? '网页'} · {draft.source_type} ·{' '}
                <span className="cw-num">{draft.url}</span>
              </div>
            )}
          </>
        ) : null}
        {error ? <div className="cw-error">{error}</div> : null}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" icon={<Plus />} disabled={!draft || busy} onClick={submit}>
            {busy && draft ? '添加并同步中…' : '添加并同步'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ── 漏斗设置（预算、初筛线） ──────────────────────────────────────

export function FunnelSettingsModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [cfg, setCfg] = useState<FunnelSettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    collectionApi.funnelSettings().then(setCfg).catch((err) => setError(errorText(err)));
  }, [open]);

  const save = async () => {
    if (!cfg) return;
    try {
      await collectionApi.saveFunnelSettings({
        daily_budget: cfg.daily_budget,
        triage_threshold: cfg.triage_threshold,
        quick_routing_group: cfg.quick_routing_group || undefined,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  };

  return (
    <Modal title="分析漏斗设置" open={open} onCancel={onClose} onOk={save} okText="保存" cancelText="取消" width={440}>
      {cfg ? (
        <div className="cw-form">
          <label>
            每日分析预算（元，快速判断与完整分析共用）
            <InputNumber min={0} max={10000} step={1} value={cfg.daily_budget}
              onChange={(v) => setCfg({ ...cfg, daily_budget: Number(v ?? 0) })} style={{ width: '100%' }} />
          </label>
          <label>
            初筛过线分（0–100，低于此分不进快速判断）
            <InputNumber min={0} max={100} step={5} value={cfg.triage_threshold}
              onChange={(v) => setCfg({ ...cfg, triage_threshold: Number(v ?? 0) })} style={{ width: '100%' }} />
          </label>
          <label>
            快速判断模型路由组（留空用默认）
            <Input value={cfg.quick_routing_group ?? ''} maxLength={64}
              onChange={(e) => setCfg({ ...cfg, quick_routing_group: e.target.value || null })} placeholder="analysis_lite" />
          </label>
          <div className="cw-cell-sub">
            今日已花 <Num value={cfg.budget.spent} digits={2} /> 元。到上限即停，剩余排到次日；排队超过 3 天的不再自动分析。点开、收藏、用作项目来源时按需分析，不受预算限制。
          </div>
        </div>
      ) : (
        <div className="cw-empty">{error ?? '加载中'}</div>
      )}
      {cfg && error ? <div className="cw-error">{error}</div> : null}
    </Modal>
  );
}

export function BudgetLine({ budget }: { budget: { budget: number; spent: number } | undefined }) {
  if (!budget) return null;
  const ratio = budget.budget > 0 ? Math.min(1, budget.spent / budget.budget) : 1;
  return (
    <div className="cw-budget">
      今日分析
      <span className="cw-num">
        {budget.spent.toFixed(2)} / {budget.budget.toFixed(2)} 元
      </span>
      <span className="cw-budget-bar" data-over={budget.spent >= budget.budget ? 'true' : undefined}>
        <i style={{ width: `${ratio * 100}%` }} />
      </span>
    </div>
  );
}

// ── 平台接入 ─────────────────────────────────────────────────────

/** 抖音 / 小红书：本机浏览器登录态与最近一次采集结果 */
function BrowserLogin({ p, onChanged }: { p: PlatformInfo; onChanged: (message: string) => void }) {
  const st = p.browser_status;
  const ago = (ts?: number) => (ts ? new Date(ts * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : null);
  const failed = Boolean(st?.last_error);
  const tone = failed ? 'warn' : st?.last_ok_at || st?.login_at ? 'ok' : 'off';
  const label = failed
    ? st?.last_error?.includes('登录') ? '登录失效' : st?.last_error?.includes('验证码') ? '需要验证' : '最近失败'
    : st?.last_ok_at
      ? `正常 · ${ago(st.last_ok_at)}`
      : st?.login_at
        ? `已登录 · ${ago(st.login_at)}`
        : '未登录';
  const open = async () => {
    try {
      const r = await collectionApi.openPlatformLogin(p.platform);
      onChanged(r.already ? `${p.label} 登录窗口已经打开` : `已在本机打开 ${p.label} 登录窗口，登录后关掉窗口即可`);
    } catch (err) {
      onChanged(errorText(err));
    }
  };
  return (
    <span className="cw-row" style={{ gap: 8 }} title={st?.last_error || '本机 Edge 浏览器采集，全局一次一个页面、低频'}>
      <StatusDot tone={tone} />
      <span className="cw-muted">{label}</span>
      <Button variant="ghost" onClick={open}>
        {failed || !st?.login_at ? '打开登录窗口' : '重新登录'}
      </Button>
    </span>
  );
}

export function PlatformList({ items, onChanged }: { items: PlatformInfo[]; onChanged: (message: string) => void }) {
  const [editing, setEditing] = useState<PlatformInfo | null>(null);
  const [value, setValue] = useState('');

  const save = async () => {
    if (!editing) return;
    try {
      const res = await collectionApi.setPlatformKey(editing.platform, value.trim() || null);
      onChanged(res.has_key ? `${editing.label} Key 已保存` : `${editing.label} Key 已清除`);
      setEditing(null);
      setValue('');
    } catch (err) {
      onChanged(errorText(err));
    }
  };

  if (!items.length) return <div className="cw-empty">加载中</div>;
  return (
    <>
      <ul className="cw-platforms">
        {items.map((p) => (
          <li key={p.platform}>
            <span className="cw-cell-title">{p.label}</span>
            <span className="cw-dimtext">
              {Object.entries(CAPABILITY_LABEL)
                .filter(([cap]) => p.capabilities[cap])
                .map(([, label]) => label)
                .join(' · ')}
            </span>
            {p.browser ? (
              <BrowserLogin p={p} onChanged={onChanged} />
            ) : p.needs_key ? (
              <Button variant="ghost" icon={<KeyRound />} onClick={() => { setEditing(p); setValue(''); }}>
                <StatusDot tone={p.has_key ? 'ok' : p.platform === 'youtube' ? 'warn' : 'off'} />
                {p.has_key ? 'Key 已填' : p.platform === 'youtube' ? '填 Key' : '填 Token（可选）'}
              </Button>
            ) : (
              <span className="cw-muted">无需 Key</span>
            )}
          </li>
        ))}
      </ul>
      <Modal title={`${editing?.label ?? ''} API Key`} open={Boolean(editing)} onCancel={() => setEditing(null)} onOk={save}
        okText="保存" cancelText="取消" width={420}>
        <div className="cw-form">
          <label>
            {editing?.platform === 'youtube' ? 'YouTube Data API v3 Key（搜索、详情、评论需要）' : 'GitHub Token（提高接口限额）'}
            <Input.Password value={value} onChange={(e) => setValue(e.target.value)} placeholder="留空保存即清除" autoComplete="off" />
          </label>
          <div className="cw-cell-sub">加密保存在本机数据库，只用于请求该平台。</div>
        </div>
      </Modal>
    </>
  );
}

// ── 最近采到（封面 + 观测曲线） ────────────────────────────────────

function RecentCard({ item }: { item: RecentItem }) {
  const metric = primarySeries(item.series);
  const points = metric ? item.series[metric].map((p) => p.value) : [];
  const duration = formatDuration(item.duration);
  const kind = item.media_type ?? 'article';
  return (
    <article className="cw-recent-item" data-orientation={item.orientation ?? undefined}>
      <Cover
        src={item.cover_asset_id ? mediaUrl(item.cover_asset_id) : null}
        title={item.title}
        color={item.cover_color}
        orientation={item.orientation}
        kind={kind}
        badge={duration}
      />
      <a href={item.url} target="_blank" rel="noreferrer" title={item.title}>
        {item.title}
      </a>
      <div className="cw-recent-meta">
        <span>{PLATFORM_LABEL[item.platform ?? ''] ?? item.platform ?? '—'}</span>
        <span className="cw-num">{relativeTime(item.published_at ?? item.crawled_at)}</span>
        <span className="cw-grow" />
        <Chip color={item.analysis_level === 'full' ? mediaColor.repo : undefined}>{analysisLabel(item)}</Chip>
      </div>
      <div className="cw-recent-meta">
        {metric ? (
          <span>
            {METRIC_LABEL[metric] ?? metric} <span className="cw-num">{compactNumber(item.latest[metric])}</span>
          </span>
        ) : (
          <span className="cw-muted">无平台指标</span>
        )}
        <span className="cw-grow" />
        <Sparkline values={points} label={`${METRIC_LABEL[metric ?? ''] ?? '指标'}观测：${points.join('、')}`}
          color={(mediaColor as Record<string, string>)[kind]} width={96} height={22} />
      </div>
      <div className="cw-recent-meta">
        初筛 <Num value={item.triage_score} />
      </div>
    </article>
  );
}

export function RecentDrawer({ source, onClose }: { source: SourceHealthRow | null; onClose: () => void }) {
  const [items, setItems] = useState<RecentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!source) return;
    setItems(null);
    setError(null);
    collectionApi
      .recent(source.id, 24)
      .then((res) => setItems(res.items))
      .catch((err) => setError(errorText(err)));
  }, [source]);

  return (
    <Drawer
      title={source ? `${source.name} · 最近采到` : ''}
      open={Boolean(source)}
      onClose={onClose}
      size={760}
      destroyOnHidden
    >
      {error ? <div className="cw-error">{error}</div> : null}
      {!items && !error ? <div className="cw-empty">加载中</div> : null}
      {items && !items.length ? <div className="cw-empty">还没有采到内容</div> : null}
      {items?.length ? (
        <div className="cw-recent">
          {items.map((item) => (
            <RecentCard key={item.id} item={item} />
          ))}
        </div>
      ) : null}
    </Drawer>
  );
}
