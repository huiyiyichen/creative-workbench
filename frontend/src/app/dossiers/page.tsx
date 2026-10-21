'use client';

/**
 * 专题（改造方案 5.5）：持续 3 天以上的事件、每个追踪词、你关注的话题。
 * 未关注、30 天没有新内容的自动专题归档，仍可搜索。
 */

import { EmptyInstrument, ScanSkeleton } from '@/design/instrument';
import Link from 'next/link';
import { Input, message } from 'antd';
import { Plus } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Button, CwPage, SearchField, Segmented, TopBar } from '@/design/components';
import { GapSpark, StatusTag, platformName } from '@/design/discover';
import { color } from '@/design/tokens';
import { discoverApi, type DossierSummary } from '@/lib/api/_discover';
import { relativeTime } from '@/lib/collection';
import { bucketSeries, topPlatforms } from '@/lib/discover';

const KIND_LABEL = { event: '事件', watch_term: '追踪词', manual: '关注' } as const;

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

export default function DossiersPage() {
  const [archived, setArchived] = useState<'active' | 'archived'>('active');
  const [q, setQ] = useState('');
  const [items, setItems] = useState<DossierSummary[] | null>(null);
  const [newTopic, setNewTopic] = useState('');

  const load = useCallback(() => {
    discoverApi
      .dossiers({ archived: archived === 'archived', q: q || undefined })
      .then((r) => setItems(r.items))
      .catch((err) => message.error(errText(err)));
  }, [archived, q]);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  const follow = async () => {
    const word = newTopic.trim();
    if (!word) return;
    try {
      await discoverApi.follow({ title: word, query: word });
      setNewTopic('');
      message.success(`已关注「${word}」`);
      load();
    } catch (err) {
      message.error(errText(err));
    }
  };

  // 「关注一个话题」放进网格最后的空槽卡里，页面上只留一个输入框
  const followSlot = (
    <div className="cw-card cw-dossier-card cw-dossier-slot">
      <span className="cw-muted" style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        <Plus size={12} /> 关注一个话题
      </span>
      <p className="cw-muted">输入标题关键词，之后出现相关内容就会归到这个专题里。</p>
      <div className="cw-row">
        <Input placeholder="例如：Agent 记忆" value={newTopic} onChange={(e) => setNewTopic(e.target.value)} onPressEnter={follow} />
        <Button onClick={follow} disabled={!newTopic.trim()}>
          关注
        </Button>
      </div>
    </div>
  );

  return (
    <CwPage>
      <TopBar
        title="专题"
        sub={
          items ? (
            <span className="cw-num">
              {items.length} 个{archived === 'archived' ? '已归档' : '进行中'} · 共 {items.reduce((n, d) => n + (d.content_count ?? 0), 0)} 条内容
            </span>
          ) : undefined
        }
      />
      <div className="cw-filters">
        <Segmented
          label="范围"
          value={archived}
          onChange={setArchived}
          options={[
            { value: 'active', label: '进行中' },
            { value: 'archived', label: '已归档' },
          ]}
        />
        {/* 少于 10 个专题不需要搜索框（评审 #3 1.12） */}
        {q || (items && items.length >= 10) ? <SearchField placeholder="搜索专题" width={240} value={q} onChange={setQ} /> : null}
      </div>
      {!items ? (
        <ScanSkeleton shape="cards" height={240} />
      ) : items.length === 0 ? (
        archived === 'archived' ? (
          <EmptyInstrument kind="dark" title="没有归档的专题" />
        ) : (
          <EmptyInstrument
            kind="flat"
            title="还没有专题"
            reason="持续 3 天以上的事件和每个追踪词会自动成为专题；也可以在热点 · 升温里点「关注」。"
            actions={
              <Link className="cw-btn" data-variant="primary" href="/hot?tab=rising">
                去热点看升温
              </Link>
            }
          />
        )
      ) : (
        <div className="cw-dossier-grid cw-stagger" data-few={items.length <= 3 ? 'true' : undefined}>
          {items.map((d) => (
            <Link key={d.id} href={`/dossiers/${d.id}`} className="cw-card cw-dossier-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="cw-muted" style={{ fontSize: 12 }}>
                  {KIND_LABEL[d.kind]}
                  {d.followed ? ' · 已关注' : ''}
                </span>
                <span className="cw-grow" />
                {d.status ? <StatusTag status={d.status} /> : null}
              </div>
              <h3>{d.title}</h3>
              <div className="cw-dossier-count">
                <div>
                  已收集 <b className="cw-num">{d.content_count ?? 0}</b> 条
                </div>
                {d.latest_title ? <span title={d.latest_title}>最新：{d.latest_title}</span> : null}
              </div>
              <GapSpark values={bucketSeries(d.series, 3)} width={items.length <= 3 ? 360 : 260} label={`${d.title} 热度曲线`} accent={color.rd} />
              <div className="cw-rise-plats">
                {topPlatforms(d.platforms, 4).map(([p, n]) => (
                  <span key={p}>
                    {platformName(p)} <b className="cw-num">{n}</b>
                  </span>
                ))}
                <span className="cw-grow" />
                {d.last_seen_at ? <span className="cw-muted">最近 {relativeTime(d.last_seen_at)}</span> : null}
              </div>
            </Link>
          ))}
          {archived === 'active' ? followSlot : null}
        </div>
      )}
    </CwPage>
  );
}
