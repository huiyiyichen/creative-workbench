'use client';

/** 溯源抽屉（创作工作台设计 7.2）：向上展开来源链直到采集内容 / 灵感库条目；向下列出被哪些产物使用；
 *  采集内容可以继续展开它的「经历」。 */

import Link from 'next/link';
import { Drawer, Spin } from 'antd';
import { useEffect, useState } from 'react';
import { color } from './tokens';
import { request } from '@/lib/api/_core';
import { runsApi, type LineageNode, type LineageQuery, type LineageView } from '@/lib/api/_runs';
import { JOURNEY_LABEL } from '@/lib/discover';

export const ARTIFACT_KIND_LABEL: Record<string, string> = {
  research_brief: '研究简报',
  direction_cards: '方向卡',
  draft: '文稿稿件',
  review: '审校意见',
  draft_version: '文稿版本',
  storyboard: '分镜',
  keyframes: '关键帧',
  video: '成片',
  qa_report: '质检报告',
  platform_xhs: '小红书版',
  platform_zhihu: '知乎版',
  platform_wechat: '公众号版',
  platform_bilibili: 'B站版',
  platform_douyin: '抖音版',
};

const RELATION_LABEL: Record<string, string> = {
  cites: '引用',
  derived_from: '来自',
  reviews: '审校',
  uses: '使用',
  fixes: '修正',
  generated: '参考生成',
};

const TYPE_COLOR: Record<string, string> = { artifact: color.cy, content: color.yl, library: color.mg, url: color.bl };

/** 锚点的可读名称：p_xxxx → 段落，shot_3 → 第 3 镜 */
export function anchorLabel(anchor: string | null | undefined): string | null {
  if (!anchor) return null;
  const m = /^shot_(\d+)$/.exec(anchor);
  if (m) return `第 ${m[1]} 镜`;
  if (anchor.startsWith('p_')) return '段落';
  if (/^d\d+$/.test(anchor)) return `方向 ${anchor.slice(1)}`;
  if (/^f\d+$/.test(anchor)) return `结论 ${anchor.slice(1)}`;
  if (/^[rq]\d+$/.test(anchor)) return `意见 ${anchor.slice(1)}`;
  return anchor;
}

export function countLeaves(nodes: LineageNode[]): { content: number; library: number; url: number } {
  const out = { content: 0, library: 0, url: 0 };
  const seen = new Set<string>();
  const walk = (ns: LineageNode[]) => {
    for (const n of ns) {
      const key = `${n.type}:${n.id ?? n.url}`;
      if (n.type !== 'artifact' && !seen.has(key)) {
        seen.add(key);
        if (n.type in out) out[n.type as keyof typeof out] += 1;
      }
      if (n.sources) walk(n.sources);
    }
  };
  walk(nodes);
  return out;
}

