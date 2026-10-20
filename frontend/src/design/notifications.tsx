'use client';

/** 通知中心：导航底部铃铛（带未读数）+ 抽屉。来源：采集自动处理、日报 / 周刊、流程等你处理、全流程进度。 */

import Link from 'next/link';
import { Drawer } from 'antd';
import { Bell } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { notificationsApi } from '@/lib/api';
import { relativeTime } from '@/lib/collection';
import { notifyColor, notifyHref } from '@/lib/notify';
import type { NotificationItem } from '@/types';

export function useUnreadCount(): [number, () => void] {
  const [count, setCount] = useState(0);
  const load = useCallback(() => {
    notificationsApi
      .unreadCount()
      .then((r) => setCount(r.count))
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    const onFocus = () => load();
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(t);
      window.removeEventListener('focus', onFocus);
    };
  }, [load]);
  return [count, load];
}

export function NotifyButton({ count, onOpen }: { count: number; onOpen: () => void }) {
  const label = count ? `通知（${count} 条未读）` : '通知';
  return (
    <button type="button" className="cw-nav-item" title={label} aria-label={label} onClick={onOpen}>
      <Bell aria-hidden="true" />
      {count ? <i className="cw-nav-badge" aria-hidden="true" /> : null}
    </button>
  );
}

export function NotificationDrawer({ open, onClose, onChanged }: { open: boolean; onClose: () => void; onChanged: () => void }) {
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);

  const load = useCallback(() => {
    notificationsApi
      .list({ unread: unreadOnly || undefined, limit: 60 })
      .then((r) => setItems(r.notifications))
      .catch(() => setItems([]));
  }, [unreadOnly]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const markRead = async (n: NotificationItem) => {
    if (n.is_read) return;
    setItems((cur) => cur?.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)) ?? cur);
    await notificationsApi.markRead(n.id).catch(() => undefined);
    onChanged();
  };
  const markAll = async () => {
    await notificationsApi.markAllRead().catch(() => undefined);
    setItems((cur) => cur?.map((x) => ({ ...x, is_read: true })) ?? cur);
    onChanged();
  };
  const remove = async (n: NotificationItem) => {
    setItems((cur) => cur?.filter((x) => x.id !== n.id) ?? cur);
    await notificationsApi.delete(n.id).catch(() => undefined);
    onChanged();
  };

  const unread = items?.filter((n) => !n.is_read).length ?? 0;
  return (
    <Drawer
      title="通知"
      open={open}
      onClose={onClose}
      size={460}
      className="cw-drawer"
      extra={
        <span className="cw-row">
          <button type="button" className="cw-link-btn" aria-pressed={unreadOnly} onClick={() => setUnreadOnly((v) => !v)}>
            {unreadOnly ? '看全部' : '只看未读'}
          </button>
          <button type="button" className="cw-link-btn" disabled={!unread} onClick={markAll}>
            全部已读
          </button>
        </span>
      }
    >
      {items === null ? <p className="cw-muted">加载中…</p> : null}
      {items && !items.length ? <p className="cw-empty">{unreadOnly ? '没有未读通知。' : '还没有通知。采集自动处理、报告生成、流程等你处理时会出现在这里。'}</p> : null}
      <ul className="cw-notify-list">
        {items?.map((n) => {
          const href = notifyHref(n);
          const body = (
            <>
              <b className="cw-notify-dot" style={{ background: n.is_read ? 'transparent' : notifyColor(n.type), borderColor: notifyColor(n.type) }} aria-hidden />
              <span className="cw-notify-main">
                <span className="cw-notify-title">{n.title}</span>
                <span className="cw-notify-msg">{n.message}</span>
              </span>
              <span className="cw-num cw-notify-at">{relativeTime(n.created_at)}</span>
            </>
          );
          return (
            <li key={n.id} data-read={n.is_read || undefined}>
              {href ? (
                <Link
                  href={href}
                  onClick={() => {
                    void markRead(n);
                    onClose();
                  }}
                >
                  {body}
                </Link>
              ) : (
                <button type="button" onClick={() => void markRead(n)}>
                  {body}
                </button>
              )}
              <button type="button" className="cw-link-btn cw-notify-del" aria-label="删除这条通知" onClick={() => void remove(n)}>
                删除
              </button>
            </li>
          );
        })}
      </ul>
    </Drawer>
  );
}
