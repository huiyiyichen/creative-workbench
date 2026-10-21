'use client';

/**
 * 搜索：先搜库里已有的（采集内容、灵感库、随笔、项目、产出、报告），
 * 再按关键词去各平台现抓——抓回来的内容进今日信息流；勾选「持续追踪」则成为追踪词，以后定时采集。
 */

import { EmptyInstrument, ScanSkeleton, StatusLamp } from '@/design/instrument';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Search as SearchIcon, Radar } from 'lucide-react';
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, CwPage, Segmented, TopBar } from '@/design/components';
import { RecentCard } from '@/app/sources/_parts';
import { PLATFORM_LABEL, relativeTime } from '@/lib/collection';
import { splitHits, uniqBy } from '@/lib/text';
import {
  SEARCH_GROUP_LABEL,
  SEARCH_GROUP_ORDER,
  searchApi,
  type CrawlPlatform,
  type CrawlResult,
  type SearchGroup,
  type SearchResult,
} from '@/lib/api/_search';

type Tab = 'all' | SearchGroup;

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

/** 命中词高亮：英文整词、全部命中；中文子串 */
function Highlight({ text, q }: { text: string; q: string }) {
  return (
    <>
      {splitHits(text, q).map((p, i) => (p.hit ? <mark key={i} className="cw-hit">{p.text}</mark> : <span key={i}>{p.text}</span>))}
    </>
  );
}

