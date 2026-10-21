'use client';

/** 月刊里的「本月创作人格」：只按本月真实动作统计；可导出竖版分享图（带投票口令）。 */

import { Input } from 'antd';
import { Copy, Download } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/design/components';
import { toast } from '@/design/feedback';
import { ScanSkeleton } from '@/design/instrument';
import { monthlyDigestApi, type CreatorPersona } from '@/lib/api/_digests';
import { buildPersonaSvg, downloadPng, monthLabel, shareText, svgDataUrl } from '@/lib/persona-card';

const VOTE_KEY = 'cw.persona.vote';

export function PersonaPanel({ month }: { month?: string }) {
  const [data, setData] = useState<CreatorPersona | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [vote, setVote] = useState('');
  useEffect(() => {
    setVote(window.localStorage.getItem(VOTE_KEY) || '');
  }, []);
  useEffect(() => {
    setData(null);
    setError(null);
    monthlyDigestApi
      .persona(month)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : '创作人格没算出来'));
  }, [month]);
  const svg = useMemo(() => (data ? buildPersonaSvg(data, { vote: vote.trim() || undefined }) : ''), [data, vote]);
  if (error) return <p className="cw-error">{error}</p>;
  if (!data) return <ScanSkeleton height={260} label="统计本月创作动作" />;
  const s = data.stats;
  const saveVote = (v: string) => {
    setVote(v);
    window.localStorage.setItem(VOTE_KEY, v);
  };
  return (
    <section className="cw-persona" aria-label="本月创作人格">
      <div className="cw-persona-card">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={svgDataUrl(svg)} alt={`${monthLabel(data.month)}创作人格：${data.archetype.name}`} />
      </div>
      <div className="cw-persona-side">
        <small className="cw-muted">{monthLabel(data.month)} · 创作人格</small>
        <h2 className="cw-persona-name">{data.archetype.name}</h2>
        <p className="cw-persona-tag">{data.archetype.tagline}</p>
        <dl className="cw-persona-stats">
          <div>
            <dt>动作</dt>
            <dd className="cw-num">{s.actions}</dd>
          </div>
          <div>
            <dt>文稿版本</dt>
            <dd className="cw-num">{s.revisions}</dd>
          </div>
          <div>
            <dt>已发布</dt>
            <dd className="cw-num">{s.published}</dd>
          </div>
          <div>
            <dt>夜里占比</dt>
            <dd className="cw-num">{s.night_pct}%</dd>
          </div>
        </dl>
        <label className="cw-field">
          <span>投票口令（印在分享图底部，比如「B站搜 创意工作台 投一票」）</span>
          <Input value={vote} maxLength={40} onChange={(e) => saveVote(e.target.value)} placeholder="不填就不印" />
        </label>
        <div className="cw-row">
          <Button
            variant="primary"
            icon={<Download size={14} />}
            onClick={async () => {
              try {
                await downloadPng(svg, `创作人格-${data.month}.png`);
              } catch (err) {
                toast.error(err, '导出失败');
              }
            }}
          >
            下载分享图
          </Button>
          <Button
            icon={<Copy size={14} />}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(shareText(data, vote.trim() || undefined));
                toast.success('已复制配图文案');
              } catch {
                toast.error('浏览器不允许访问剪贴板');
              }
            }}
          >
            复制文案
          </Button>
        </div>
        {s.actions < 5 ? <p className="cw-muted">这个月动作还少，人格会随着你多做几件事变化。</p> : null}
      </div>
    </section>
  );
}
