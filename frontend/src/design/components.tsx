'use client';

/**
 * 调色台基础组件（自建，照样张）。antd 只在表单、下拉、日期、上传、虚拟表格、弹层里用。
 */

import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useLayoutEffect, useRef, useState, type ButtonHTMLAttributes, type CSSProperties, type ReactNode } from 'react';
import { Search as SearchGlyph, X as XGlyph } from 'lucide-react';
import { sparkPath } from '@/lib/collection';
import { kindColor, SignalArt } from './signal-art';
import { cwAntdThemeFor } from './antd-theme';
import { useCwTheme } from './theme';

export function CwPage({ children, className = '' }: { children: ReactNode; className?: string }) {
  const [mode] = useCwTheme();
  return (
    <ConfigProvider theme={cwAntdThemeFor(mode)} locale={zhCN} button={{ autoInsertSpace: false }}>
      <AntdApp component={false}>
        <div className={`cw-page ${className}`}>{children}</div>
      </AntdApp>
    </ConfigProvider>
  );
}

export function TopBar({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <header className="cw-topbar">
      <h1>{title}</h1>
      {sub ? <span className="cw-sub">{sub}</span> : null}
      <span className="cw-grow" />
      {children}
    </header>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'primary' | 'ghost';
  size?: 'default' | 'icon';
  icon?: ReactNode;
};

export function Button({ variant = 'default', size = 'default', icon, children, className = '', ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      className={`cw-btn ${className}`}
      data-variant={variant === 'default' ? undefined : variant}
      data-size={size === 'default' ? undefined : size}
      {...rest}
    >
      {icon}
      {children}
    </button>
  );
}

export function Chip({ color, children }: { color?: string; children: ReactNode }) {
  return (
    <span className="cw-chip" style={color ? ({ '--c': color } as CSSProperties) : undefined}>
      {color ? <b /> : null}
      {children}
    </span>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: ReactNode; count?: number | null; tone?: 'bad' }[];
  onChange: (value: T) => void;
  label: string;
}) {
  // 选中底块是一块滑块，切换时平移过去（设计评审 C13）
  const ref = useRef<HTMLDivElement>(null);
  const [thumb, setThumb] = useState<{ x: number; w: number } | null>(null);
  useLayoutEffect(() => {
    const host = ref.current;
    if (!host) return;
    const measure = () => {
      const el = host.querySelector<HTMLElement>('[aria-pressed="true"]');
      setThumb(el ? { x: el.offsetLeft, w: el.offsetWidth } : null);
    };
    measure();
    // 字体晚到、窗口缩放、计数变化都会改宽度：跟着重量
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    ro?.observe(host);
    void document.fonts?.ready.then(measure);
    return () => ro?.disconnect();
  }, [value, options.length]);
  return (
    <div className="cw-seg" role="group" aria-label={label} ref={ref} data-slide={thumb ? 'true' : undefined}>
      {thumb ? <i className="cw-seg-thumb" style={{ transform: `translateX(${thumb.x}px)`, width: thumb.w }} aria-hidden /> : null}
      {options.map((opt) => (
        <button key={opt.value} type="button" aria-pressed={opt.value === value} onClick={() => onChange(opt.value)}>
          {opt.label}
          {opt.count !== undefined && opt.count !== null ? <em data-tone={opt.tone}>{opt.count}</em> : null}
        </button>
      ))}
    </div>
  );
}

