'use client';

/**
 * 全站共用的「仪器」组件（设计评审 #1 · 1.3）。每块面板都是一台仪器：刻度 + 信号 + 读数 + 一行标注。
 * 颜色只表示内容形态；亮度表示强弱；发光只给「活的东西」（现在、运行中、选中、最新值、异常）。
 */

import Link from 'next/link';
import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from 'react';

// ── 减少动态 ──

function subscribeRM(cb: () => void) {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {};
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
  mq.addEventListener('change', cb);
  return () => mq.removeEventListener('change', cb);
}

/** 用户要求减少动态时为 true：JS 动画（扫描、计数、依次点亮）直接给终态。 */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeRM,
    () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)').matches : false),
    () => false,
  );
}

/** 数字从 0 计到目标（600ms easeOutCubic，只在首次出现时）。 */
export function useCountUp(target: number | null | undefined, ms = 600): number | null {
  const reduce = useReducedMotion();
  const [v, setV] = useState<number | null>(null);
  const done = useRef(false);
  useEffect(() => {
    if (target === null || target === undefined) return;
    if (reduce || done.current || target === 0) {
      setV(target);
      return;
    }
    done.current = true;
    const start = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / ms);
      setV(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms, reduce]);
  return target === null || target === undefined ? null : v ?? 0;
}

// ── 状态灯 ──

export type LampTone = 'ok' | 'warn' | 'bad' | 'run' | 'off';

/** 圆形发光灯：正常 绿 / 警告 黄 / 失败 红 / 运行 青（脉冲）/ 待机 灰（不发光）。 */
export function StatusLamp({ tone, label, href, title }: { tone: LampTone; label?: ReactNode; href?: string; title?: string }) {
  const body = (
    <>
      <i className="cw-lamp-dot" aria-hidden />
      {label ? <span>{label}</span> : null}
    </>
  );
  return href ? (
    <Link className="cw-lamp" data-tone={tone} href={href} title={title}>
      {body}
    </Link>
  ) : (
    <span className="cw-lamp" data-tone={tone} title={title} role={label ? undefined : 'img'} aria-label={label ? undefined : title}>
      {body}
    </span>
  );
}

// ── 面板 ──

/** 仪器面板：标题 + 图例槽 + 右侧控件；grid 变体叠加刻度网格（图谱、空态、大图表）。 */
export function Instrument({
  title,
  legend,
  extra,
  grid,
  children,
  className = '',
  label,
}: {
  title?: ReactNode;
  legend?: ReactNode;
  extra?: ReactNode;
  grid?: boolean;
  children: ReactNode;
  className?: string;
  label?: string;
}) {
  return (
    <section className={`cw-instrument ${className}`} data-grid={grid ? 'true' : undefined} aria-label={label}>
      {title || legend || extra ? (
        <header className="cw-instrument-head">
          {title ? <h2>{title}</h2> : null}
          {legend}
          <span className="cw-grow" />
          {extra}
        </header>
      ) : null}
      {children}
    </section>
  );
}

/** 读数格：标签 → 大数字 → 增量 / 说明 → 可选迷你曲线。多个并排时用 Readouts 包起来。 */
export function Readout({
  label,
  value,
  unit,
  sub,
  tone,
  count,
  children,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  sub?: ReactNode;
  /** good 绿 / bad 红 / warn 黄（不要用 up/down 表示好坏：花费涨是坏事，播放涨是好事） */
  tone?: 'good' | 'bad' | 'warn' | 'up' | 'down';
  count?: number | null;
  children?: ReactNode;
}) {
  const n = useCountUp(count);
  const shown = count !== undefined && count !== null && n !== null ? Math.round(n).toLocaleString('zh-CN') : value;
  return (
    <div className="cw-readout">
      <span>{label}</span>
      <b className="cw-num">
        {shown}
        {unit ? <em> {unit}</em> : null}
      </b>
      {sub ? <small data-tone={tone}>{sub}</small> : null}
      {children}
    </div>
  );
}

export function Readouts({ children }: { children: ReactNode }) {
  return <div className="cw-readouts">{children}</div>;
}

// ── 空状态 / 加载 ──

export type EmptyKind = 'flat' | 'dark' | 'unplugged';

