'use client';

/**
 * 统一筛选按钮（评审 #3 灵感库 / 任务）：未选时「授权 ⌄」，选中后「授权 · CC0 ×」。
 * 替代 antd Select——首屏不用等 cssinjs，和页面其他 ghost 按钮同一种外观。
 */

import { Dropdown } from 'antd';
import { ChevronDown, X } from 'lucide-react';

export type FilterOption<T extends string | number> = { value: T; label: string; count?: number };

export function FilterButton<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T | null | undefined;
  options: FilterOption<T>[];
  onChange: (v: T | undefined) => void;
}) {
  const cur = options.find((o) => o.value === value);
  return (
    <span className="cw-filterbtn" data-on={cur ? 'true' : undefined}>
      <Dropdown
        trigger={['click']}
        disabled={!options.length}
        menu={{
          selectable: true,
          selectedKeys: cur ? [String(cur.value)] : [],
          style: { maxHeight: 320, overflowY: 'auto' },
          items: options.map((o) => ({
            key: String(o.value),
            label: (
              <span className="cw-filterbtn-item">
                {o.label}
                {o.count ? <small className="cw-num">{o.count}</small> : null}
              </span>
            ),
          })),
          onClick: ({ key }) => onChange(options.find((o) => String(o.value) === key)?.value),
        }}
      >
        <button type="button" className="cw-filterbtn-main" aria-label={cur ? `${label}：${cur.label}` : label}>
          <span>{label}</span>
          {cur ? <b>{cur.label}</b> : <ChevronDown size={13} aria-hidden />}
        </button>
      </Dropdown>
      {cur ? (
        <button type="button" className="cw-filterbtn-clear" aria-label={`清除${label}`} onClick={() => onChange(undefined)}>
          <X size={12} />
        </button>
      ) : null}
    </span>
  );
}
