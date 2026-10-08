'use client';

import { useEffect, useState } from 'react';
import { Button, Drawer, Empty, List, Progress, Tag, Tooltip } from 'antd';
import { Film, LoaderCircle } from 'lucide-react';
import { studioApi } from '@/lib/api';
import type { StudioArtifact } from '@/lib/api';

export function ArtifactProgress({ artifact }: { artifact: StudioArtifact }) {
  const active = artifact.status === 'queued' || artifact.status === 'rendering';
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  const heartbeat = artifact.progress?.last_heartbeat ? new Date(artifact.progress.last_heartbeat).getTime() : 0;
  const storedElapsed = artifact.progress?.elapsed_seconds ?? 0;
  const elapsed = active && heartbeat ? storedElapsed + Math.max(0, Math.floor((now - heartbeat) / 1000)) : storedElapsed;
  const elapsedLabel = `${Math.floor(elapsed / 60)}分${String(elapsed % 60).padStart(2, '0')}秒`;
  const heartbeatAge = heartbeat ? Math.max(0, Math.floor((now - heartbeat) / 1000)) : null;
  return <div className="space-y-2">
    <div className="flex flex-wrap items-center gap-2">
      {active && <LoaderCircle size={15} className="animate-spin text-primary" />}
      <span className="text-sm font-medium">{artifact.progress?.stage || ({ queued: '等待制作', rendering: '制作中', done: '制作完成', error: '制作失败' }[artifact.status] || artifact.status)}</span>
      <Tag color={artifact.status === 'done' ? 'green' : artifact.status === 'error' ? 'red' : 'blue'}>版本 {artifact.version}</Tag>
      {active && <Tag color={heartbeatAge != null && heartbeatAge > 30 ? 'orange' : 'blue'}>{heartbeatAge != null && heartbeatAge > 30 ? '暂无新进度' : `已用 ${elapsedLabel}`}</Tag>}
    </div>
    {artifact.progress?.percent != null && <Progress percent={artifact.progress.percent} status={artifact.status === 'error' ? 'exception' : active ? 'active' : 'normal'} size="small" />}
    {artifact.error && <div className="text-xs text-red-600">{artifact.error}</div>}
    {active && heartbeatAge != null && <div className="text-xs text-gray-500">后台心跳：{heartbeatAge === 0 ? '刚刚' : `${heartbeatAge} 秒前`}{artifact.progress?.workspace_files != null && ` · 工作区文件 ${artifact.progress.workspace_files} 个`}</div>}
    {artifact.progress?.logs?.map((log, index) => <div key={index} className="flex gap-3 text-xs text-gray-500"><time className="font-mono">{new Date(log.at).toLocaleTimeString('zh-CN')}</time>{log.stage}</div>)}
  </div>;
}

export default function ProductionStatus() {
  const [jobs, setJobs] = useState<StudioArtifact[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    const update = () => void studioApi.jobs().then((data) => {
      if (!cancelled) { setJobs(data.items); setError(''); }
    }).catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : '任务加载失败'); });
    update();
    const timer = window.setInterval(update, 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);
  const active = jobs.filter((job) => ['queued', 'rendering'].includes(job.status));
  return <>
    <Tooltip title="制作任务"><Button type="text" onClick={() => setOpen(true)} icon={active.length ? <LoaderCircle size={17} className="animate-spin text-primary" /> : <Film size={17} />}>
      {active.length ? `制作中 ${active.length}` : '制作记录'}
    </Button></Tooltip>
    <Drawer title="制作任务" open={open} onClose={() => setOpen(false)} size="default">
      {error && <div className="mb-4 text-sm text-red-600">{error}</div>}
      {jobs.length ? <List dataSource={jobs} renderItem={(job) => <List.Item>
        <div className="w-full">
          <div className="mb-3 flex items-start justify-between gap-3"><span className="text-sm font-bold">{job.title}</span><Button size="small" href={`/studio?project_id=${job.project_id}&stage=2`} onClick={() => setOpen(false)}>打开</Button></div>
          <ArtifactProgress artifact={job} />
          {job.preview_path && <Button type="link" href={job.preview_path} target="_blank">预览成片</Button>}
        </div>
      </List.Item>} /> : <Empty description="暂无制作任务" />}
    </Drawer>
  </>;
}
