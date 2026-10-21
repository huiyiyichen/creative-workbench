'use client';

/** 测评历史（调色台样式）：最近 30 次测评一行一条，点开看每个模型的结果和评分。 */

import React, { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Card } from '@/design/components';
import { EmptyInstrument, ScanSkeleton, StatusLamp } from '@/design/instrument';
import { modelsApi } from '@/lib/api';
import type { EvalResult, EvalRun } from '@/lib/api';
import { promptTypeLabel } from './_model-eval-utils';

export function HistoryTab() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ results: EvalResult[] } | null>(null);

  useEffect(() => {
    modelsApi
      .listEvalRuns(30)
      .then((res) => setRuns(res.runs))
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);

  const toggle = async (id: string) => {
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    setDetail(null);
    setDetail(await modelsApi.getEvalRun(id));
  };

  if (loading) return <ScanSkeleton height={200} label="读取测评历史" />;
  if (!runs.length) {
    return <EmptyInstrument kind="flat" title="还没有测评记录" reason="在「A/B 测评」里选两个以上模型同题跑一次，结果和评分会留在这里。" />;
  }

  return (
    <Card title="测评历史" extra={<small className="cw-muted cw-num">{runs.length} 次</small>}>
      <ol className="cw-model-rows">
        {runs.map((run) => {
          const open = expanded === run.eval_run_id;
          return (
            <li key={run.eval_run_id} className="cw-eval-run">
              <button type="button" className="cw-eval-run-head" aria-expanded={open} onClick={() => toggle(run.eval_run_id)}>
                {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <b>{promptTypeLabel[run.prompt_type] || run.prompt_type}</b>
                <span className="cw-muted cw-num">{run.model_count} 个模型 · {run.created_at?.slice(0, 16).replace('T', ' ')}</span>
                <span className="cw-grow" />
                <StatusLamp tone={run.fail_count ? 'warn' : 'ok'} label={run.fail_count ? `${run.done_count} 成功 · ${run.fail_count} 失败` : `${run.done_count} 成功`} />
              </button>
              {open ? (
                detail ? (
                  <table className="cw-table">
                    <tbody>
                      {detail.results.map((r) => (
                        <tr key={r.id}>
                          <td>{r.model_name}</td>
                          <td><StatusLamp tone={r.status === 'DONE' ? 'ok' : 'bad'} label={r.status === 'DONE' ? '完成' : '失败'} /></td>
                          <td className="cw-num">{r.duration_ms} ms</td>
                          <td className="cw-num">{r.quality_score ? `人工 ${r.quality_score}/5` : '未评分'}</td>
                          <td className="cw-num cw-muted">{r.auto_score !== null ? `自动 ${r.auto_score}/5` : ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <ScanSkeleton height={60} />
                )
              ) : null}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