function Journey({ contentId }: { contentId: number }) {
  const [items, setItems] = useState<{ id: number; stage: string; summary: string | null; at: string }[] | null>(null);
  useEffect(() => {
    request<{ items: { id: number; stage: string; summary: string | null; at: string }[] }>(`/contents/${contentId}/journey`)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [contentId]);
  if (items === null) return <Spin size="small" />;
  if (!items.length) return <small className="cw-muted">没有经历记录</small>;
  return (
    <ol className="cw-lin-journey">
      {items.map((j) => (
        <li key={j.id}>
          <b>{JOURNEY_LABEL[j.stage] || j.stage}</b> {j.summary ? <span className="cw-muted">{j.summary}</span> : null}
        </li>
      ))}
    </ol>
  );
}

function NodeRow({ node }: { node: LineageNode }) {
  const [journey, setJourney] = useState(false);
  const typeLabel =
    node.type === 'artifact'
      ? ARTIFACT_KIND_LABEL[node.kind || ''] || node.kind || '产物'
      : node.type === 'content'
        ? `采集内容${node.platform ? ` · ${node.platform}` : ''}`
        : node.type === 'library'
          ? '灵感库'
          : '网页';
  const title = node.title || node.url || `#${node.id}`;
  const href =
    node.type === 'content' && node.id
      ? `/items/${node.id}`
      : node.type === 'library' && node.id
        ? `/library?open=${node.id}`
        : node.type === 'artifact' && node.run_id
          ? `/runs/${node.run_id}`
          : node.url || null;
  const anc = anchorLabel(node.target_anchor);
  return (
    <li className="cw-lin-node">
      <div className="cw-lin-head">
        <span className="cw-lin-dot" style={{ background: TYPE_COLOR[node.type] || color.dim }} />
        <small className="cw-muted">{RELATION_LABEL[node.relation] || node.relation}</small>
        <b>{typeLabel}</b>
        {node.version && node.type === 'artifact' ? <small className="cw-num">v{node.version}</small> : null}
        {anc ? <small className="cw-lin-anchor">{anc}</small> : null}
        {href ? (
          href.startsWith('http') ? (
            <a href={href} target="_blank" rel="noreferrer" className="cw-lin-title">
              {title}
            </a>
          ) : (
            <Link href={href} className="cw-lin-title">
              {title}
            </Link>
          )
        ) : (
          <span className="cw-lin-title">{title}</span>
        )}
        {node.type === 'content' && node.id ? (
          <button type="button" className="cw-link-btn" onClick={() => setJourney(!journey)}>
            {journey ? '收起经历' : '经历'}
          </button>
        ) : null}
      </div>
      {journey && node.id ? <Journey contentId={node.id} /> : null}
      {node.sources?.length ? (
        <ul className="cw-lin-tree">
          {node.sources.map((s, i) => (
            <NodeRow key={`${s.type}-${s.id ?? s.url}-${i}`} node={s} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function LineageDrawer({
  query,
  artifactId,
  anchor,
  title,
  onClose,
}: {
  query?: LineageQuery | null;
  artifactId?: number | null;
  anchor?: string;
  title?: string;
  onClose: () => void;
}) {
  const open = Boolean(query || artifactId);
  const [data, setData] = useState<LineageView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = JSON.stringify(query || { artifactId, anchor });
  useEffect(() => {
    if (!open) return;
    setData(null);
    setError(null);
    const p = query ? runsApi.resolveLineage(query) : runsApi.lineage(artifactId as number, anchor);
    p.then(setData).catch((err) => setError(err instanceof Error ? err.message : '溯源加载失败'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, open]);
  const leaves = data ? countLeaves(data.sources) : null;
  return (
    <Drawer open={open} onClose={onClose} size={520} title={title || '溯源'} className="cw-drawer" destroyOnHidden>
      {error ? <div className="cw-error">{error}</div> : null}
      {!data && !error ? <Spin /> : null}
      {data ? (
        <div className="cw-lineage">
          <header>
            <b>{ARTIFACT_KIND_LABEL[data.artifact.kind] || data.artifact.kind}</b>
            <span className="cw-num">v{data.artifact.version}</span>
            <span>{data.artifact.title}</span>
            {data.anchor ? <small className="cw-lin-anchor">{anchorLabel(data.anchor)}</small> : null}
          </header>
          {leaves ? (
            <p className="cw-muted" style={{ fontSize: 12 }}>
              追到 {leaves.content} 条采集内容、{leaves.library} 个灵感库条目、{leaves.url} 个网页
            </p>
          ) : null}
          <h4>来源</h4>
          {data.sources.length ? (
            <ul className="cw-lin-tree" data-root>
              {data.sources.map((s, i) => (
                <NodeRow key={`${s.type}-${s.id ?? s.url}-${i}`} node={s} />
              ))}
            </ul>
          ) : (
            <p className="cw-empty">{data.anchor ? '这一处没有登记来源' : '没有登记来源'}</p>
          )}
          <h4>被这些产物使用</h4>
          {data.used_by.length ? (
            <ul className="cw-lin-used">
              {data.used_by.map((u) => (
                <li key={u.id}>
                  <b>{ARTIFACT_KIND_LABEL[u.kind] || u.kind}</b> <span className="cw-num">v{u.version}</span> {u.title}
                </li>
              ))}
            </ul>
          ) : (
            <p className="cw-empty">还没有被使用</p>
          )}
        </div>
      ) : null}
    </Drawer>
  );
}
