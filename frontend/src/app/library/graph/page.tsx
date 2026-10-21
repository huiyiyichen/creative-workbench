'use client';

/** 图谱（6.7）：全部收藏、随笔、专题、风格 / 模板和它们之间的关联；点节点看详情、打开或「用于新项目」。 */

import { ScanSkeleton } from '@/design/instrument';
import Link from 'next/link';
import { message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { Card, CwPage, Segmented, TopBar } from '@/design/components';
import { LibraryGraph, NODE_COLOR, NODE_TYPE_LABEL, nodeHref } from '@/design/graph';
import { libraryApi, type GraphData, type GraphNode } from '@/lib/api/_library';

const TYPES = ['item', 'note', 'dossier', 'style', 'template', 'project'] as const;
const RANGE = [
  { value: '0', label: '全部' },
  { value: '7', label: '7 天' },
  { value: '30', label: '30 天' },
  { value: '90', label: '90 天' },
] as const;
type Range = (typeof RANGE)[number]['value'];

const RELATION_LABEL: Record<string, string> = {
  extracted: '提取',
  distilled: '提炼',
  generated: '生成',
  wikilink: '双链',
  manual: '手动',
  same_event: '同一事件',
  same_tag: '同标签',
  same_words: '标题相近',
  same_author: '同作者',
  similar: '相似',
  used_in_project: '用于项目',
};

export default function GraphPage() {
  const [types, setTypes] = useState<Set<string>>(new Set(TYPES));
  const [range, setRange] = useState<Range>('0');
  const [data, setData] = useState<GraphData | null>(null);
  const [picked, setPicked] = useState<GraphNode | null>(null);

  useEffect(() => {
    setData(null);
    libraryApi
      .graph({ types: [...types], days: range === '0' ? undefined : Number(range) })
      .then(setData)
      .catch((err) => {
        message.error(err instanceof Error ? err.message : '请求失败');
        setData({ nodes: [], edges: [], center: null });
      });
  }, [types, range]);

  const neighbors = useMemo(() => {
    if (!picked || !data) return [];
    const byKey = new Map(data.nodes.map((n) => [n.key, n]));
    return data.edges
      .filter((e) => e.source === picked.key || e.target === picked.key)
      .map((e) => ({ node: byKey.get(e.source === picked.key ? e.target : e.source), relation: e.relation }))
      .filter((x): x is { node: GraphNode; relation: string } => Boolean(x.node));
  }, [picked, data]);

  const toggle = (t: string) =>
    setTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next.size ? next : prev;
    });

  const [ptype, pid] = picked ? picked.key.split(':') : ['', ''];

  return (
    <CwPage>
      <TopBar title="图谱" sub={data ? `${data.nodes.length} 个节点 · ${data.edges.length} 条关联` : '加载中…'}>
        <nav className="cw-seg" aria-label="灵感库分页">
          <Link href="/library">收藏</Link>
          <Link href="/notes">随笔</Link>
          <Link href="/library/styles">风格与模板</Link>
          <Link href="/library/graph" aria-current="page">
            图谱
          </Link>
        </nav>
      </TopBar>
      <div className="cw-filters">
        <div className="cw-seg" role="group" aria-label="节点类型">
          {TYPES.map((t) => (
            <button key={t} type="button" aria-pressed={types.has(t)} onClick={() => toggle(t)}>
              <i className="cw-dot" style={{ background: NODE_COLOR[t === 'item' ? 'image' : t] }} aria-hidden /> {NODE_TYPE_LABEL[t]}
            </button>
          ))}
        </div>
        <Segmented<Range> label="时间" value={range} onChange={setRange} options={RANGE.map((r) => ({ value: r.value, label: r.label }))} />
      </div>
      <div className="cw-lib-layout">
        <section>
          {data && data.nodes.length === 0 ? (
            <div className="cw-empty">还没有可画的关联。收藏几条内容、写几条带 [[双链]] 的随笔就会出现</div>
          ) : data ? (
            <LibraryGraph data={data} height={640} onSelect={setPicked} selected={picked?.key} />
          ) : (
            <ScanSkeleton height={160} />
          )}
        </section>
        <aside className="cw-today-side">
          <Card title={picked ? picked.label || '（无标题）' : '节点'}>
            {picked ? (
              <>
                <p className="cw-muted">
                  {NODE_TYPE_LABEL[picked.type]} · {picked.degree} 条关联
                </p>
                <div className="cw-row" style={{ marginBottom: 10 }}>
                  <Link className="cw-btn" href={nodeHref(picked)}>
                    打开
                  </Link>
                  {ptype === 'item' ? (
                    <Link className="cw-btn" data-variant="primary" href={`/projects/new?source=library:${pid}`}>
                      用于新项目
                    </Link>
                  ) : ptype === 'note' ? (
                    <Link className="cw-btn" data-variant="primary" href={`/projects/new?source=note:${pid}`}>
                      用于新项目
                    </Link>
                  ) : null}
                </div>
                <ul className="cw-report-list">
                  {neighbors.slice(0, 20).map(({ node, relation }) => (
                    <li key={node.key}>
                      <button type="button" className="cw-link-btn" onClick={() => setPicked(node)}>
                        {node.label || '（无标题）'}
                      </button>
                      <span className="cw-grow" />
                      <span className="cw-muted">{RELATION_LABEL[relation] || relation}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="cw-muted">点一个节点看它的关联。颜色表示类型，越大关联越多；滚轮缩放，拖动平移。</p>
            )}
          </Card>
        </aside>
      </div>
    </CwPage>
  );
}
