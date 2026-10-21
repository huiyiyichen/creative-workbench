'use client';

/** 任务中心（创作工作台设计 7）：流程运行、生成、采集、分析的完整列表，可按类型、状态、项目、时间筛选。 */

import { message } from 'antd';
import { FilterButton } from '@/design/filter-button';
import { useCallback, useEffect, useState } from 'react';
import { CwPage, Segmented as CwSegmented, TopBar } from '@/design/components';
import { EmptyInstrument, Instrument, Readout, Readouts, ScanSkeleton, StatusLamp } from '@/design/instrument';
import { TaskFold, TaskLanes, TaskRow } from '@/design/tasks';
import { TasksNav } from '@/design/TasksNav';
import { sortTasks } from '@/lib/task-lanes';
import { projectsApi, type ProjectSummary } from '@/lib/api/_projects';
import { TASK_STATUS_LABEL, TASK_TYPE_LABEL, foldTasks, tasksApi, type TaskList, type TaskStatus, type TaskType } from '@/lib/api/_tasks';
import { onTasksChanged } from '@/lib/events';

const STATUS_ORDER: TaskStatus[] = ['running', 'waiting', 'failed', 'done', 'stopped'];

export default function TasksPage() {
  const [types, setTypes] = useState<TaskType[]>([]);
  const [status, setStatus] = useState<TaskStatus | 'all'>('all');
  const [project, setProject] = useState<number | undefined>();
  const [days, setDays] = useState(1);
  const [data, setData] = useState<TaskList | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const load = useCallback(() => {
    tasksApi
      .list({ type: types.length ? types : undefined, status: status === 'all' ? undefined : status, project, days, limit: 200 })
      .then(setData)
      .catch((err) => message.error(err instanceof Error ? err.message : '加载失败'));
  }, [types, status, project, days]);
  useEffect(() => {
    load();
    const off = onTasksChanged(load);
    const t = setInterval(load, 30_000);
    return () => {
      off();
      clearInterval(t);
    };
  }, [load]);
  useEffect(() => {
    projectsApi
      .list()
      .then((r) => setProjects(r.items))
      .catch(() => setProjects([]));
  }, []);
  const counts = data?.counts;
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => setNow(Date.now()), [data]);
  const items = data ? sortTasks(data.items) : [];
  const failed = counts?.failed ?? 0;
  const total = counts ? Object.values(counts).reduce((a, b) => a + b, 0) : 0;
  const totalCost = data ? data.items.reduce((n, t) => n + (t.cost || 0), 0) : 0;
  return (
    <CwPage>
      <TopBar title="任务" sub={counts ? <span className="cw-num">{`近 ${days === 1 ? '24 小时' : `${days} 天`} · ${total} 个`}</span> : undefined}>
        {counts ? (
          <StatusLamp
            tone={data!.active ? 'run' : failed ? 'bad' : 'ok'}
            label={data!.active ? `${data!.active} 个进行中` : failed ? `${failed} 个失败` : '都处理完了'}
          />
        ) : null}
        <TasksNav />
        <CwSegmented
          label="时间范围"
          value={String(days)}
          onChange={(v) => setDays(Number(v))}
          options={[1, 7, 30].map((d) => ({ value: String(d), label: d === 1 ? '24 小时' : `${d} 天` }))}
        />
      </TopBar>
      {data === null ? (
        <ScanSkeleton height={220} />
      ) : (
        <Instrument title="任务泳道" legend={<span className="cw-muted" style={{ fontSize: 12 }}>片段长度 = 实际耗时</span>}>
          <Readouts>
            <Readout label="进行中" value="0" count={data.active} sub={counts && counts.waiting ? `其中 ${counts.waiting} 个等你处理` : undefined} tone={counts && counts.waiting ? 'warn' : undefined} />
            <Readout label="失败" value="0" count={failed} tone={failed ? 'bad' : 'good'} sub={failed ? '可以在下面重试' : '没有失败'} />
            <Readout label="完成" value="0" count={counts?.done ?? 0} />
            {totalCost > 0 ? <Readout label="花费" value={`¥${totalCost.toFixed(2)}`} sub="生成与流程运行" /> : null}
          </Readouts>
          {now ? <TaskLanes items={data.items} hours={days * 24} now={now} /> : null}
        </Instrument>
      )}
      <div className="cw-row cw-task-filters" style={{ marginTop: 20 }}>
        <CwSegmented
          label="状态"
          value={status}
          onChange={(v) => setStatus(v as TaskStatus | 'all')}
          options={[
            { value: 'all', label: '全部' },
            ...STATUS_ORDER.map((s) => ({ value: s, label: TASK_STATUS_LABEL[s], count: counts ? counts[s] : null, tone: s === 'failed' && counts?.failed ? ('bad' as const) : undefined })),
          ]}
        />
        <FilterButton label="类型" value={types[0]} onChange={(v) => setTypes(v ? [v] : [])} options={(Object.keys(TASK_TYPE_LABEL) as TaskType[]).map((t) => ({ value: t, label: TASK_TYPE_LABEL[t] }))} />
        <FilterButton label="项目" value={project} onChange={setProject} options={projects.map((p) => ({ value: p.id, label: p.title }))} />
      </div>
      {data && !items.length ? (
        status === 'failed' ? (
          <EmptyInstrument kind="flat" title={`近 ${days === 1 ? '24 小时' : `${days} 天`}没有失败的任务`} reason="失败的采集、生成、流程运行会出现在这里，可以一键重试。" />
        ) : (
          <EmptyInstrument kind="flat" title="没有符合条件的任务" reason="采集、分析、生成、流程运行和飞书写入都会记在任务中心。" />
        )
      ) : null}
      <div className="cw-task-list cw-stagger">
        {foldTasks(items).map((e) => (e.kind === 'one' ? <TaskRow key={e.task.key} task={e.task} onChanged={load} /> : <TaskFold key={e.key} tasks={e.tasks} onChanged={load} />))}
      </div>
    </CwPage>
  );
}
