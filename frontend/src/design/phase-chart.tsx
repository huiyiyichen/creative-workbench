'use client';

/** 热度相位图：每个话题一个点（大小 = 条数，颜色 = 状态），四个象限即「新出现 / 升温 / 降温 / 持续」，点象限筛选。 */

import { useState, type CSSProperties } from 'react';
import type { TopicStatus } from '@/lib/api/_discover';
import { STATUS_COLOR, STATUS_LABEL } from '@/lib/discover';
import { DAY_X, ZERO_Y, phasePoints, type PhaseInput } from '@/lib/phase';
import { useReducedMotion } from './instrument';

type Row = PhaseInput & { title: string; status: TopicStatus };

const W = 1000;
const H = 260;
const QUADS: { status: TopicStatus; label: string; x: number; y: number; anchor: 'start' | 'end' }[] = [
  { status: 'new', label: '新出现', x: 12, y: 22, anchor: 'start' },
  { status: 'rising', label: '升温', x: W - 12, y: 22, anchor: 'end' },
  { status: 'cooling', label: '降温', x: W - 12, y: H - 12, anchor: 'end' },
  { status: 'steady', label: '持续', x: 12, y: H - 12, anchor: 'start' },
];
const TICKS = [
  { h: 1, l: '1 小时' },
  { h: 6, l: '6 小时' },
  { h: 24, l: '1 天' },
  { h: 72, l: '3 天' },
  { h: 168, l: '7 天' },
];

export function PhaseChart({
  rows,
  now,
  active,
  onPick,
  onOpen,
}: {
  rows: Row[];
  now: number;
  active: TopicStatus | '';
  onPick: (s: TopicStatus | '') => void;
  onOpen: (id: number) => void;
}) {
  const reduce = useReducedMotion();
  const pts = phasePoints(rows, now);
  const byId = new Map(rows.map((r) => [r.id, r]));
  const [hover, setHover] = useState<number | null>(null);
  const h = hover !== null ? byId.get(hover) : null;
  const hp = hover !== null ? pts.find((p) => p.id === hover) : null;
  const ageX = (hours: number) => (Math.log1p(hours) / Math.log1p(168)) * W;
  return (
    <div className="cw-phase">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="话题热度相位图">
        <rect className="cw-phase-q" data-on={active === 'new' || active === '' ? 'true' : undefined} x="0" y="0" width={DAY_X * W} height={ZERO_Y * H} />
        <rect className="cw-phase-q" data-hot="true" x={DAY_X * W} y="0" width={(1 - DAY_X) * W} height={ZERO_Y * H} />
        <line className="cw-phase-axis" x1="0" x2={W} y1={ZERO_Y * H} y2={ZERO_Y * H} />
        <line className="cw-phase-axis" x1={DAY_X * W} x2={DAY_X * W} y1="0" y2={H} />
        {TICKS.map((t) => (
          <line key={t.h} className="cw-phase-tick" x1={ageX(t.h)} x2={ageX(t.h)} y1="0" y2={H} />
        ))}
        {pts.map((p, i) => {
          const row = byId.get(p.id)!;
          const dim = active && row.status !== active;
          return (
            <circle
              key={p.id}
              className="cw-phase-pt"
              data-dim={dim ? 'true' : undefined}
              data-hover={hover === p.id ? 'true' : undefined}
              cx={p.x * W}
              cy={p.y * H}
              r={p.r}
              style={{ '--c': STATUS_COLOR[row.status] || 'var(--cw-dim)', animationDelay: reduce ? undefined : `${Math.min(i, 30) * 20}ms` } as CSSProperties}
              onPointerEnter={() => setHover(p.id)}
              onPointerLeave={() => setHover(null)}
              onClick={() => onOpen(p.id)}
            />
          );
        })}
      </svg>
      {QUADS.map((q) => (
        <button
          key={q.status}
          type="button"
          className="cw-phase-label"
          aria-pressed={active === q.status}
          style={{ [q.x > W / 2 ? 'right' : 'left']: 12, [q.y > H / 2 ? 'bottom' : 'top']: 10, '--c': STATUS_COLOR[q.status] } as CSSProperties}
          onClick={() => onPick(active === q.status ? '' : q.status)}
        >
          <i />
          {q.label}
          <small className="cw-num">{rows.filter((r) => r.status === q.status).length}</small>
        </button>
      ))}
      <div className="cw-phase-x cw-num" aria-hidden>
        {TICKS.map((t) => (
          <span key={t.h} style={{ left: `${(ageX(t.h) / W) * 100}%` }}>
            {t.l}
          </span>
        ))}
      </div>
      <span className="cw-phase-ylab" aria-hidden>
        ↑ 热度在涨
      </span>
      {h && hp ? (
        <div className="cw-tip cw-phase-tip" style={{ left: `${hp.x * 100}%`, top: `${(hp.y * H * 100) / H}%`, position: 'absolute' }}>
          {h.title}
          <small>
            {STATUS_LABEL[h.status]} · {h.content_count} 条 · {hp.change >= 0 ? '+' : ''}
            {Math.round(hp.change * 100)}%
          </small>
        </div>
      ) : null}
    </div>
  );
}
