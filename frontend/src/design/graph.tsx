'use client';

/**
 * 灵感库图谱（6.7）：sigma.js + graphology（WebGL）。颜色表示类型，大小表示关联数。
 * 全局图谱用 ForceAtlas2 布局；局部图谱（详情里）以中心节点为圆心按一度 / 二度分圈。
 */

import { useEffect, useRef } from 'react';
import type { GraphData, GraphNode } from '@/lib/api/_library';
import { color, mediaColor } from './tokens';

export const NODE_COLOR: Record<string, string> = {
  article: mediaColor.article,
  post: mediaColor.article,
  video: mediaColor.video,
  image: mediaColor.image,
  prompt: mediaColor.prompt,
  repo: mediaColor.repo,
  link: color.dim,
  generated: color.mg,
  asset: color.wh,
  palette: color.wh,
  font: color.wh,
  icon: color.wh,
  texture: color.wh,
  motion: color.wh,
  audio: color.wh,
  note: color.yl,
  dossier: color.rd,
  style: color.gr,
  template: color.gr,
  project: color.cy,
};

export const NODE_TYPE_LABEL: Record<string, string> = {
  item: '收藏',
  note: '随笔',
  dossier: '专题',
  style: '风格',
  template: '模板',
  project: '项目',
};

export function nodeHref(n: GraphNode): string {
  const [type, id] = n.key.split(':');
  if (type === 'item') return `/library?open=${id}`;
  if (type === 'note') return `/notes?focus=${id}`;
  if (type === 'dossier') return `/dossiers/${id}`;
  if (type === 'style') return `/library/styles?style=${encodeURIComponent(n.ref || '')}`;
  if (type === 'template') return `/library/styles?template=${encodeURIComponent(n.ref || '')}`;
  return `/studio/${id}`;
}

/** 初始坐标：局部图谱按深度分圈，全局图谱按类型分扇区（之后交给 ForceAtlas2） */
export function initialPositions(data: GraphData): Record<string, { x: number; y: number }> {
  const out: Record<string, { x: number; y: number }> = {};
  const groups: Record<string, GraphNode[]> = {};
  for (const n of data.nodes) {
    const g = data.center ? String(n.depth ?? 0) : n.type;
    (groups[g] ||= []).push(n);
  }
  const keys = Object.keys(groups).sort();
  keys.forEach((g, gi) => {
    const list = groups[g];
    list.forEach((n, i) => {
      if (data.center && n.key === data.center) {
        out[n.key] = { x: 0, y: 0 };
        return;
      }
      const ring = data.center ? Number(g) : 1 + (i % 5) * 0.4;
      const angle = data.center ? (2 * Math.PI * i) / list.length : (2 * Math.PI * (gi + i / Math.max(list.length, 1))) / keys.length;
      out[n.key] = { x: Math.cos(angle) * ring * 10, y: Math.sin(angle) * ring * 10 };
    });
  });
  return out;
}

export function LibraryGraph({
  data,
  height = 560,
  onSelect,
  selected,
}: {
  data: GraphData;
  height?: number;
  onSelect?: (node: GraphNode | null) => void;
  selected?: string | null;
}) {
  const box = useRef<HTMLDivElement>(null);
  const onSelectRef = useRef(onSelect);
  const selectedRef = useRef(selected);
  // 渲染期间不写 ref（React 19 规则）：提交后同步给 sigma 回调读取
  useEffect(() => {
    onSelectRef.current = onSelect;
    selectedRef.current = selected;
  });
  const refresh = useRef<(() => void) | null>(null);

  useEffect(() => {
    let killed = false;
    let renderer: { kill: () => void; refresh: () => void } | null = null;
    (async () => {
      const [{ default: Graph }, { default: Sigma }, fa2] = await Promise.all([
        import('graphology'),
        import('sigma'),
        import('graphology-layout-forceatlas2'),
      ]);
      if (killed || !box.current) return;
      const graph = new Graph({ multi: false, type: 'undirected' });
      const pos = initialPositions(data);
      const byKey = new Map(data.nodes.map((n) => [n.key, n]));
      for (const n of data.nodes) {
        graph.addNode(n.key, {
          label: n.label,
          x: pos[n.key]?.x ?? Math.random(),
          y: pos[n.key]?.y ?? Math.random(),
          size: Math.min(18, 3 + Math.sqrt(n.degree) * 3) + (n.key === data.center ? 4 : 0),
          color: NODE_COLOR[n.kind] || color.dim,
        });
      }
      for (const e of data.edges) {
        if (graph.hasNode(e.source) && graph.hasNode(e.target) && !graph.hasEdge(e.source, e.target)) {
          graph.addEdge(e.source, e.target, { size: e.relation.startsWith('same_') ? 0.6 : 1.2, color: e.relation.startsWith('same_') ? color.grat : color.line });
        }
      }
      if (!data.center && graph.order > 1) {
        fa2.default.assign(graph, { iterations: Math.min(400, 80 + graph.order), settings: { ...fa2.default.inferSettings(graph), gravity: 1.2, barnesHutOptimize: graph.order > 300 } });
      }
      renderer = new Sigma(graph, box.current, {
        labelColor: { color: color.text },
        labelSize: 12,
        labelRenderedSizeThreshold: data.center ? 0 : 8,
        defaultEdgeColor: color.line,
        nodeReducer: (key, attrs) => (selectedRef.current && key === selectedRef.current ? { ...attrs, highlighted: true, forceLabel: true } : attrs),
      }) as unknown as { kill: () => void; refresh: () => void };
      const r = renderer as unknown as { on: (ev: string, fn: (p: { node?: string }) => void) => void };
      r.on('clickNode', ({ node }) => onSelectRef.current?.((node && byKey.get(node)) || null));
      r.on('clickStage', () => onSelectRef.current?.(null));
      refresh.current = () => renderer?.refresh();
    })();
    return () => {
      killed = true;
      renderer?.kill();
      refresh.current = null;
    };
  }, [data]);

  useEffect(() => {
    refresh.current?.();
  }, [selected]);

  return <div ref={box} className="cw-graph" style={{ height }} role="img" aria-label={`关联图谱：${data.nodes.length} 个节点，${data.edges.length} 条关联`} />;
}