function EmptyArt({ kind }: { kind: EmptyKind }) {
  if (kind === 'dark') {
    return (
      <svg viewBox="0 0 160 64" className="cw-empty-art" aria-hidden>
        {Array.from({ length: 24 }, (_, i) => (
          <circle key={i} cx={8 + (i % 12) * 13} cy={i < 12 ? 22 : 42} r="3.2" />
        ))}
      </svg>
    );
  }
  if (kind === 'unplugged') {
    return (
      <svg viewBox="0 0 160 64" className="cw-empty-art" data-kind="unplugged" aria-hidden>
        <rect x="18" y="20" width="34" height="24" rx="5" />
        <line x1="52" y1="28" x2="62" y2="28" />
        <line x1="52" y1="36" x2="62" y2="36" />
        <path d="M84 32 C 100 32, 104 50, 142 50" />
        <rect x="76" y="26" width="10" height="12" rx="2" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 160 64" className="cw-empty-art" data-kind="flat" aria-hidden>
      {[16, 32, 48].map((y) => (
        <line key={y} className="cw-empty-grat" x1="0" x2="160" y1={y} y2={y} />
      ))}
      <line className="cw-empty-trace" x1="0" x2="160" y1="32" y2="32" />
      <circle className="cw-empty-dot" cx="0" cy="32" r="3" />
    </svg>
  );
}

/** 仪器空态：待机的仪器（平直迹线 / 熄灭的点阵 / 没插线的端口）+ 一句原因 + 主按钮，绝不只放一行灰字。 */
export function EmptyInstrument({
  kind = 'flat',
  title,
  reason,
  actions,
  compact,
  children,
}: {
  kind?: EmptyKind;
  title: ReactNode;
  reason?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="cw-empty-inst" data-compact={compact ? 'true' : undefined} role="status">
      <EmptyArt kind={kind} />
      <h3>{title}</h3>
      {reason ? <p>{reason}</p> : null}
      {actions ? <div className="cw-empty-acts">{actions}</div> : null}
      {children}
    </div>
  );
}

/** 加载态：保留刻度网格，一条带拖尾的竖向扫描线循环划过。 */
export type SkeletonShape = 'scan' | 'rows' | 'cards' | 'columns' | 'form';

/**
 * 加载占位。按页面实际版式画静态骨架（行 / 卡片 / 分栏 / 表单），只有图表类仪器（shape='scan'）
 * 保留扫描线——扫描是「仪器在读数」的语义，不是通用转圈（用户反馈：很多页面不该扫）。
 */
export function ScanSkeleton({
  height = 160,
  label = '加载中',
  shape = 'rows',
  count,
}: {
  height?: number;
  label?: string;
  shape?: SkeletonShape;
  count?: number;
}) {
  if (shape === 'scan') {
    return (
      <div className="cw-scan" style={{ height }} aria-busy="true" aria-label={label}>
        <i />
        <span>{label}</span>
      </div>
    );
  }
  const n = count ?? (shape === 'rows' ? Math.max(2, Math.round(height / 48)) : shape === 'form' ? 3 : 3);
  return (
    <div className="cw-skel-wrap" data-shape={shape} aria-busy="true" aria-label={label}>
      <span className="cw-sr-only">{label}</span>
      {Array.from({ length: n }, (_, i) =>
        shape === 'rows' ? (
          <div key={i} className="cw-skel-line">
            <i style={{ width: `${68 - (i % 3) * 14}%` }} />
            <i style={{ width: `${34 - (i % 2) * 10}%` }} />
          </div>
        ) : shape === 'form' ? (
          <div key={i} className="cw-skel-field">
            <i />
            <i />
          </div>
        ) : (
          <div key={i} className="cw-skel-card" style={{ minHeight: shape === 'columns' ? height : Math.min(height, 200) }}>
            <i style={{ width: '40%' }} />
            <i style={{ width: '72%' }} />
            <i style={{ width: '56%' }} />
            {shape === 'columns' ? Array.from({ length: 6 }, (_, j) => <i key={j} style={{ width: `${84 - (j % 3) * 12}%` }} />) : null}
          </div>
        ),
      )}
    </div>
  );
}

// ── 小图形 ──

/** 迷你柱：最后一根点亮发光。values 为空时显示虚线框 + 说明。 */
export function MiniScope({ values, color, label, empty = '暂无历史观测', height = 26 }: { values: number[]; color?: string; label: string; empty?: string; height?: number }) {
  if (values.length < 2) {
    return (
      <span className="cw-miniscope-empty" style={{ height }}>
        {empty}
      </span>
    );
  }
  const max = Math.max(1, ...values);
  return (
    <span className="cw-miniscope" role="img" aria-label={label} style={{ height, ...(color ? ({ '--c': color } as CSSProperties) : {}) }}>
      {values.map((v, i) => (
        <i key={i} data-last={i === values.length - 1 ? 'true' : undefined} style={{ height: `${Math.max(6, (v / max) * 100)}%`, animationDelay: `${i * 15}ms` }} />
      ))}
    </span>
  );
}

/** 分布条：标签 / 条 / 数字 / 备注；宽度从 0 展开，逐条错开。 */
export function DistBars({
  rows,
  format = (v) => v.toLocaleString('zh-CN'),
}: {
  rows: { key: string; label: ReactNode; value: number; color?: string; note?: ReactNode; href?: string }[];
  format?: (v: number) => string;
}) {
  const max = Math.max(0, ...rows.map((r) => r.value));
  return (
    <div className="cw-distbars">
      {rows.map((r, i) => (
        <div key={r.key} style={{ '--c': r.color || 'var(--cw-cy)', '--i': i } as CSSProperties}>
          <span>{r.href ? <Link href={r.href}>{r.label}</Link> : r.label}</span>
          <s style={{ width: `${max > 0 ? Math.max(1, (r.value / max) * 100) : 0}%` }} />
          <b className="cw-num">{format(r.value)}</b>
          <em className="cw-num">{r.note ?? ''}</em>
        </div>
      ))}
    </div>
  );
}

/** 流程链路：完成实心绿、当前青色发光脉冲、未开始空心；节点可点。 */
export function SignalPath({
  steps,
}: {
  steps: { key: string; label: ReactNode; state: 'done' | 'current' | 'todo'; href?: string; hint?: string; sub?: ReactNode }[];
}) {
  return (
    <ol className="cw-path">
      {steps.map((s, i) => {
        const node = (
          <>
            <i aria-hidden />
            <span>{s.label}</span>
            {s.sub ? <small className="cw-num">{s.sub}</small> : null}
          </>
        );
        return (
          <li key={s.key} data-state={s.state} data-linked={i > 0 && steps[i - 1].state === 'done' ? 'true' : undefined} title={s.hint}>
            {s.href ? (
              <Link href={s.href} aria-current={s.state === 'current' ? 'step' : undefined}>
                {node}
              </Link>
            ) : (
              <div>{node}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** 形态色标：方块（图例）。 */
export function KindSwatch({ color, label }: { color: string; label?: ReactNode }) {
  return (
    <span className="cw-swatch-l">
      <b style={{ background: color }} />
      {label}
    </span>
  );
}
