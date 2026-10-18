'use client';

/**
 * 调色台基础组件（自建，照样张）。antd 只在表单、下拉、日期、上传、虚拟表格、弹层里用。
 */

import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react';
import { cwAntdTheme } from './antd-theme';

export function CwPage({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <ConfigProvider theme={cwAntdTheme} locale={zhCN}>
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
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div className="cw-seg" role="group" aria-label={label}>
      {options.map((opt) => (
        <button key={opt.value} type="button" aria-pressed={opt.value === value} onClick={() => onChange(opt.value)}>
          {opt.label}
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
