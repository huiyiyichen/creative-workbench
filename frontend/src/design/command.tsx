'use client';

/** 全局跳转面板（Ctrl+K）与快捷键说明（?）。 */

import { Modal } from 'antd';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CW_NAV, CW_NAV_BOTTOM } from './nav';
import { SHORTCUTS, filterCommands, type CommandItem } from '@/lib/command';
import { projectsApi } from '@/lib/api/_projects';
import { SEARCH_GROUP_LABEL, SEARCH_GROUP_ORDER, searchApi } from '@/lib/api/_search';

const NAV_KEYWORDS: Record<string, string> = {
  today: 'today jr home',
  hot: 'hot rd trending',
  reports: 'reports bg daily weekly monthly rb zk yk',
  topics: 'dossiers zt',
  library: 'library lgk notes favorites',
  projects: 'projects xm',
  works: 'works zp',
  tasks: 'tasks rw runs',
  sources: 'sources xy',
  settings: 'settings sz model mx',
};

const EXTRA_PAGES: CommandItem[] = [
  { id: 'p-model', label: '设置 · 模型', group: '页面', href: '/admin/model-eval', keywords: 'model llm mx' },
  { id: 'p-prompts', label: '设置 · 提示词', group: '页面', href: '/admin/prompts', keywords: 'prompts tsc' },
  { id: 'p-feishu', label: '设置 · 飞书', group: '页面', href: '/settings/feishu', keywords: 'feishu lark fs' },
  { id: 'p-daily', label: '日报', group: '页面', href: '/daily', keywords: 'daily rb' },
  { id: 'p-search', label: '搜索 · 按关键词抓取', group: '页面', href: '/search', keywords: 'search crawl ss zq' },
];

/** 其他地方（导航按钮）打开面板用的事件名 */
export const OPEN_EVENT = 'cw:command';

function isTyping(el: EventTarget | null): boolean {
  const t = el as HTMLElement | null;
  if (!t) return false;
  return t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName);
}

export function CommandPalette({ onToggleTheme, onOpenTasks }: { onToggleTheme: () => void; onOpenTasks: () => void }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [help, setHelp] = useState(false);
  const [q, setQ] = useState('');
  const [cursor, setCursor] = useState(0);
  const [projects, setProjects] = useState<CommandItem[]>([]);
  const [hits, setHits] = useState<CommandItem[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setHelp(false);
        setOpen((v) => !v);
      } else if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey && !isTyping(e.target)) {
        e.preventDefault();
        setHelp(false);
        setOpen(true);
      } else if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey && !isTyping(e.target)) {
        e.preventDefault();
        setOpen(false);
        setHelp((v) => !v);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener('keydown', onKey);
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener(OPEN_EVENT, onOpen);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    setQ('');
    setCursor(0);
    requestAnimationFrame(() => inputRef.current?.focus());
    projectsApi
      .list({})
      .then((r) => setProjects(r.items.slice(0, 50).map((p) => ({ id: `proj-${p.id}`, label: p.title || p.theme, group: '项目' as const, href: `/projects/${p.id}`, keywords: p.theme }))))
      .catch(() => setProjects([]));
  }, [open]);

  const base: (CommandItem & { run?: () => void })[] = useMemo(
    () => [
      ...[...CW_NAV.flatMap((g) => g.items), ...CW_NAV_BOTTOM]
        .filter((i) => !i.pending)
        .map((i) => ({ id: `nav-${i.id}`, label: i.label, group: '页面' as const, href: i.href, keywords: NAV_KEYWORDS[i.id] })),
      ...EXTRA_PAGES,
      { id: 'act-new', label: '新建项目', group: '操作', href: '/projects/new', keywords: 'new project xjxm' },
      { id: 'act-tasks', label: '打开任务抽屉', group: '操作', keywords: 'tasks rw', run: onOpenTasks },
      { id: 'act-theme', label: '切换亮色 / 暗色', group: '操作', keywords: 'theme dark light zt', run: onToggleTheme },
      { id: 'act-help', label: '快捷键', group: '操作', keywords: 'shortcuts kjj ?', run: () => setHelp(true) },
    ],
    [onOpenTasks, onToggleTheme],
  );
  const all = useMemo(() => [...base, ...projects], [base, projects]);

  // 库内命中：输入停 250ms 后查一次，每类最多 3 条
  useEffect(() => {
    const term = q.trim();
    if (!open || !term) {
      setHits([]);
      return;
    }
    let alive = true;
    const t = setTimeout(() => {
      searchApi
        .search(term, { limit: 3, groups: ['contents', 'library', 'notes', 'reports'] })
        .then((r) => {
          if (!alive) return;
          setHits(
            SEARCH_GROUP_ORDER.flatMap((g) =>
              (r.groups[g] ?? []).map((h) => ({ id: `hit-${g}-${h.id}`, label: h.title, group: '结果' as const, href: h.href, hint: SEARCH_GROUP_LABEL[g] })),
            ).slice(0, 8),
          );
        })
        .catch(() => alive && setHits([]));
    }, 250);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [q, open]);

  const shown = useMemo(() => {
    const term = q.trim();
    const local = filterCommands(all, q, term ? 8 : 14) as (CommandItem & { run?: () => void })[];
    if (!term) return local;
    const search: CommandItem = { id: 'search', label: `搜索「${term}」：库内内容 + 去平台抓`, group: '搜索', href: `/search?q=${encodeURIComponent(term)}` };
    return [search, ...local, ...hits];
  }, [all, q, hits]);

  const pick = useCallback(
    (item: CommandItem & { run?: () => void }) => {
      setOpen(false);
      if (item.run) item.run();
      else if (item.href) router.push(item.href);
    },
    [router],
  );

  return (
    <>
      <Modal open={open} onCancel={() => setOpen(false)} footer={null} closable={false} width={560} className="cw-cmd" destroyOnHidden>
        <input
          ref={inputRef}
          className="cw-cmd-input"
          placeholder="搜索内容，或跳转到页面、项目、操作…"
          value={q}
          aria-label="全局搜索与跳转"
          onChange={(e) => {
            setQ(e.target.value);
            setCursor(0);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault();
              setCursor((c) => Math.min(shown.length - 1, c + 1));
            } else if (e.key === 'ArrowUp') {
              e.preventDefault();
              setCursor((c) => Math.max(0, c - 1));
            } else if (e.key === 'Enter' && shown[cursor]) {
              e.preventDefault();
              pick(shown[cursor]);
            }
          }}
        />
        <ul className="cw-cmd-list" role="listbox">
          {shown.map((it, i) => (
            <li key={it.id} role="option" aria-selected={i === cursor} data-search={it.group === '搜索' || undefined} onMouseEnter={() => setCursor(i)} onClick={() => pick(it)}>
              <span>{it.label}</span>
              <small>{it.hint ?? it.group}</small>
            </li>
          ))}
          {!shown.length ? <li className="cw-empty">没有匹配的条目</li> : null}
        </ul>
        <div className="cw-cmd-foot">↑↓ 选择 · Enter 打开 · Esc 关闭 · ? 快捷键</div>
      </Modal>
      <Modal open={help} onCancel={() => setHelp(false)} footer={null} title="快捷键" width={420}>
        <dl className="cw-keys">
          {SHORTCUTS.map((s) => (
            <div key={s.keys}>
              <dt>
                {s.keys.split(' ').map((k) => (
                  <kbd key={k}>{k}</kbd>
                ))}
              </dt>
              <dd>{s.desc}</dd>
            </div>
          ))}
        </dl>
      </Modal>
    </>
  );
}
