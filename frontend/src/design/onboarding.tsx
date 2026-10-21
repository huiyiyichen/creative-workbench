'use client';

/** 首页「开始使用」三步引导：配模型 → 加信源 → 建项目。三步都完成或点「不再显示」后不再出现。 */

import Link from 'next/link';
import { Check, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Button } from './components';
import { StatusLamp } from './instrument';
import { modelsApi } from '@/lib/api/_models';
import { sourcesApi } from '@/lib/api/_sources';
import { projectsApi } from '@/lib/api/_projects';
import { onboardingSteps, type OnboardingCounts } from '@/lib/onboarding';

const KEY = 'cw.onboarding.dismissed';

export function Onboarding() {
  const [counts, setCounts] = useState<OnboardingCounts | null>(null);
  const [hidden, setHidden] = useState(true);
  useEffect(() => {
    if (typeof window !== 'undefined' && window.localStorage.getItem(KEY) === '1') return;
    setHidden(false);
    Promise.all([
      modelsApi.list().then((r) => r.models.filter((m) => m.enabled).length).catch(() => null),
      sourcesApi.list({ page: 1, page_size: 1, enabled: true }).then((r) => r.total ?? r.items?.length ?? 0).catch(() => null),
      projectsApi.list({}).then((r) => r.items.length).catch(() => null),
    ]).then(([models, sources, projects]) => setCounts({ models, sources, projects }));
  }, []);
  if (hidden || !counts) return null;
  const steps = onboardingSteps(counts);
  if (steps.every((s) => s.done)) return null;
  const dismiss = () => {
    window.localStorage.setItem(KEY, '1');
    setHidden(true);
  };
  const todo = steps.filter((s) => !s.done);
  const next = todo[0];
  return (
    <section className="cw-onboard" aria-label="开始使用">
      <StatusLamp tone="warn" />
      <span className="cw-onboard-lead">
        还差 <b className="cw-num">{todo.length}</b> 步就能用起来
      </span>
      <ol>
        {steps.map((s) => (
          <li key={s.key} data-done={s.done || undefined} title={s.desc}>
            <i>{s.done ? <Check size={11} aria-hidden /> : null}</i>
            {s.title}
          </li>
        ))}
      </ol>
      <span className="cw-grow" />
      <small className="cw-muted cw-onboard-desc">{next.desc}</small>
      <Link className="cw-btn" data-variant="ghost" href={next.href}>
        {next.action}
      </Link>
      <Button variant="ghost" size="icon" aria-label="不再显示" title="不再显示" onClick={dismiss}>
        <X size={14} aria-hidden />
      </Button>
    </section>
  );
}