export function Card({ title, extra, children, className = '' }: { title?: ReactNode; extra?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`cw-card ${className}`}>
      {title ? (
        <div className="cw-card-head">
          {title}
          <span className="cw-grow" />
          {extra}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function SectionHead({ title, note, children }: { title: string; note?: ReactNode; children?: ReactNode }) {
  return (
    <div className="cw-section-head">
      <h2>{title}</h2>
      {note ? <small>{note}</small> : null}
      <span className="cw-grow" />
      {children}
    </div>
  );
}

export type Tone = 'ok' | 'warn' | 'bad' | 'off';

export function StatusDot({ tone, label }: { tone: Tone; label?: string }) {
  return <i className="cw-dot" data-tone={tone === 'off' ? undefined : tone} role={label ? 'img' : undefined} aria-label={label} />;
}

/** 数字：缺失显示「—」，不显示 0（AGENTS.md：缺失指标保持空值） */
export function Num({ value, digits = 0, suffix = '' }: { value: number | null | undefined; digits?: number; suffix?: string }) {
  if (value === null || value === undefined || Number.isNaN(value)) return <span className="cw-num cw-muted">—</span>;
  return (
    <span className="cw-num">
      {value.toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits })}
      {suffix}
    </span>
  );
}

/** 每日新增迷你柱 */
export function MiniBars({ values, color, label }: { values: number[]; color?: string; label: string }) {
  const max = Math.max(1, ...values);
  return (
    <div className="cw-bars" role="img" aria-label={label} style={color ? ({ '--c': color } as CSSProperties) : undefined}>
      {values.map((v, i) => (
        <i key={i} data-zero={v === 0 ? 'true' : undefined} style={{ height: v === 0 ? 2 : `${Math.max(12, (v / max) * 100)}%` }} />
      ))}
    </div>
  );
}

/** 观测曲线：不足 2 个点显示「暂无历史观测」，不画 0（改造方案 3.3） */
export function Sparkline({
  values,
  label,
  color,
  width = 120,
  height = 28,
}: {
  values: number[];
  label: string;
  color?: string;
  width?: number;
  height?: number;
}) {
  const d = sparkPath(values, width, height);
  if (!d) return <span className="cw-spark-empty">暂无历史观测</span>;
  return (
    <svg className="cw-spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}
      style={color ? ({ '--c': color } as CSSProperties) : undefined}>
      <path d={d} />
    </svg>
  );
}

/**
 * 封面：本地缓存（主色占位、懒加载）；缺失或加载失败时用按标题生成的示波器图形（改造方案 3.4）。
 * 横版 16:9，竖版 9:16。
 */
export function Cover({
  src,
  title,
  color,
  orientation,
  kind,
  badge,
}: {
  src: string | null;
  title: string;
  color?: string | null;
  orientation?: 'landscape' | 'portrait' | null;
  kind?: string | null;
  badge?: string | null;
}) {
  const [failed, setFailed] = useState(false);
  const showImg = Boolean(src) && !failed;
  return (
    <div
      className="cw-cover"
      data-orientation={orientation === 'portrait' ? 'portrait' : 'landscape'}
      style={{ background: color || undefined }}
    >
      {showImg ? (
        // 本地缓存的封面走自己的 /media 接口，next/image 的优化在这里没有意义
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src!} alt="" loading="lazy" onError={() => setFailed(true)} />
      ) : (
        <SignalArt title={title} kind={kind} />
      )}
      {kind ? <span className="cw-cover-kind" style={{ '--c': kindColor(kind) } as CSSProperties} /> : null}
      {badge ? <span className="cw-cover-badge cw-num">{badge}</span> : null}
    </div>
  );
}

export { kindColor } from './signal-art';

/**
 * 全站统一搜索框（替换 antd Input.Search）：内嵌放大镜、有字时显示清空、Esc 清空、回车提交。
 * 不带独立的「搜索」按钮——回车即可。
 */
export function SearchField({
  value,
  onChange,
  onSubmit,
  placeholder = '搜索',
  width,
  label,
  autoFocus,
  busy,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit?: (v: string) => void;
  placeholder?: string;
  width?: number | string;
  label?: string;
  autoFocus?: boolean;
  busy?: boolean;
}) {
  return (
    <span className="cw-searchfield" style={width !== undefined ? { width, flex: 'none' } : undefined} data-busy={busy ? 'true' : undefined}>
      <SearchGlyph size={14} aria-hidden />
      <input
        type="search"
        value={value}
        placeholder={placeholder}
        aria-label={label || placeholder}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            onSubmit?.(value);
          } else if (e.key === 'Escape' && value) {
            e.preventDefault();
            e.stopPropagation();
            onChange('');
          }
        }}
      />
      {value ? (
        <button type="button" className="cw-searchfield-clear" aria-label="清空" onClick={() => onChange('')}>
          <XGlyph size={12} aria-hidden />
        </button>
      ) : null}
    </span>
  );
}
