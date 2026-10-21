'use client';

/** 热度相位图：每个话题一个点（大小 = 条数，颜色 = 状态），四个象限即「新出现 / 升温 / 降温 / 持续」，点象限筛选。 */

import { useState, type CSSProperties } from 'react';
import type { TopicStatus } from '@/lib/api/_discover';
import { STATUS_COLOR, STATUS_LABEL } from '@/lib/discover';
import { BAND, DAY_X, OVER_W, PAD_X, ZERO_Y, ageX as ageNorm, phasePoints, plotX, type PhaseInput } from '@/lib/phase';
import { useReducedMotion } from './instrument';

type Row = PhaseInput & { title: string; status: TopicStatus };

const W = 1000;
const H = 260;
const STATUSES: TopicStatus[] = ['new', 'rising', 'steady', 'peak', 'cooling'];
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
  const ageX = (hours: number) => plotX(ageNorm(hours)) * W;
  return (
    <div className="cw-phase">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="话题热度相位图">
        <rect className="cw-phase-band" x="0" y="0" width={W} height={BAND * H} />
        <text className="cw-phase-bandlab" x="8" y={BAND * H - 8}>首次观测</text>
        <rect className="cw-phase-q" data-hot="true" x={DAY_X * W} y={BAND * H} width={(1 - PAD_X - OVER_W - DAY_X) * W} height={ZERO_Y * H - BAND * H} />
        <line className="cw-phase-axis" x1="0" x2={W} y1={ZERO_Y * H} y2={ZERO_Y * H} />
        {!pts.some((p) => !p.first && (p.change ?? 0) < 0) ? (
          <text className="cw-phase-bandlab" x={DAY_X * W + 8} y={ZERO_Y * H + 18}>
            暂无降温
          </text>
        ) : null}
        <line className="cw-phase-axis" x1={DAY_X * W} x2={DAY_X * W} y1={BAND * H} y2={H} />
        <rect className="cw-phase-over" x={(1 - PAD_X - OVER_W) * W} y={BAND * H} width={(OVER_W + PAD_X / 2) * W} height={H - BAND * H} />
        {TICKS.map((t) => (
          <line key={t.h} className="cw-phase-tick" x1={ageX(t.h)} x2={ageX(t.h)} y1={BAND * H} y2={H} />
        ))}
        {pts.map((p, i) => {
          const row = byId.get(p.id)!;
          const dim = active && row.status !== active;
          return (
            <circle
              key={p.id}
              className="cw-phase-pt"
              data-dim={dim ? 'true' : undefined}
              data-first={p.first ? 'true' : undefined}
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
      <div className="cw-phase-legend" role="group" aria-label="按状态筛选">
        {STATUSES.map((st) => (
          <button
            key={st}
            type="button"
            className="cw-phase-label"
            aria-pressed={active === st}
            style={{ '--c': STATUS_COLOR[st] } as CSSProperties}
            onClick={() => onPick(active === st ? '' : st)}
          >
            <i />
            {STATUS_LABEL[st]}
            <small className="cw-num">{rows.filter((r) => r.status === st).length}</small>
          </button>
        ))}
      </div>
      <div className="cw-phase-x cw-num" aria-hidden>
        {TICKS.map((t) => (
          <span key={t.h} style={{ left: `${(ageX(t.h) / W) * 100}%` }}>
            {t.l}
          </span>
        ))}
        <span style={{ left: `${(1 - PAD_X / 2 - OVER_W / 2) * 100}%` }}>&gt;7 天</span>
      </div>
      <span className="cw-phase-ylab" aria-hidden style={{ left: `calc(${DAY_X * 100}% + 8px)`, top: ZERO_Y * 260 - 20 }}>
        ↑ 热度在涨
      </span>
      {h && hp ? (
        <div className="cw-tip cw-phase-tip" style={{ left: `${hp.x * 100}%`, top: `${(hp.y * H * 100) / H}%`, position: 'absolute' }}>
          {h.title}
          <small>
            {STATUS_LABEL[h.status]} · {h.content_count} 条 · {hp.change === null ? '首次观测' : `${hp.change >= 0 ? '+' : ''}${Math.round(hp.change * 100)}%`}
          </small>
        </div>
      ) : null}
    </div>
  );
}
