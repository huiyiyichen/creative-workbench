'use client';

/**
 * 用量统计（调色台样式）：一排读数（费用 / 缓存命中 / 成功率 / 平均耗时），
 * 下面两张表：按模型、按任务类型，各带一条相对占比的细条。
 */

import React from 'react';
import { RefreshCw } from 'lucide-react';
import { Button, Card } from '@/design/components';
import { EmptyInstrument, Readout, Readouts, ScanSkeleton } from '@/design/instrument';
import type { ModelUsageSummary } from '@/lib/api';
import { formatCurrency, formatTokens, promptTypeLabel } from './_model-eval-utils';

function Meter({ ratio }: { ratio: number }) {
  return (
    <div className="cw-meter" aria-hidden>
      <i style={{ width: `${Math.max(3, Math.round(ratio * 100))}%` }} />
    </div>
  );
}

export function UsageTab({
  usage,
  loading,
  onRefresh,
}: {
  usage: ModelUsageSummary | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  if (loading) return <ScanSkeleton height={220} label="读取用量" />;
  if (!usage || usage.total.calls === 0) {
    return (
      <EmptyInstrument
        kind="flat"
        title="近 30 天还没有模型调用"
        reason="写稿、改写、日报等任务跑过之后，这里会按模型和任务类型列出 Token 和费用。"
        actions={
          <Button icon={<RefreshCw size={14} />} onClick={onRefresh}>
            刷新
          </Button>
        }
      />
    );
  }

  const t = usage.total;
  const maxModel = Math.max(...usage.by_model.map((i) => i.tokens_input + i.tokens_output), 1);
  const maxPrompt = Math.max(...usage.by_prompt.map((i) => i.estimated_cost), 0.000001);

  return (
    <div className="cw-models">
      <Readouts>
        <Readout label="费用预估" value={formatCurrency(t.estimated_cost)} sub="按模型单价估算" />
        <Readout label="缓存命中" value={formatTokens(t.cache_read_tokens)} sub={`实际计费输入 ${formatTokens(t.billable_input_tokens)}`} />
        <Readout label="成功率" value={`${(t.success_rate * 100).toFixed(1)}%`} sub={`${t.success_calls} 成功 · ${t.failed_calls} 失败`} />
        <Readout label="平均耗时" value={`${t.avg_duration_ms} ms`} sub={`自 ${usage.since.slice(0, 10)} 起`} />
      </Readouts>

      <Card title="按模型" extra={<Button variant="ghost" icon={<RefreshCw size={14} />} onClick={onRefresh}>刷新</Button>}>
        <table className="cw-table">
          <thead>
            <tr>
              <th>模型</th>
              <th>调用</th>
              <th>输入</th>
              <th>输出</th>
              <th>平均耗时</th>
              <th>费用</th>
              <th style={{ width: '22%' }}>Token 占比</th>
            </tr>
          </thead>
          <tbody>
            {usage.by_model.map((i) => (
              <tr key={i.model_id ?? i.model_name}>
                <td>
                  {i.model_name}
                  <small className="cw-muted" style={{ display: 'block' }}>{i.provider || '未知接口'}</small>
                </td>
                <td className="cw-num">
                  {i.calls}
                  {i.failed_calls ? <small style={{ color: 'var(--cw-rd)' }}> · {i.failed_calls} 失败</small> : null}
                </td>
                <td className="cw-num">{formatTokens(i.tokens_input)}</td>
                <td className="cw-num">{formatTokens(i.tokens_output)}</td>
                <td className="cw-num">{i.avg_duration_ms} ms</td>
                <td className="cw-num">{formatCurrency(i.estimated_cost)}</td>
                <td><Meter ratio={(i.tokens_input + i.tokens_output) / maxModel} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="按任务类型" extra={<small className="cw-muted">{usage.by_prompt.length} 类</small>}>
        {usage.by_prompt.length ? (
          <table className="cw-table">
            <thead>
              <tr>
                <th>任务</th>
                <th>调用</th>
                <th>Token</th>
                <th>费用</th>
                <th style={{ width: '30%' }}>费用占比</th>
              </tr>
            </thead>
            <tbody>
              {usage.by_prompt.map((i) => (
                <tr key={i.prompt_type}>
                  <td>{promptTypeLabel[i.prompt_type] || i.prompt_type}</td>
                  <td className="cw-num">{i.calls}</td>
                  <td className="cw-num">{formatTokens(i.tokens_input + i.tokens_output)}</td>
                  <td className="cw-num">{formatCurrency(i.estimated_cost)}</td>
                  <td><Meter ratio={i.estimated_cost / maxPrompt} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="cw-muted">还没有按任务归类的调用。</p>
        )}
      </Card>
    </div>
  );
}
