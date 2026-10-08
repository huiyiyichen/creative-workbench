/**
 * 评分拆解可视化（独立可复用组件）。
 *
 * 从 ContentAnalysisPanel 抽出，供 today-picks 卡片轻量展示评分解释。
 * 输入后端 ScoreBreakdown（见 backend/app/services/scoring_engine.py:104）。
 */
'use client';

import type { ScoreBreakdown as ScoreBreakdownType } from '@/types';

const DIMENSION_LABELS: Record<string, { label: string; weight: number; color: string }> = {
  info_density: { label: '信息密度', weight: 25, color: '#3b82f6' },
  actionability: { label: '可操作性', weight: 20, color: '#8b5cf6' },
  creator_value: { label: '创作者价值', weight: 18, color: '#6366f1' },
  viral_potential: { label: '爆文潜力', weight: 15, color: '#ef4444' },
  source_authority: { label: '来源权威', weight: 12, color: '#f59e0b' },
  freshness: { label: '时效新鲜', weight: 10, color: '#10b981' },
};

export default function ScoreBreakdownChart({
  breakdown,
  sourceAuthorityKnown,
  contentScore,
}: {
  breakdown: ScoreBreakdownType;
  sourceAuthorityKnown?: boolean;
  contentScore?: number | null;
}) {
  const dims = breakdown.dimension_scores || {};
  const qualityFactor = breakdown.quality_factor ?? 1;
  const riskFactor = breakdown.risk_factor ?? 1;
  const personalizationBonus = breakdown.personalization_bonus ?? 0;
  const calculatedScore =
    (breakdown.base_score + breakdown.source_bonus) *
      qualityFactor *
      riskFactor *
      breakdown.time_decay *
      breakdown.diversity_factor +
    personalizationBonus;
  const factors = [
    { label: '来源加权', value: breakdown.source_bonus, max: 20, color: '#f59e0b' },
    { label: '质量系数', value: qualityFactor * 100, max: 100, color: '#10b981', suffix: '%' },
    { label: '风险系数', value: riskFactor * 100, max: 100, color: '#6b7280', suffix: '%' },
    { label: '时效衰减', value: breakdown.time_decay * 100, max: 100, color: '#10b981', suffix: '%' },
    { label: '多样性', value: breakdown.diversity_factor * 100, max: 100, color: '#6366f1', suffix: '%' },
    { label: '兴趣调整', value: personalizationBonus, max: 20, color: '#3b82f6' },
  ];

  return (
    <div>
      {/* 6-dimension weighted contribution bars */}
      <div className="mb-4 flex flex-col gap-2.5">
        {Object.entries(DIMENSION_LABELS).map(([key, meta]) => {
          const raw = dims[key] ?? 0;
          const pct = Math.min(100, (raw / meta.weight) * 100);
          return (
            <div key={key} className="flex items-center gap-2.5">
              <span className="w-[110px] shrink-0 text-right text-xs text-gray-600">
                {meta.label}
                <span className="ml-1 text-[10px] text-gray-400">{meta.weight}%</span>
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded bg-gray-100">
                <div
                  style={{ width: `${pct}%`, background: meta.color }}
                  className="h-full rounded transition-[width] duration-500"
                />
              </div>
              <span className="w-8 text-right font-mono text-[11px] text-gray-500">
                {raw.toFixed(1)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Adjustment factors */}
      <div className="grid grid-cols-3 gap-3 border-y border-gray-100 px-3.5 py-2.5">
        {factors.map((f) => (
          <div key={f.label} className="flex-1 text-center">
            <div className="font-mono text-base font-bold" style={{ color: f.color }}>
              {f.suffix ? `${Math.round(f.value)}${f.suffix}` : (f.value > 0 ? `+${f.value.toFixed(0)}` : f.value.toFixed(0))}
            </div>
            <div className="mt-0.5 text-[10px] text-gray-400">{f.label}</div>
          </div>
        ))}
      </div>

      {/* Final score */}
      <div className="mt-3 flex items-center justify-between rounded-lg bg-primary-light px-4 py-3">
        <span className="text-[13px] font-medium text-gray-600">排序分</span>
        <span className="font-mono text-[22px] font-extrabold text-primary">
          {breakdown.final_score.toFixed(1)}
        </span>
      </div>
      <div className="mt-2 text-xs text-gray-500">
        <div>
          基础分 = {contentScore != null && contentScore > 0
            ? `内容分 ${contentScore.toFixed(1)} × 60% + 六项加权贡献 × 40%`
            : '无内容分时，可用内容均值 × 50% + 六项加权贡献 × 50%'} + 反馈调整
        </div>
        <div className="mt-1">
          本条计算：({breakdown.base_score.toFixed(1)} {breakdown.source_bonus < 0 ? '−' : '+'} {Math.abs(breakdown.source_bonus).toFixed(1)})
          × {qualityFactor.toFixed(2)} × {riskFactor.toFixed(2)} × {breakdown.time_decay.toFixed(3)} × {breakdown.diversity_factor.toFixed(2)}
          {personalizationBonus < 0 ? ' − ' : ' + '}{Math.abs(personalizationBonus).toFixed(1)}
          {' = '}{calculatedScore.toFixed(1)}
        </div>
        <div className="mt-1">
          时效系数 {Math.round(breakdown.time_decay * 100)}% ·
          多样性 {Math.round(breakdown.diversity_factor * 100)}% ·
          兴趣调整 {personalizationBonus >= 0 ? '+' : '−'}{Math.abs(personalizationBonus).toFixed(0)} ·
          反馈调整 {Number(dims.feedback_adjustment ?? 0) >= 0 ? '+' : ''}{Number(dims.feedback_adjustment ?? 0).toFixed(1)}
        </div>
        {sourceAuthorityKnown === false && (
          <div className="mt-1">来源权威暂无单独评分，基础分按中性值 50 计入。</div>
        )}
      </div>
    </div>
  );
}

export { DIMENSION_LABELS };
