'use client';

/**
 * A/B 测评（调色台样式）：选 ≥2 个可调用模型 + 一种任务 → 同题跑一遍 → 并排看结果并人工打 1–5 分。
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Play } from 'lucide-react';
import { Button, Card, Segmented } from '@/design/components';
import { EmptyInstrument, StatusLamp } from '@/design/instrument';
import { modelsApi } from '@/lib/api';
import type { EvalResult, LlmModelItem } from '@/lib/api';
import { toast } from '@/design/feedback';

const PROMPT_TYPES = [
  { value: 'analysis', label: '选题分析' },
  { value: 'daily_report', label: 'AI 日报' },
  { value: 'weekly_digest', label: 'AI 周刊' },
  { value: 'classification', label: '内容分类' },
];

export function EvaluateTab({ models }: { models: LlmModelItem[] }) {
  const enabledModels = useMemo(() => models.filter((m) => m.enabled), [models]);
  const runnableModelIds = useMemo(
    () => new Set(enabledModels.filter((m) => m.api_key_set || !m.api_base).map((m) => m.id)),
    [enabledModels],
  );
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [promptType, setPromptType] = useState('analysis');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ eval_run_id: string; results: EvalResult[] } | null>(null);
  const [scoringId, setScoringId] = useState<number | null>(null);

  useEffect(() => {
    setSelected((prev) => new Set([...prev].filter((id) => runnableModelIds.has(id))));
  }, [runnableModelIds]);

  const toggleModel = (id: number) => {
    if (!runnableModelIds.has(id)) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleRun = async () => {
    if (selected.size < 2) {
      toast.warning('至少选择 2 个模型进行对比');
      return;
    }
    setRunning(true);
    setResult(null);
    try {
      const res = await modelsApi.runEvaluation({ model_ids: [...selected], prompt_type: promptType });
      setResult(await modelsApi.getEvalRun(res.eval_run_id));
    } catch (e) {
      toast.error(e, '测评失败');
    }
    setRunning(false);
  };

  const handleScore = async (evalId: number, score: number) => {
    setScoringId(evalId);
    try {
      await modelsApi.scoreEvaluation(evalId, score);
      setResult((cur) => (cur ? { ...cur, results: cur.results.map((r) => (r.id === evalId ? { ...r, quality_score: score } : r)) } : cur));
    } catch (e) {
      toast.error(e, '评分失败');
    } finally {
      setScoringId(null);
    }
  };

  if (runnableModelIds.size < 2) {
    return (
      <EmptyInstrument
        kind="unplugged"
        title="至少要两个能调用的模型"
        reason={`A/B 测评是让几个模型同题对比。现在可调用的只有 ${runnableModelIds.size} 个，在「模型配置」里再加一个并填好 Key。`}
      />
    );
  }

  return (
    <div className="cw-models">
      <Card title="参与对比的模型" extra={<small className="cw-muted cw-num">{selected.size} / {runnableModelIds.size} 已选</small>}>
        <div className="cw-toggles">
          {enabledModels.map((m) => {
            const runnable = runnableModelIds.has(m.id);
            return (
              <button
                key={m.id}
                type="button"
                className="cw-toggle"
                aria-pressed={selected.has(m.id)}
                disabled={!runnable}
                title={runnable ? m.resolved_model : '缺少 API Key，暂不能参与测评'}
                onClick={() => toggleModel(m.id)}
              >
                {m.name}
                {!runnable ? <small>缺 Key</small> : null}
              </button>
            );
          })}
        </div>
      </Card>

      <div className="cw-filters">
        <Segmented label="测评任务" value={promptType} onChange={setPromptType} options={PROMPT_TYPES} />
        <span className="cw-grow" />
        {selected.size < 2 ? <span className="cw-muted">再选 {2 - selected.size} 个模型</span> : null}
        <Button variant="primary" icon={<Play size={14} />} onClick={handleRun} disabled={running || selected.size < 2}>
          {running ? '测评进行中…' : '开始测评'}
        </Button>
      </div>

      {result ? (
        <div className="cw-eval-grid">
          {result.results.map((r) => (
            <Card
              key={r.id}
              title={r.model_name}
              extra={<StatusLamp tone={r.status === 'DONE' ? 'ok' : 'bad'} label={r.status === 'DONE' ? `${r.duration_ms} ms` : '失败'} />}
            >
              {r.status !== 'DONE' ? <p className="cw-model-test" data-tone="bad">{r.error_message}</p> : null}
              {r.tokens_input !== null ? (
                <small className="cw-muted cw-num">Token {r.tokens_input} → {r.tokens_output}{r.auto_score !== null ? ` · 自动评分 ${r.auto_score}/5` : ''}</small>
              ) : null}
              {r.response_text ? <div className="cw-eval-text">{r.response_text}</div> : null}
              <div className="cw-eval-score" role="group" aria-label={`给 ${r.model_name} 打分`}>
                <span className="cw-muted">人工评分</span>
                {[1, 2, 3, 4, 5].map((s) => (
                  <button key={s} type="button" className="cw-toggle" aria-pressed={r.quality_score === s} disabled={scoringId === r.id} onClick={() => handleScore(r.id, s)}>
                    {s}
                  </button>
                ))}
              </div>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
