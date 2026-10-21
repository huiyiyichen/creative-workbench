'use client';

/** 任务分区子页导航：任务 / 流程运行 / 后台任务（评审 #3 2.4：/stats/jobs 并入任务分区，用同款分段）。 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const ITEMS = [
  { href: '/tasks', label: '任务' },
  { href: '/runs', label: '流程运行' },
  { href: '/stats/jobs', label: '后台任务' },
];

export function TasksNav() {
  const path = usePathname() || '';
  return (
    <nav className="cw-seg" aria-label="任务分页">
      {ITEMS.map((i) => (
        <Link key={i.href} href={i.href} aria-current={path === i.href || path.startsWith(`${i.href}/`) ? 'page' : undefined}>
          {i.label}
        </Link>
      ))}
    </nav>
  );
}
