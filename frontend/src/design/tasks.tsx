'use client';

/** 任务中心部件：任务行、全局抽屉（导航「任务」打开，按进行中 / 失败 / 完成分组）、实时计数。 */

import Link from 'next/link';
import { Drawer, message, notification } from 'antd';
import { Bot, Download, Image as ImageIcon, ScanSearch, Table2 } from 'lucide-react';
import { useCallback, useEffect, useState, type CSSProperties } from 'react';
import { Button } from './components';
import { TASK_STATUS_LABEL, TASK_TYPE_LABEL, fmtDuration, groupTasks, subscribeTasks, tasksApi, type TaskStatus, type TaskType, type TaskView } from '@/lib/api/_tasks';
import { onTasksChanged } from '@/lib/events';
import { LANE_ORDER, batchClips, laneClips } from '@/lib/task-lanes';
import { CN_OFFSET_MS, cnParts, fmtHM } from '@/lib/time-cn';
import { StatusLamp, type LampTone } from './instrument';

const LAMP: Record<TaskStatus, LampTone> = { running: 'run', waiting: 'warn', failed: 'bad', done: 'ok', stopped: 'off' };

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
  const at = task.started_at || task.created_at;
  return (
    <div className="cw-task" data-status={task.status}>
      <StatusLamp tone={LAMP[task.status]} title={TASK_STATUS_LABEL[task.status]} />
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
        </div>
        {task.status === 'failed' && task.reason ? (
          <p className="cw-task-reason">
            {task.reason}
            {task.hint ? <span className="cw-muted">。{task.hint}</span> : null}
          </p>
        ) : null}
      </div>
      {task.status === 'failed' || task.status === 'waiting' ? (
        <span className="cw-task-status" style={{ color: TASK_STATUS_COLOR[task.status] }}>
          {TASK_STATUS_LABEL[task.status]}
        </span>
      ) : (
        <span />
      )}
      <span className="cw-num cw-muted cw-task-dur">{fmtDuration(task.duration_ms)}</span>
      <span className="cw-num cw-muted cw-task-at">
        {fmtHM(at)}
        {task.cost ? <small> · ¥{task.cost.toFixed(2)}</small> : null}
      </span>
      <span className="cw-task-acts">
        {task.can_retry ? <Button onClick={() => act('retry')}>重试</Button> : null}
        {task.can_stop ? <Button onClick={() => act('stop')}>停止</Button> : null}
      </span>
    </div>
  );
}

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

/** 任务泳道：轨道 = 任务类型，片段宽度 = 实际耗时，颜色 = 状态；失败发光、运行中脉冲，播放头 = 现在。 */
export function TaskLanes({ items, hours, now }: { items: TaskView[]; hours: number; now: number }) {
  const end = now;
  const start = now - hours * 3600 * 1000;
  const lanes = laneClips(items, start, end, now);
  const step = hours <= 24 ? 3 : hours <= 24 * 7 ? 24 : 24 * 7;
  const ticks: { pos: number; label: string }[] = [];
  const H = 3600 * 1000;
  let t = Math.ceil((start + CN_OFFSET_MS) / (step * H)) * step * H - CN_OFFSET_MS;
  for (; t < end; t += step * H) {
    const p = cnParts(t);
    ticks.push({ pos: (t - start) / (end - start), label: step < 24 ? `${String(p.h).padStart(2, '0')}:00` : `${p.mo}/${p.d}` });
  }
  return (
    <div className="cw-timeline cw-lanes" style={{ border: 0, background: 'none' }}>
      <div className="cw-tl-grid">
        <div className="cw-ruler">
          <span />
          <div className="cw-ruler-scale">
            {ticks.map((tk) => (
              <span key={tk.pos} className="cw-num" style={{ left: `${tk.pos * 100}%` }}>
                {tk.label}
              </span>
            ))}
          </div>
        </div>
        {LANE_ORDER.filter((type) => (lanes.get(type) || []).length).map((type) => {
          const clips = lanes.get(type) || [];
          const Icon = TYPE_ICON[type] || Bot;
          return (
            <div className="cw-track" key={type}>
              <span className="cw-track-name">
                <Icon size={12} aria-hidden /> {TASK_TYPE_LABEL[type]}
                {clips.length ? <em className="cw-num">{clips.length}</em> : null}
              </span>
              <div className="cw-lane">
                {ticks.map((tk) => (
                  <i key={tk.pos} className="cw-lane-tick" style={{ left: `${tk.pos * 100}%` }} />
                ))}
                {batchClips(clips).map((b) => {
                  const c = b.clips[0];
                  const label = b.count > 1 ? `${b.count} 个${TASK_TYPE_LABEL[type]}任务${b.failed ? `，${b.failed} 个失败` : ''}` : `${c.task.kind_label} · ${c.title} · ${TASK_STATUS_LABEL[c.status]}${c.task.duration_ms ? ` · ${fmtDuration(c.task.duration_ms)}` : ''}`;
                  return (
                    <Link
                      key={b.key}
                      href={b.failed ? (b.clips.find((x) => x.status === 'failed')?.task.href ?? c.task.href) : c.task.href}
                      className="cw-taskclip"
                      data-status={b.status}
                      data-batch={b.count > 1 ? 'true' : undefined}
                      title={label}
                      style={{ left: `${b.left * 100}%`, width: `max(${b.count > 1 ? 14 : 4}px, ${b.width * 100}%)`, '--c': TASK_STATUS_COLOR[b.status] } as CSSProperties}
                    >
                      {b.count > 1 ? <b className="cw-num">{b.count}</b> : null}
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
        {lanes.size === 0 ? <div className="cw-tl-empty">这段时间没有任务</div> : null}
        <div className="cw-playhead" data-edge="right" style={{ left: 'calc(var(--cw-track-w) + (100% - var(--cw-track-w)) * 1)' }}>
          <span className="cw-num">
            现在
          </span>
        </div>
      </div>
    </div>
  );
}
