'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { activeTab, sectionTabsFor, type SectionTab } from './sections';

export function SectionTabs({ tabs, label }: { tabs?: SectionTab[]; label?: string }) {
  const pathname = usePathname() || '/';
  const list = tabs ?? sectionTabsFor(pathname);
  if (!list) return null;
  const current = activeTab(pathname, list);
  return (
    <nav className="cw-tabs" aria-label={label ?? '分页'}>
      {list.map((t) =>
        t.pending ? (
          <span key={t.href} aria-disabled="true" title={`${t.pending}上线`} style={{ padding: '8px 14px', color: 'var(--cw-faint)', fontSize: 14 }}>
            {t.label}
          </span>
        ) : (
          <Link key={t.href} href={t.href} aria-current={current === t.href ? 'page' : undefined}>
            {t.label}
          </Link>
        ),
      )}
    </nav>
  );
}
