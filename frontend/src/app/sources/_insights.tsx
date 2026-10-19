'use client';

/**
 * 采集页其余部分（改造方案 3.8）：建议、覆盖（漏采）、完整度、信源价值、结构。
 * 建议都是「点一下才执行」的动作（3.9）。
 */

import Link from 'next/link';
import { message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, MiniBars, SectionHead } from '@/design/components';
import { color } from '@/design/tokens';
import { collectionApi, type CollectionInsights } from '@/lib/api/_collection';
import { PLATFORM_LABEL } from '@/lib/collection';
import { MEDIA_LABEL, percent } from '@/lib/discover';

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

function Share({ rows, label }: { rows: { key: string; count: number }[]; label: (k: string) => string }) {
  const total = rows.reduce((a, r) => a + r.count, 0) || 1;
  return (
    <div className="cw-plat-bars" style={{ ['--c' as string]: color.cy }}>
      {rows.slice(0, 6).map((r) => (
        <div key={r.key}>
          <span>{label(r.key)}</span>
          <s style={{ width: `${(r.count / total) * 100}%` }} />
          <b className="cw-num">{Math.round((r.count / total) * 100)}%</b>
        </div>
      ))}
    </div>
  );
}

export function SuggestionsCard({ onChanged, onAddSource }: { onChanged: () => void; onAddSource: () => void }) {
  const [data, setData] = useState<CollectionInsights | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(() => {
    collectionApi.insights().then(setData).catch(() => setData(null));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const run = async (i: number) => {
    const s = data?.suggestions[i];
    if (!s) return;
    setBusy(i);
    try {
      if (s.kind === 'disable' && s.source_id) await collectionApi.updateSource(s.source_id, { enabled: false });
      else if (s.kind === 'stale' && s.source_id) await collectionApi.syncSource(s.source_id);
      else if (s.kind === 'subscribe' && s.author_url) {
        const rec = await collectionApi.recognize(s.author_url);
        await collectionApi.createSource({ ...rec, sync_now: true });
      } else if (s.kind === 'structure') {
        onAddSource();
        return;
      }
      message.success('已执行');
      load();
      onChanged();
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(null);
    }
  };

  if (!data || data.suggestions.length === 0) return null;
  return (
    <>
      <SectionHead title="建议" note="点一下才执行" />
      <Card>
        <ul className="cw-suggest">
          {data.suggestions.map((s, i) => (
            <li key={i}>
              <span className="cw-grow">{s.text}</span>
              <Button disabled={busy === i} onClick={() => run(i)}>
                {s.action}
              </Button>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}

export function InsightsSections() {
  const [data, setData] = useState<CollectionInsights | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    collectionApi.insights().then(setData).catch((err) => setError(errText(err)));
  }, []);

  if (error) return <div className="cw-error">{error}</div>;
  if (!data) return null;
  const v = data.value;
  return (
    <>
      <div className="cw-grid-2">
        <div>
          <SectionHead title="覆盖" note="48 小时内热榜 / 追踪词有、订阅里 0 条" />
          <Card>
            {data.coverage.length === 0 ? (
              <div className="cw-muted">没有漏采</div>
            ) : (
              <ul className="cw-report-list">
                {data.coverage.slice(0, 10).map((c) => (
                  <li key={c.event_id}>
                    <span className="cw-grow">{c.text}</span>
                    {c.content_id ? <Link href={`/items/${c.content_id}`}>看条目</Link> : null}
                    <Link href="/hot?tab=terms">加追踪词</Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <div>
          <SectionHead title="结构" note="近 30 天内容占比" />
          <Card>
            <div style={{ display: 'grid', gap: 14 }}>
              <div>
                <div className="cw-muted" style={{ fontSize: 12, marginBottom: 6 }}>平台</div>
                <Share rows={data.structure.platform} label={(k) => PLATFORM_LABEL[k] || k} />
              </div>
              <div>
                <div className="cw-muted" style={{ fontSize: 12, marginBottom: 6 }}>形态</div>
                <Share rows={data.structure.media_type} label={(k) => MEDIA_LABEL[k] || k} />
              </div>
            </div>
          </Card>
        </div>
      </div>

      <SectionHead title="信源价值" note={`近 ${v.days} 天；值得做率的分母只算已完整分析`}>
        <span className="cw-muted" style={{ fontSize: 12 }}>收藏趋势</span>
        <MiniBars values={v.favorite_trend.map((w) => w.favorites)} color={color.gr} label="近 8 周每周收藏数" />
      </SectionHead>
      <Card className="cw-scroll-x">
        <table className="cw-table">
          <thead>
            <tr>
              <th>信源</th>
              <th>产出</th>
              <th>已分析</th>
              <th>值得做</th>
              <th>被收藏</th>
              <th>用进项目</th>
              <th>重复率</th>
              <th>最先报道</th>
              <th>分析花费</th>
            </tr>
          </thead>
          <tbody>
            {v.sources.map((s) => (
              <tr key={s.source_id}>
                <td>{s.name}</td>
                <td className="cw-num">{s.items}</td>
                <td className="cw-num">{s.analyzed}</td>
                <td className="cw-num">
                  {s.worth} <span className="cw-muted">{s.worth_rate === null ? '' : percent(s.worth_rate)}</span>
                </td>
                <td className="cw-num">{s.favorited}</td>
                <td className="cw-num cw-muted">{s.used_in_projects ?? '—'}</td>
                <td className="cw-num">{percent(s.duplicate_rate)}</td>
                <td className="cw-num">{s.first_reports}</td>
                <td className="cw-num">{s.cost ? `${s.cost.toFixed(2)} 元` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <SectionHead title="完整度" note="近 30 天各信源字段完整率；延迟 = 发布到采集的中位数" />
      <Card className="cw-scroll-x">
        <table className="cw-table">
          <thead>
            <tr>
              <th>信源</th>
              <th>条数</th>
              <th>封面</th>
              <th>发布时间</th>
              <th>作者</th>
              <th>平台指标</th>
              <th>正文</th>
              <th>延迟</th>
            </tr>
          </thead>
          <tbody>
            {data.completeness.map((r) => (
              <tr key={r.source_id}>
                <td>{r.name}</td>
                <td className="cw-num">{r.items}</td>
                <td className="cw-num">{percent(r.cover)}</td>
                <td className="cw-num">{percent(r.published_at)}</td>
                <td className="cw-num">{percent(r.author)}</td>
                <td className="cw-num">{percent(r.metrics)}</td>
                <td className="cw-num">{percent(r.body)}</td>
                <td className="cw-num">{r.delay_hours_median === null ? '—' : `${r.delay_hours_median} 小时`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}
