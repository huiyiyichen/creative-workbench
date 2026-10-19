'use client';

/**
 * 设置 · 评分说明（原算法流程页，11.2）：分析漏斗怎么走、初筛权重与各环节阈值（可调）、
 * 结论规则、话题状态阈值，以及近 30 天结论与你的标记、收藏的一致率（4.3）。
 */

import { InputNumber, message } from 'antd';
import { useEffect, useState } from 'react';
import { Button, Card } from '@/design/components';
import { discoverApi, type ScoringSettings } from '@/lib/api/_discover';
import { percent } from '@/lib/discover';

type Group = 'triage_weights' | 'verdict_rules' | 'status_rules';

const LABELS: Record<Group, Record<string, string>> = {
  triage_weights: {
    engagement: '平台指标',
    rank: '上榜排名',
    source_value: '信源历史价值',
    keyword: '命中追踪词',
    freshness: '新鲜度',
    coverage: '覆盖平台数',
    similarity: '与收藏的相似度',
  },
  verdict_rules: {
    worth_points: '值得做：依据得分 ≥',
    watch_points: '观察：依据得分 ≥',
    stale_days: '发布超过 N 天最多「观察」',
    fresh_hours: '时机好：发布 N 小时内',
    growth_ratio: '升温：观测期增长比例 ≥',
    coverage_platforms: '同题：同一事件平台数 ≥',
    event_members: '同题：同一事件条数 ≥',
    quality_good: '内容质量加分线',
  },
  status_rules: {
    new_hours: '新出现：首次出现不足 N 小时',
    rising_ratio: '升温：近 24h 比前 24h 增长 ≥',
    cooling_ratio: '降温：比峰值下降 ≥',
    steady_days: '持续：连续 N 天有信号',
  },
};

const TITLES: Record<Group, string> = {
  triage_weights: '免费初筛权重（缺失的信号不参与加权）',
  verdict_rules: '选题结论规则（风险分 ≥70 或命中敏感规则直接跳过）',
  status_rules: '话题状态阈值（每小时计算）',
};

const FUNNEL = [
  ['采到', '去重'],
  ['规则预筛', '视频按「标题 + 描述 + 字幕」总长度判断，不花钱'],
  ['免费初筛', '平台指标与增速、排名、覆盖平台数、信源价值、追踪词、与收藏相似度、新鲜度加权，不花钱'],
  ['事件归并', '本地向量，同一事件只有代表进入后续分析，其他条目继承结果'],
  ['快速判断', '便宜模型只看标题和摘要，20 条一批'],
  ['完整分析', '受每日预算约束；点开详情、收藏、用作项目来源时按需补分析'],
  ['结论', '按依据规则计算，不调用模型'],
];

export default function ScoringSettingsPage() {
  const [data, setData] = useState<ScoringSettings | null>(null);
  const [draft, setDraft] = useState<Record<Group, Record<string, number>>>({ triage_weights: {}, verdict_rules: {}, status_rules: {} });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    discoverApi
      .scoring()
      .then((d) => {
        setData(d);
        setDraft({ triage_weights: d.triage_weights.values, verdict_rules: d.verdict_rules.values, status_rules: d.status_rules.values });
      })
      .catch((err) => message.error(err instanceof Error ? err.message : '请求失败'));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await discoverApi.saveScoring(draft);
      message.success('已保存，下一轮计算生效');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '请求失败');
    } finally {
      setSaving(false);
    }
  };

  if (!data) return <div className="cw-muted">加载中…</div>;
  const a = data.agreement;
  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 1080 }}>
      <Card title="近 30 天一致率" extra={<small className="cw-muted">结论与你的「不对」、收藏是否一致</small>}>
        <div className="cw-mini-kpis" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
          <div>
            你标记过 <b className="cw-num">{a.marks}</b>
          </div>
          <div>
            改过结论 <b className="cw-num">{a.corrected}</b>
          </div>
          <div>
            标记一致率 <b className="cw-num">{percent(a.mark_agreement)}</b>
          </div>
          <div>
            收藏中「值得做」 <b className="cw-num">{a.favorites ? `${a.favorites_worth}/${a.favorites}` : '—'}</b>
          </div>
        </div>
      </Card>
      <Card title="分析漏斗">
        <ol className="cw-journey" style={{ marginLeft: 6 }}>
          {FUNNEL.map(([k, v]) => (
            <li key={k} style={{ gridTemplateColumns: '80px 1fr' }}>
              <span className="cw-journey-stage">{k}</span>
              <span>{v}</span>
            </li>
          ))}
        </ol>
      </Card>
      {(Object.keys(TITLES) as Group[]).map((g) => (
        <Card key={g} title={TITLES[g]}>
          <div className="cw-settings-grid">
            {Object.keys(LABELS[g]).map((k) => (
              <label key={k}>
                {LABELS[g][k]}
                <InputNumber
                  min={0}
                  step={g === 'triage_weights' || k.endsWith('ratio') ? 0.05 : 1}
                  value={draft[g][k]}
                  onChange={(v) => setDraft((d) => ({ ...d, [g]: { ...d[g], [k]: Number(v ?? 0) } }))}
                  style={{ width: '100%' }}
                />
                <small className="cw-muted">默认 {data[g].defaults[k]}</small>
              </label>
            ))}
          </div>
        </Card>
      ))}
      <div>
        <Button variant="primary" onClick={save} disabled={saving}>
          {saving ? '保存中…' : '保存'}
        </Button>
      </div>
    </div>
  );
}