function LocalResults({ q, data, error }: { q: string; data: SearchResult | null; error: string | null }) {
  const [tab, setTab] = useState<Tab>('all');
  useEffect(() => setTab('all'), [q]);
  const groups = useMemo(
    () => SEARCH_GROUP_ORDER.filter((g) => (data?.groups[g]?.length ?? 0) > 0),
    [data],
  );
  if (error) return <p className="cw-error">{error}</p>;
  if (!data) return <ScanSkeleton height={220} label="在库里搜索" />;
  if (!data.total) {
    return <EmptyInstrument kind="dark" title={`库里还没有和「${q}」相关的内容`} reason="右边可以一键去各平台现抓；抓回来的会直接进库，也能顺手设成追踪词。" />;
  }
  const shown = tab === 'all' ? groups : groups.filter((g) => g === tab);
  return (
    <>
      <Segmented<Tab>
        label="结果类型"
        value={tab}
        onChange={setTab}
        options={[
          { value: 'all', label: `全部 ${data.total}` },
          ...groups.map((g) => ({ value: g, label: `${SEARCH_GROUP_LABEL[g]} ${data.groups[g]!.length}` })),
        ]}
      />
      {shown.map((g) => (
        <section key={g} className="cw-search-group">
          <h3>{SEARCH_GROUP_LABEL[g]}</h3>
          <ul>
            {uniqBy(data.groups[g]!, (h) => h.href).map((h) => (
              <li key={h.href}>
                <Link href={h.href}>
                  <Highlight text={h.title} q={q} />
                </Link>
                {h.snippet ? (
                  <p>
                    <Highlight text={h.snippet} q={q} />
                  </p>
                ) : null}
                <div className="cw-search-meta">
                  {h.platform ? <span>{PLATFORM_LABEL[h.platform] ?? h.platform}</span> : null}
                  {h.at ? <span className="cw-num">{relativeTime(h.at)}</span> : null}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}

function CrawlPanel({ q, onDone }: { q: string; onDone: () => void }) {
  const [platforms, setPlatforms] = useState<CrawlPlatform[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [track, setTrack] = useState(false);
  const [tracking, setTracking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CrawlResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    searchApi
      .platforms()
      .then((r) => {
        setPlatforms(r.items);
        setPicked(r.items.filter((p) => !p.needs_key || p.has_key).map((p) => p.platform));
      })
      .catch((err) => setError(errText(err)));
  }, []);

  useEffect(() => {
    setResult(null);
    setError(null);
    searchApi
      .tracking(q)
      .then((r) => {
        setTracking(r.tracking);
        setTrack(r.tracking);
      })
      .catch(() => setTracking(false));
  }, [q]);

  const toggle = (p: string) => setPicked((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]));

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await searchApi.crawl({ q, platforms: picked, track });
      setResult(r);
      setTracking(r.tracking);
      if (r.error_message) setError(r.error_message);
      onDone();
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  };

  const names = picked.map((p) => platforms.find((x) => x.platform === p)?.label ?? p).join('、');
  return (
    <section className="cw-instrument cw-crawl">
      <div className="cw-card-head">
        <Radar size={15} aria-hidden />
        去平台抓「{q}」
        <span className="cw-grow" />
        {tracking ? <span className="cw-chip">已在追踪</span> : null}
      </div>
      <div className="cw-crawl-platforms" role="group" aria-label="抓取平台">
        {platforms.map((p) => {
          const blocked = p.needs_key && !p.has_key;
          return (
            <button
              key={p.platform}
              type="button"
              className="cw-pill"
              aria-pressed={picked.includes(p.platform)}
              disabled={blocked || busy}
              title={blocked ? '要先在「信源 · 平台」里填 API Key' : undefined}
              onClick={() => toggle(p.platform)}
            >
              {p.label}
              {blocked ? <small> · 缺 Key</small> : null}
            </button>
          );
        })}
      </div>
      <label className="cw-crawl-track">
        <input className="cw-check" type="checkbox" checked={track} disabled={busy} onChange={(e) => setTrack(e.target.checked)} />
        以后自动追踪（每 2 小时抓一次，会出现在「专题」里）
      </label>
      {busy || result ? (
        <ul className="cw-radar" aria-label="各平台进度">
          {picked.map((pk) => (
            <li key={pk}>
              <StatusLamp tone={busy ? 'run' : error ? 'bad' : 'ok'} label={platforms.find((x) => x.platform === pk)?.label || pk} />
              <span className="cw-radar-bar" data-busy={busy ? 'true' : undefined}>
                <i />
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="cw-row">
        <Button variant="primary" icon={<SearchIcon size={14} />} disabled={busy || !picked.length} onClick={run}>
          {busy ? '抓取中…' : '抓取'}
        </Button>
        <span className="cw-muted" aria-live="polite">
          {busy ? `正在 ${names} 搜索，通常十几秒到一分钟` : null}
          {!busy && result
            ? `抓到 ${result.fetched} 条，新入库 ${result.new} 条${result.duplicates ? `，${result.duplicates} 条之前已有` : ''}${
                result.tracking ? '；已加入追踪' : ''
              }`
            : null}
        </span>
      </div>
      {error ? <p className="cw-error">{error}</p> : null}
      {result?.items.length ? (
        <>
          <div className="cw-recent cw-crawl-items">
            {result.items.map((it) => (
              <RecentCard key={it.id} item={it} />
            ))}
          </div>
          <div className="cw-row">
            <Link className="cw-btn" data-variant="ghost" href="/">
              去今日看
            </Link>
            {result.tracking ? (
              <Link className="cw-btn" data-variant="ghost" href="/dossiers">
                打开专题
              </Link>
            ) : null}
          </div>
        </>
      ) : null}
      {result && !result.items.length && !error ? (
        <p className="cw-empty">这次没抓到新内容。换个说法，或者多选几个平台再试。</p>
      ) : null}
    </section>
  );
}

function SearchInner() {
  const router = useRouter();
  const params = useSearchParams();
  const q = (params.get('q') || '').trim();
  const [draft, setDraft] = useState(q);
  const [data, setData] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => setDraft(q), [q]);
  useEffect(() => {
    if (!q) inputRef.current?.focus();
  }, [q]);

  const load = useCallback(() => {
    if (!q) return;
    setError(null);
    searchApi
      .search(q, { limit: 20 })
      .then(setData)
      .catch((err) => setError(errText(err)));
  }, [q]);

  useEffect(() => {
    setData(null);
    load();
  }, [load]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const v = draft.trim();
    router.push(v ? `/search?q=${encodeURIComponent(v)}` : '/search');
  };

  // 有关键词时搜索框放进左栏，和右侧「去平台抓」面板顶边对齐
  const searchForm = (
    <form className="cw-search-form" onSubmit={submit} role="search">
      <SearchIcon size={16} aria-hidden />
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="输入关键词：先搜库里已有的，再去各平台抓"
        aria-label="搜索关键词"
        maxLength={100}
      />
      <kbd className="cw-kbd" aria-hidden>
        ⏎
      </kbd>
      <button type="submit" className="cw-sr-only">
        搜索
      </button>
    </form>
  );
  return (
    <CwPage>
      <TopBar title="搜索" sub={q && data ? <span className="cw-num">{data.total} 条库内结果</span> : undefined} />
      {q ? null : searchForm}
      {q ? (
        <div className="cw-search-layout">
          <div className="cw-search-local">
            {searchForm}
            <LocalResults q={q} data={data} error={error} />
          </div>
          <CrawlPanel q={q} onDone={load} />
        </div>
      ) : (
        <EmptyInstrument
          kind="flat"
          title="输入一个关键词"
          reason="库里有的（内容、灵感、随笔、项目、报告）先列出来；想看最新的，可以一键去 B站、YouTube、抖音、小红书等平台现抓。快捷键：任意页面按 / 或 Ctrl K。"
        />
      )}
    </CwPage>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={null}>
      <SearchInner />
    </Suspense>
  );
}
