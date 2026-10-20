'use client';

/** 任务中心部件：任务行、全局抽屉（导航「任务」打开，按进行中 / 失败 / 完成分组）、实时计数。 */

import Link from 'next/link';
import { Drawer, message, notification } from 'antd';
import { Bot, Download, Image as ImageIcon, ScanSearch, Table2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Button } from './components';
import { TASK_STATUS_LABEL, fmtDuration, groupTasks, subscribeTasks, tasksApi, type TaskStatus, type TaskType, type TaskView } from '@/lib/api/_tasks';
import { onTasksChanged } from '@/lib/events';

const TYPE_ICON: Record<TaskType, typeof Bot> = { flow: Bot, generation: ImageIcon, sync: Download, analysis: ScanSearch, feishu: Table2 };
export const TASK_STATUS_COLOR: Record<TaskStatus, string> = {
  running: 'var(--cw-cy)',
  waiting: 'var(--cw-yl)',
  failed: 'var(--cw-rd)',
  done: 'var(--cw-gr)',
  stopped: 'var(--cw-dim)',
};

export function TaskRow({ task, onChanged, onOpen }: { task: TaskView; onChanged?: () => void; onOpen?: () => void }) {
  const Icon = TYPE_ICON[task.type] || Bot;
  const act = async (kind: 'retry' | 'stop') => {
    try {
      await (kind === 'retry' ? tasksApi.retry(task.key) : tasksApi.stop(task.key));
      onChanged?.();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '操作失败');
    }
  };
  return (
    <div className="cw-task" data-status={task.status}>
      <Icon className="cw-task-icon" aria-hidden />
      <div className="cw-task-main">
        <Link href={task.href} className="cw-task-title" onClick={onOpen}>
          <small className="cw-muted">{task.kind_label}</small> {task.title}
        </Link>
        <div className="cw-task-meta">
          {task.project_title ? (
            <Link href={`/projects/${task.project_id}`} onClick={onOpen}>
              {task.project_title}
            </Link>
          ) : null}
          {task.output_title ? <span>{task.output_title}</span> : null}
          {task.stage ? <span>{task.stage}</span> : null}
          <span className="cw-num">{fmtDuration(task.duration_ms)}</span>
          {task.cost ? <span className="cw-num">¥{task.cost.toFixed(2)}</span> : null}
        </div>
        {task.status === 'failed' && task.reason ? (
          <p className="cw-task-reason">
            {task.reason}
            {task.hint ? <span className="cw-muted">。{task.hint}</span> : null}
          </p>
        ) : null}
      </div>
      <span className="cw-task-status" style={{ color: TASK_STATUS_COLOR[task.status] }}>
        {TASK_STATUS_LABEL[task.status]}
      </span>
      <span className="cw-task-acts">
        {task.can_retry ? (
          <Button onClick={() => act('retry')}>
            重试
          </Button>
        ) : null}
        {task.can_stop ? (
          <Button onClick={() => act('stop')}>
            停止
          </Button>
        ) : null}
      </span>
    </div>
  );
}

/** 进行中的任务数（SSE 推送）；任务完成 / 失败时弹通知 */
export function useTaskCount(): number {
  const [active, setActive] = useState(0);
  // 先取一次、之后每 30 秒兜底（SSE 被代理缓冲或断开时计数也不会停住）
  useEffect(() => {
    const load = () =>
      tasksApi
        .summary()
        .then((d) => setActive(d.active))
        .catch(() => undefined);
    void load();
    const t = setInterval(load, 120_000);
    return () => clearInterval(t);
  }, []);
  useEffect(
    () =>
      subscribeTasks((p) => {
        setActive(p.active);
        for (const t of p.finished) {
          if (t.status === 'waiting') {
            notification.info({ message: `${t.kind_label}等你处理`, description: t.title, placement: 'bottomRight' });
          } else if (t.status === 'failed') {
            notification.error({ message: `${t.kind_label}失败`, description: `${t.title}：${t.reason || ''}`, placement: 'bottomRight' });
          } else if (t.status === 'done') {
            notification.success({ message: `${t.kind_label}完成`, description: t.title, placement: 'bottomRight' });
          }
        }
      }),
    [],
  );
  return active;
}

export function TaskDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [items, setItems] = useState<TaskView[] | null>(null);
  const load = useCallback(() => {
    tasksApi
      .list({ days: 2, limit: 60 })
      .then((d) => setItems(d.items))
      .catch(() => setItems([]));
  }, []);
  useEffect(() => {
    if (!open) return;
    load();
    // 任务有变化时由全局事件流触发刷新；30 秒兜底（事件流被代理缓冲时）
    const off = onTasksChanged(load);
    const t = setInterval(load, 30_000);
    return () => {
      off();
      clearInterval(t);
    };
  }, [open, load]);
  const groups = groupTasks(items || []);
  return (
    <Drawer
      title="任务"
      open={open}
      onClose={onClose}
      size={520}
      className="cw-drawer"
      extra={
        <Link href="/tasks" className="cw-link-btn" onClick={onClose}>
          全部任务
        </Link>
      }
    >
      {items === null ? <p className="cw-muted">加载中…</p> : null}
      {items && !items.length ? <p className="cw-muted">最近两天没有任务。</p> : null}
      {groups.map((g) => (
        <section key={g.id} className="cw-task-group">
          <h3>
            {g.label} <span className="cw-num cw-muted">{g.items.length}</span>
          </h3>
          {g.items.map((t) => (
            <TaskRow key={t.key} task={t} onChanged={load} onOpen={onClose} />
          ))}
        </section>
      ))}
    </Drawer>
  );
}
