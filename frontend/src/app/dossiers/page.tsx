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
import { Button, CwPage, Segmented, TopBar } from '@/design/components';
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

  return (
    <CwPage>
      <TopBar title="专题" sub="一个话题从出现到现在的完整经过" />
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
        <Input.Search allowClear placeholder="搜索专题" style={{ width: 240 }} value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="cw-grow" />
        <Input placeholder="关注一个话题（按标题关键词）" style={{ width: 240 }} value={newTopic} onChange={(e) => setNewTopic(e.target.value)} onPressEnter={follow} />
        <Button icon={<Plus size={15} />} onClick={follow} disabled={!newTopic.trim()}>
          关注
        </Button>
      </div>
      {!items ? (
        <ScanSkeleton height={240} />
      ) : items.length === 0 ? (
        archived === 'archived' ? (
          <EmptyInstrument kind="dark" title="没有归档的专题" />
        ) : (
          <EmptyInstrument
            kind="flat"
            title="还没有专题"
            reason="持续 3 天以上的事件和每个追踪词会自动成为专题；也可以在上面输入一个话题直接关注，或在热点 · 升温里点「关注」。"
            actions={
              <Link className="cw-btn" data-variant="primary" href="/hot?tab=rising">
                去热点看升温
              </Link>
            }
          />
        )
      ) : (
        <div className="cw-dossier-grid cw-stagger">
          {items.map((d) => (
            <Link key={d.id} href={`/dossiers/${d.id}`} className="cw-card cw-dossier-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="cw-muted" style={{ fontSize: 12 }}>
                  {KIND_LABEL[d.kind]}
                  {d.followed ? ' · 已关注' : ''}
                </span>
                <span className="cw-grow" />
                <StatusTag status={d.status} />
              </div>
              <h3>{d.title}</h3>
              <GapSpark values={bucketSeries(d.series, 3)} width={260} label={`${d.title} 热度曲线`} accent={color.rd} />
              <div className="cw-rise-plats">
                {topPlatforms(d.platforms, 4).map(([p, n]) => (
                  <span key={p}>
                    {platformName(p)} <b className="cw-num">{n}</b>
                  </span>
                ))}
                <span className="cw-grow" />
                <span className="cw-muted">最近 {relativeTime(d.last_seen_at)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </CwPage>
  );
}
