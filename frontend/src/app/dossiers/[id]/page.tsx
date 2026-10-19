'use client';

/** 专题页（5.5）：时间线、热度曲线、各平台首次出现、提到它的报告、相关收藏、状态与结论。 */

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { message } from 'antd';
import { ArrowLeft, Star } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, CwPage, TopBar } from '@/design/components';
import { FeedItem, GapSpark, ItemDrawer, StatusTag, VerdictMark, platformName } from '@/design/discover';
import { color } from '@/design/tokens';
import { discoverApi, type DossierDetail } from '@/lib/api/_discover';
import { relativeTime } from '@/lib/collection';

const REPORT_HREF: Record<string, (r: { id: number; date: string }) => string> = {
  daily: (r) => `/daily?date=${r.date}`,
  weekly: () => '/weekly',
  monthly: () => '/monthly',
  gap: (r) => `/reports/periods/${r.id}`,
  range: (r) => `/reports/periods/${r.id}`,
};

export default function DossierPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [data, setData] = useState<DossierDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  const load = useCallback(() => {
    discoverApi
      .dossier(id)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : '请求失败'));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = async () => {
    if (!data) return;
    try {
      await discoverApi.setFollowed(id, !data.followed);
      load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '请求失败');
    }
  };

  if (error) return <CwPage><div className="cw-error">{error}</div></CwPage>;
  if (!data) return <CwPage><div className="cw-empty">加载中…</div></CwPage>;

  const timeline = [...data.timeline].reverse();
  return (
    <CwPage>
      <Link href="/dossiers" className="cw-btn" data-variant="ghost">
        <ArrowLeft size={15} />
        专题
      </Link>
      <TopBar title={data.title} sub={data.archived_at ? '已归档' : data.first_seen_at ? `首次出现 ${relativeTime(data.first_seen_at)}` : undefined}>
        <StatusTag status={data.status} />
        {data.verdict ? <VerdictMark verdict={data.verdict.verdict} /> : null}
        <Button icon={<Star size={15} />} variant={data.followed ? 'primary' : 'default'} onClick={toggle}>
          {data.followed ? '已关注' : '关注'}
        </Button>
      </TopBar>
      {data.verdict ? <p className="cw-muted" style={{ marginTop: -8 }}>{data.verdict.reason}</p> : null}

      <div className="cw-today">
        <section>
          <Card title="热度曲线" extra={<small className="cw-muted">{data.trend_computed_at ? `每小时计算 · ${relativeTime(data.trend_computed_at)}` : '观测不足'}</small>}>
            <GapSpark values={data.series} width={760} height={80} accent={color.rd} label={`${data.title} 逐小时信号`} />
            <div className="cw-firsts" style={{ marginTop: 10 }}>
              <span>各平台首次出现：</span>
              {data.first_by_platform.map((f, i) => (
                <span key={f.platform}>
                  {i + 1}. <b>{platformName(f.platform)}</b> <span className="cw-num">{new Date(f.at).toLocaleString('zh-CN', { hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                </span>
              ))}
            </div>
          </Card>
          <div className="cw-feed-head">
            <h2>时间线</h2>
            <span className="cw-muted">{data.timeline.length} 条，按发布时间</span>
          </div>
          {timeline.length === 0 ? (
            <div className="cw-empty">还没有相关内容</div>
          ) : (
            <ul className="cw-feed cw-dtl">
              {timeline.map((item) => (
                <FeedItem key={item.id} item={item} onOpen={setOpenId} selected={item.id === openId} />
              ))}
            </ul>
          )}
        </section>
        <aside className="cw-today-side">
          <Card title="提到它的报告">
            {data.reports.length === 0 ? (
              <div className="cw-muted">还没有报告提到它</div>
            ) : (
              <ul className="cw-report-list">
                {data.reports.map((r) => (
                  <li key={`${r.kind}-${r.id}`}>
                    <Link href={(REPORT_HREF[r.kind] || REPORT_HREF.gap)(r)}>{r.label}</Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="相关收藏">
            {data.favorites.length === 0 ? (
              <div className="cw-muted">没有收藏</div>
            ) : (
              <ul className="cw-report-list">
                {data.favorites.map((f) => (
                  <li key={f.id}>
                    <button type="button" className="cw-link-btn" onClick={() => setOpenId(f.id)}>
                      {f.title}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="随笔与项目">
            <div className="cw-muted">随笔在阶段 3、项目关联在阶段 4 接入</div>
          </Card>
        </aside>
      </div>
      <ItemDrawer id={openId} onClose={() => setOpenId(null)} />
    </CwPage>
  );
}
