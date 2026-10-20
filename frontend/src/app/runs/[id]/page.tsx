'use client';

/** 运行视图（创作工作台设计 7.1）：节点图 / 时间线 / 调用树，节点详情，人工关卡；SSE 实时更新。 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { InputNumber, Modal, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, CwPage, TopBar } from '@/design/components';
import {
  ArtifactBody,
  GatePanel,
  RunGraph,
  RunTimeline,
  STATUS_COLOR,
  STATUS_LABEL,
  StepDetailPanel,
  TraceTree,
  fmtCost,
  fmtMs,
  stepForRenderId,
} from '@/design/runs';
import { mergeStep, runsApi, subscribeRun, type RunDetail, type TraceStep } from '@/lib/api/_runs';

type Tab = 'graph' | 'timeline' | 'trace';

export default function RunPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const router = useRouter();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [tab, setTab] = useState<Tab>('graph');
  const [selected, setSelected] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceStep[] | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [addCost, setAddCost] = useState(1);
  const [now, setNow] = useState(() => Date.now());

  const reload = useCallback(() => {
    runsApi
      .get(id)
      .then(setDetail)
      .catch((err) => message.error(err instanceof Error ? err.message : '加载失败'));
  }, [id]);

  useEffect(() => {
    reload();
    const off = subscribeRun(id, {
      snapshot: setDetail,
      run: (run) => {
        setDetail((d) => (d ? { ...d, run } : d));
        if (['done', 'waiting', 'failed', 'paused', 'stopped'].includes(run.status)) reload();
      },
      step: (s) => setDetail((d) => (d ? { ...d, steps: mergeStep(d.steps, s) } : d)),
    });
    return off;
  }, [id, reload]);

  // 运行中每秒刷新耗时
  const running = detail?.run.status === 'running' || detail?.run.status === 'queued';
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [running]);

  useEffect(() => {
    if (tab !== 'trace') return;
    runsApi
      .trace(id)
      .then((r) => setTrace(r.items))
      .catch(() => setTrace([]));
  }, [tab, id, detail?.steps.length, detail?.run.status]);

  if (!detail) {
    return (
      <CwPage>
        <TopBar title="运行" />
        <p className="cw-muted">加载中…</p>
      </CwPage>
    );
  }
  const { run } = detail;
  const elapsed = run.started_at
    ? (run.finished_at ? new Date(run.finished_at).getTime() : now) - new Date(run.started_at).getTime()
    : null;
  const pending = detail.steps.find((s) => s.status === 'waiting' && s.executor === 'human');
  const step = stepForRenderId(detail.steps, selected);
  const finals = detail.artifacts.filter((a) => a.kind === 'direction_cards' || a.title.endsWith('汇总'));

  const stop = async () => {
    try {
      await runsApi.stop(id);
      reload();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '停止失败');
    }
  };
  const cont = async (extra?: number) => {
    try {
      await runsApi.continue(id, extra ? { cost: extra } : {});
      setAddOpen(false);
      reload();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '继续失败');
    }
  };

  return (
    <CwPage>
      <TopBar
        title={run.title}
        sub={
          <span className="cw-runhead">
            <span className="cw-runstatus" style={{ ['--st' as string]: STATUS_COLOR[run.status] }}>
              {STATUS_LABEL[run.status]}
            </span>
            <span className="cw-num">{fmtMs(elapsed)}</span>
            <span className="cw-num">
              {fmtCost(run.cost)}
              {run.budget.cost ? ` / ${fmtCost(run.budget.cost)}` : ''}
            </span>
            {run.parent_run_id ? <Link href={`/runs/${run.parent_run_id}`}>分叉自 #{run.parent_run_id}</Link> : null}
          </span>
        }
      >
        <Link href="/runs" className="cw-link-btn">
          全部运行
        </Link>
        <a className="cw-link-btn" href={runsApi.exportUrl(id, 'md')}>
          导出 Markdown
        </a>
        <a className="cw-link-btn" href={runsApi.exportUrl(id, 'json')}>
          JSON
        </a>
        {run.status === 'paused' ? (
          <Button variant="primary" onClick={() => setAddOpen(true)}>
            追加预算并继续
          </Button>
        ) : null}
        {run.status === 'failed' ? (
          <Button variant="primary" onClick={() => cont()}>
            继续
          </Button>
        ) : null}
        {['queued', 'running', 'waiting', 'paused'].includes(run.status) ? <Button onClick={stop}>停止</Button> : null}
      </TopBar>

      {run.status_reason && run.status !== 'waiting' ? (
        <div className="cw-runreason" data-status={run.status} role="status">
          {run.status_reason}
        </div>
      ) : null}
      {run.status === 'done' && detail.decisions.length ? (
        <div className="cw-runreason" data-status="done" role="status">
          {detail.decisions.map((d) => {
            const c = d.choice || {};
            const label = (c.title as string) || (c.custom as string) || (c.auto ? '关卡已关闭，保留全部方向' : '已选择');
            return (
              <span key={d.id}>
                你的选择：{label}
                {d.note ? `（${d.note}）` : ''}
              </span>
            );
          })}
        </div>
      ) : null}
      {pending ? <GatePanel runId={id} step={pending} onDone={reload} /> : null}

      <div className="cw-tabs" role="tablist">
        {(
          [
            ['graph', '节点图'],
            ['timeline', '时间线'],
            ['trace', '调用树'],
          ] as const
        ).map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
            {l}
          </button>
        ))}
      </div>

      <div className="cw-runview" data-detail={step ? 'true' : undefined}>
        <div className="cw-runview-main">
          {tab === 'graph' ? <RunGraph key={step ? 'side' : 'full'} detail={detail} selected={selected} onSelect={setSelected} /> : null}
          {tab === 'timeline' ? (
            <RunTimeline steps={detail.steps} now={now} onSelect={(s) => setSelected(s.branch ? `${s.node}:${s.branch}` : s.node)} />
          ) : null}
          {tab === 'trace' ? trace ? <TraceTree items={trace} /> : <p className="cw-muted">加载调用树…</p> : null}
          {detail.forks.length ? (
            <p className="cw-muted" style={{ marginTop: 10 }}>
              分叉运行：
              {detail.forks.map((f) => (
                <Link key={f.id} href={`/runs/${f.id}`} style={{ marginRight: 10 }}>
                  #{f.id} 从「{f.fork_node}」重跑（{STATUS_LABEL[f.status]}）
                </Link>
              ))}
            </p>
          ) : null}
        </div>
        {step ? (
          <aside className="cw-runview-side" aria-label="节点详情">
            <button type="button" className="cw-link-btn cw-runview-close" onClick={() => setSelected(null)}>
              关闭
            </button>
            <StepDetailPanel
              key={`${step.id}-${step.status}`}
              runId={id}
              stepId={step.id}
              canFork={!['queued', 'running'].includes(run.status)}
              onForked={(nid) => router.push(`/runs/${nid}`)}
            />
          </aside>
        ) : null}
      </div>

      {finals.length ? (
        <div className="cw-grid-2" style={{ marginTop: 18 }}>
          {finals.map((a) => (
            <Card key={a.id} title={a.title}>
              <ArtifactBody a={a} />
            </Card>
          ))}
        </div>
      ) : null}

      <Modal
        open={addOpen}
        title="追加预算"
        okText="追加并继续"
        cancelText="取消"
        onOk={() => cont(addCost)}
        onCancel={() => setAddOpen(false)}
      >
        <p className="cw-muted">{run.status_reason}</p>
        追加 ¥ <InputNumber min={0.1} max={50} step={0.5} value={addCost} onChange={(v) => setAddCost(Number(v) || 1)} />
      </Modal>
    </CwPage>
  );
}
