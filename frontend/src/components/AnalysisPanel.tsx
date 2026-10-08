'use client';

import React from 'react';
import { ArrowRight, Film, PenLine, X } from 'lucide-react';
import { Button, Panel } from '@/components/ui';
import type { ContentAnalysis } from '@/types';
import RelationPanel from '@/components/RelationPanel';
import EvidencePanel from '@/components/EvidencePanel';
import { useDialogFocus } from '@/components/useDialogFocus';
import ScoreBreakdownChart from '@/components/ScoreBreakdownChart';
import { explainRecommendation } from '@/lib/recommendation';

interface AnalysisPanelProps {
  analysis: ContentAnalysis & { _content_id?: number };
  onClose: () => void;
}

export default function AnalysisPanel({ analysis, onClose }: AnalysisPanelProps) {
  const { dialogRef, onKeyDown } = useDialogFocus<HTMLDivElement>(true, onClose);
  const contentId = analysis.content_id || analysis._content_id || 0;
  const decision = explainRecommendation(analysis);

  return (
    <>
      <div onClick={onClose} className="fixed inset-0 z-[999] bg-black/20" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="analysis-panel-title"
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className="fixed bottom-0 right-0 top-0 z-[1000] w-[520px] max-w-[90vw] overflow-y-auto bg-white p-8 shadow-[-4px_0_24px_rgba(0,0,0,0.1)]"
      >
        <div className="mb-6 flex items-center justify-between">
          <h2 id="analysis-panel-title" className="text-lg font-bold text-gray-900">AI 分析报告</h2>
          <button type="button" onClick={onClose} className="cursor-pointer border-0 bg-transparent p-1 text-gray-400 hover:text-gray-600" title="关闭" aria-label="关闭分析报告">
            <X size={18} strokeWidth={2} />
          </button>
        </div>

        {analysis.score_breakdown && <div className="mb-6">
          <h3 className="mb-3 text-[13px] font-semibold text-gray-700">排序依据</h3>
          <ScoreBreakdownChart
            breakdown={analysis.score_breakdown}
            sourceAuthorityKnown={analysis.source_weight != null}
            contentScore={analysis.curation_score}
          />
        </div>}
        <div className="mb-6">
          <h3 className="mb-2 text-[13px] font-semibold text-gray-700">写作建议 · {decision.level}</h3>
          <p className="text-xs leading-6 text-gray-600">{decision.reason}</p>
        </div>
        <div className="mb-6">
          <h3 className="mb-3 text-[13px] font-semibold text-gray-700">AI 内容评分</h3>
          {[
            { label: '内容分', value: analysis.curation_score, color: 'var(--color-primary)' },
            { label: '信息密度', value: analysis.info_density || 0, color: '#8B5CF6' },
            { label: '可操作性', value: analysis.actionability || 0, color: '#3B82F6' },
            { label: '来源权威', value: analysis.source_weight, color: '#10B981' },
          ].map((s) => (
            <div key={s.label} className="mb-2 flex items-center gap-2.5">
              <span className="w-16 text-xs text-gray-500">{s.label}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100">
                <div className="h-full rounded-full" style={{ width: `${s.value}%`, background: s.color }} />
              </div>
              <span className="w-8 text-right text-xs font-semibold text-gray-700">{s.value == null ? '未知' : Math.round(s.value)}</span>
            </div>
          ))}
        </div>

        <div className="mb-6">
          <h3 className="mb-3 text-[13px] font-semibold text-gray-700">多维评分</h3>
          {[
            { label: '质量', value: analysis.quality_score, color: '#10B981' },
            { label: '热度', value: analysis.hot_score, color: '#EF4444' },
            { label: '新鲜度', value: analysis.freshness_score, color: '#3B82F6' },
            { label: '创作价值', value: analysis.creator_score, color: 'var(--color-primary)' },
            { label: '爆文潜力', value: analysis.viral_score, color: '#F59E0B' },
            { label: '风险', value: analysis.risk_score, color: '#6B7280' },
          ].map((s) => (
            <div key={s.label} className="mb-2 flex items-center gap-2.5">
              <span className="w-16 text-xs text-gray-500">{s.label}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-100">
                <div className="h-full rounded-full" style={{ width: `${s.value}%`, background: s.color }} />
              </div>
              <span className="w-6 text-right text-xs font-semibold text-gray-700">{Math.round(s.value || 0)}</span>
            </div>
          ))}
        </div>

        {analysis.summary && (
          <div className="mb-6">
            <h3 className="mb-2 text-[13px] font-semibold text-gray-700">内容摘要</h3>
            <p className="text-[13px] leading-7 text-gray-600">{analysis.summary}</p>
          </div>
        )}
        {analysis.key_points != null && analysis.key_points.length > 0 && (
          <div className="mb-6">
            <h3 className="mb-2 text-[13px] font-semibold text-gray-700">核心观点</h3>
            {analysis.key_points.map((point, i) => (
              <div key={i} className="mb-2 border-l-[3px] border-primary pl-3">
                <span className="text-[13px] leading-6 text-gray-600">{point}</span>
              </div>
            ))}
          </div>
        )}
        {analysis.creator_angles != null && analysis.creator_angles.length > 0 && (
          <div className="mb-6">
            <h3 className="mb-2 text-[13px] font-semibold text-gray-700">创作角度</h3>
            {analysis.creator_angles.map((angle, i) => (
              <div key={i} className="mb-2 border-l-[3px] border-teal pl-3">
                <span className="text-[13px] leading-6 text-gray-600">{angle}</span>
              </div>
            ))}
          </div>
        )}
        {analysis.title_suggestions != null && analysis.title_suggestions.length > 0 && (
          <div className="mb-6">
            <h3 className="mb-2 text-[13px] font-semibold text-gray-700">建议标题</h3>
            {analysis.title_suggestions.map((title, i) => (
              <div key={i} className="mb-1.5 text-[13px] leading-7 text-gray-600">
                <span className="font-semibold text-primary">{i + 1}.</span> {title}
              </div>
            ))}
          </div>
        )}

        {contentId > 0 && (
          <Panel className="mt-7 border-primary-border/60 bg-primary-light/40 p-5">
            <h3 className="mb-1 flex items-center gap-2 text-sm font-bold text-gray-900">
              <PenLine size={15} strokeWidth={2} />
              进入创作工作台
            </h3>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs text-gray-600"><Film size={15} />模板、视觉风格、分镜和成片统一管理</div>
              <Button type="button" variant="primary" onClick={() => { window.location.href = `/studio?content_id=${contentId}`; }}>
                打开
                <ArrowRight size={14} />
              </Button>
            </div>
          </Panel>
        )}

        {/* Cross-source evidence */}
        {contentId > 0 && (
          <EvidencePanel contentId={contentId} />
        )}

        {/* Related content */}
        {contentId > 0 && (
          <RelationPanel contentId={contentId} />
        )}
      </div>
    </>
  );
}
