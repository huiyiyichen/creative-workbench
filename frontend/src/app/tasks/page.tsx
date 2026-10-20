'use client';

/** 任务中心（创作工作台设计 7）：流程运行、生成、采集、分析的完整列表，可按类型、状态、项目、时间筛选。 */

import { Segmented, Select, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { CwPage, TopBar } from '@/design/components';
import { TaskRow } from '@/design/tasks';
import { projectsApi, type ProjectSummary } from '@/lib/api/_projects';
import { TASK_STATUS_LABEL, TASK_TYPE_LABEL, tasksApi, type TaskList, type TaskStatus, type TaskType } from '@/lib/api/_tasks';
import { onTasksChanged } from '@/lib/events';

const STATUS_ORDER: TaskStatus[] = ['running', 'waiting', 'failed', 'done', 'stopped'];

export default function TasksPage() {
  const [types, setTypes] = useState<TaskType[]>([]);
  const [status, setStatus] = useState<TaskStatus | 'all'>('all');
  const [project, setProject] = useState<number | undefined>();
  const [days, setDays] = useState(7);
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
  return (
    <CwPage>
      <TopBar title="任务" sub={counts ? <span className="cw-num">{data.active} 个进行中</span> : undefined} />
      <div className="cw-row cw-task-filters">
        <Segmented
          value={status}
          onChange={(v) => setStatus(v as TaskStatus | 'all')}
          options={[
            { value: 'all', label: '全部' },
            ...STATUS_ORDER.map((s) => ({ value: s, label: `${TASK_STATUS_LABEL[s]}${counts ? ` ${counts[s]}` : ''}` })),
          ]}
        />
        <Select
          mode="multiple"
          allowClear
          placeholder="全部类型"
          style={{ minWidth: 180 }}
          value={types}
          onChange={setTypes}
          options={(Object.keys(TASK_TYPE_LABEL) as TaskType[]).map((t) => ({ value: t, label: TASK_TYPE_LABEL[t] }))}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="全部项目"
          style={{ minWidth: 200 }}
          value={project}
          onChange={setProject}
          options={projects.map((p) => ({ value: p.id, label: p.title }))}
        />
        <Select
          value={days}
          onChange={setDays}
          style={{ width: 110 }}
          options={[1, 7, 30, 90].map((d) => ({ value: d, label: d === 1 ? '今天' : `近 ${d} 天` }))}
        />
      </div>
      {data === null ? <p className="cw-muted">加载中…</p> : null}
      {data && !data.items.length ? <p className="cw-muted">没有符合条件的任务。</p> : null}
      <div className="cw-task-list">
        {data?.items.map((t) => (
          <TaskRow key={t.key} task={t} onChanged={load} />
        ))}
      </div>
    </CwPage>
  );
}
