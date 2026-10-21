'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  BarChart3,
  Beaker,
  FlaskConical,
  History,
  RefreshCw,
  Settings2,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button as CwButton, Segmented } from '@/design/components';
import { Readout, Readouts } from '@/design/instrument';
import { LoadingState } from '@/components/StateView';
import { AdminPageShell } from '@/components/admin-ui';
import { modelsApi } from '@/lib/api';
import type {
  LlmModelItem,
  ModelUsageSummary,
} from '@/lib/api';
import {
  type Tab,
  formatTokens,
  formatCurrency,
} from './_model-eval-utils';
import { Surface } from './_components';
import { ModelsTab } from './ModelsTab';
import { EvaluateTab } from './EvaluateTab';
import { UsageTab } from './UsageTab';
import { HistoryTab } from './HistoryTab';

export default function ModelEvalPage() {
  const [tab, setTab] = useState<Tab>('models');
  const [models, setModels] = useState<LlmModelItem[]>([]);
  const [usage, setUsage] = useState<ModelUsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [usageLoading, setUsageLoading] = useState(true);

  const fetchModels = useCallback(async () => {
    try {
      const res = await modelsApi.list();
      setModels(res.models);
    } catch (e) {
      console.error('fetchModels', e);
    }
    setLoading(false);
  }, []);

  const fetchUsage = useCallback(async () => {
    try {
      setUsageLoading(true);
      const res = await modelsApi.usageSummary(30);
      setUsage(res);
    } catch (e) {
      console.error('fetchUsage', e);
    }
    setUsageLoading(false);
  }, []);

  const refreshAll = useCallback(() => {
    void fetchModels();
    void fetchUsage();
  }, [fetchModels, fetchUsage]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const enabledCount = models.filter((m) => m.enabled).length;
  const runnableCount = models.filter((m) => m.enabled && (m.api_key_set || !m.api_base)).length;
  const routeGroups = new Set(models.map((m) => m.routing_group || 'default')).size;
  const firstRouteModel = [...models]
    .filter((m) => m.enabled)
    .sort((a, b) => (a.routing_group || 'default').localeCompare(b.routing_group || 'default') || a.routing_priority - b.routing_priority || a.id - b.id)[0];

  const tabs: Array<{ key: Tab; label: string; desc: string; icon: LucideIcon }> = [
    { key: 'models', label: '模型配置', desc: '路由链、密钥和限流参数', icon: Settings2 },
    { key: 'evaluate', label: 'A/B 测评', desc: '多模型同题测试并人工评分', icon: FlaskConical },
    { key: 'usage', label: '用量统计', desc: 'Token 消耗和费用预估', icon: BarChart3 },
    { key: 'history', label: '测评历史', desc: '查看历史运行与评分记录', icon: History },
  ];

  return (
    <AdminPageShell maxWidth={1480}>
      {/* 页头读数：没有模型时不摆一排 0（评审 #3 2.6），只留下面那台未接线的仪器 */}
      <div className="cw-admin-head" style={{ marginBottom: 14 }}>
        <h2 className="cw-sr-only">AI 模型与配音</h2>
        <Segmented<Tab>
          label="模型分页"
          value={tab}
          onChange={setTab}
          options={tabs.filter((t) => models.length || t.key === 'models').map((t) => ({ value: t.key, label: t.label }))}
        />
        <CwButton variant="ghost" icon={<RefreshCw size={14} />} onClick={refreshAll}>
          刷新
        </CwButton>
      </div>
      {models.length ? (
        <Readouts>
          <Readout label="模型" value="0" count={models.length} sub={`${enabledCount} 个启用 · ${runnableCount} 个可调用`} />
          <Readout label="路由组" value="0" count={routeGroups} sub={firstRouteModel ? `首选 ${firstRouteModel.name}` : '未设置首选'} />
          <Readout label="30 天 Token" value={usage ? formatTokens(usage.total.tokens_total) : '—'} sub={usage ? `${usage.total.calls} 次调用` : undefined} />
          {usage && usage.total.estimated_cost > 0 ? <Readout label="费用预估" value={formatCurrency(usage.total.estimated_cost)} sub="近 30 天" /> : null}
        </Readouts>
      ) : null}

      {loading ? (
        <Surface title="加载状态" icon={Beaker}>
          <LoadingState minHeight="220px" />
        </Surface>
      ) : (
        <>
          {tab === 'models' && <ModelsTab models={models} onRefresh={refreshAll} />}
          {tab === 'evaluate' && <EvaluateTab models={models} />}
          {tab === 'usage' && <UsageTab usage={usage} loading={usageLoading} onRefresh={fetchUsage} />}
          {tab === 'history' && <HistoryTab />}
        </>
      )}
    </AdminPageShell>
  );
}


