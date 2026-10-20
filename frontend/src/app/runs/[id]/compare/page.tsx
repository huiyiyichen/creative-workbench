'use client';

/** 重跑对比（创作工作台设计 7.1）：同一节点在原运行和分叉重跑里的输出并排——文字按段落、列表按项、图片并排。 */

import Link from 'next/link';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { Select, message } from 'antd';
import { Suspense, useEffect, useState } from 'react';
import { CwPage, TopBar } from '@/design/components';
import { EXECUTOR_LABEL, STATUS_LABEL, fmtCost } from '@/design/runs';
import { Diffed } from '@/design/studio-draft';
import { runsApi, type CompareSide, type CompareView } from '@/lib/api/_runs';
import { FIELD_LABEL, changedCount, compareContent, showValue, type CompareRow } from '@/lib/compare';

function label(key: string) {
  return FIELD_LABEL[key] || key;
}

function Side({ side, title }: { side: CompareSide | null; title: string }) {
  if (!side) return <div className="cw-compare-h">{title}：没有可对比的运行</div>;
  const b = side.branches[0];
  const ov = b?.override || {};
  return (
    <div className="cw-compare-h">
      <Link href={`/runs/${side.run.id}`}>#{side.run.id}</Link> {title} · {STATUS_LABEL[side.run.status]}
      {b ? (
        <small className="cw-muted">
          {' '}
          · {EXECUTOR_LABEL[b.step.executor] || b.step.executor}
          {b.step.model ? ` · ${b.step.model}` : ''} · {fmtCost(side.branches.reduce((n, x) => n + (x.step.cost || 0), 0))}
          {b.step.status === 'reused' ? ' · 复用原产物' : ''}
          {ov.prompt_extra ? ` · 追加：${ov.prompt_extra}` : ''}
          {ov.routing_group ? ` · 模型组 ${ov.routing_group}` : ''}
        </small>
      ) : null}
    </div>
  );
}

function Field({ row }: { row: CompareRow }) {
  if (row.kind === 'text') {
    return (
      <>
        <div className="cw-compare-key">{label(row.key)}</div>
        {row.rows.map((r, i) => (
          <div key={i} className="cw-compare-row" data-same={r.same || undefined}>
            <p>{r.left ? (r.right && !r.same ? <Diffed a={r.left.text} b={r.right.text} side="left" /> : r.left.text) : <i className="cw-muted">（无）</i>}</p>
            <p>{r.right ? (r.left && !r.same ? <Diffed a={r.left.text} b={r.right.text} side="right" /> : r.right.text) : <i className="cw-muted">（无）</i>}</p>
          </div>
        ))}
      </>
    );
  }
  if (row.kind === 'image') {
    return (
      <>
        <div className="cw-compare-key">{label(row.key)}</div>
        <div className="cw-compare-row" data-same={row.same || undefined}>
          {[row.left, row.right].map((src, k) => (
            <p key={k}>{src ? <img className="cw-compare-img" src={src} alt={label(row.key)} /> : <i className="cw-muted">（无）</i>}</p>
          ))}
        </div>
      </>
    );
  }
  if (row.kind === 'list') {
    return (
      <>
        <div className="cw-compare-key">
          {label(row.key)} <small className="cw-muted">{row.items.filter((x) => !x.same).length} 项不同</small>
        </div>
        {row.items.map((it) => (
          <div key={it.index} className="cw-compare-row" data-same={it.same || undefined}>
            {(['left', 'right'] as const).map((s) => (
              <div key={s} className="cw-compare-shot">
                <b className="cw-num">第 {it.index + 1} 项</b>
                {it[s] === undefined ? (
                  <i className="cw-muted">（无）</i>
                ) : it.fields.length ? (
                  it.fields.map((f) => (
                    <div key={f.key} data-changed={!f.same || undefined}>
                      <small>{label(f.key)}</small> {showValue((it[s] as Record<string, unknown> | undefined)?.[f.key])}
                    </div>
                  ))
                ) : (
                  <div>{showValue(it[s])}</div>
                )}
              </div>
            ))}
          </div>
        ))}
      </>
    );
  }
  return (
    <>
      <div className="cw-compare-key">{label(row.key)}</div>
      <div className="cw-compare-row" data-same={row.same || undefined}>
        <p className="cw-pre">{showValue(row.left)}</p>
        <p className="cw-pre">{showValue(row.right)}</p>
      </div>
    </>
  );
}

function ComparePage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const id = Number(params.id);
  const node = search.get('node') || '';
  const other = Number(search.get('other')) || undefined;
  const [data, setData] = useState<CompareView | null>(null);
  useEffect(() => {
    if (!node) return;
    runsApi
      .compare(id, node, other)
      .then(setData)
      .catch((err) => message.error(err instanceof Error ? err.message : '加载失败'));
  }, [id, node, other]);
  if (!data) {
    return (
      <CwPage>
        <TopBar title="对比" />
        <p className="cw-muted">{node ? '加载中…' : '缺少节点'}</p>
      </CwPage>
    );
  }
  const left = data.left;
  const right = data.right;
  const stepLabel = right.branches[0]?.step.label || left?.branches[0]?.step.label || node;
  const branchKeys = [...new Set([...(left?.branches || []), ...right.branches].map((b) => b.branch))];
  const sections = branchKeys.map((bk) => {
    const lb = left?.branches.find((b) => b.branch === bk);
    const rb = right.branches.find((b) => b.branch === bk);
    const n = Math.max(lb?.artifacts.length || 0, rb?.artifacts.length || 0);
    const arts = Array.from({ length: n }, (_, i) => {
      const la = lb?.artifacts[i] || null;
      const ra = rb?.artifacts[i] || null;
      const same = Boolean(la && ra && la.id === ra.id);
      return { la, ra, same, rows: compareContent(la?.content || null, ra?.content || null) };
    });
    return { bk, arts };
  });
  const total = sections.reduce((n, s) => n + s.arts.reduce((m, a) => m + (a.same ? 0 : changedCount(a.rows)), 0), 0);
  return (
    <CwPage>
      <TopBar title={`对比 · ${stepLabel}`} sub={<span className="cw-num">{total} 个字段不同</span>}>
        {data.candidates.length > 1 ? (
          <Select
            size="small"
            style={{ minWidth: 260 }}
            value={[left?.run.id, right.run.id].find((x) => x && x !== id)}
            onChange={(v) => router.replace(`/runs/${id}/compare?node=${encodeURIComponent(node)}&other=${v}`)}
            options={data.candidates.map((c) => ({ value: c.id, label: `#${c.id} ${c.fork_node ? `从「${c.fork_node}」重跑` : '原运行'}` }))}
          />
        ) : null}
        <Link className="cw-link-btn" href={`/runs/${id}`}>
          回到运行
        </Link>
      </TopBar>
      <div className="cw-compare cw-compare-page">
        <Side side={left} title={left && left.run.parent_run_id ? '分叉' : '原运行'} />
        <Side side={right} title={right.run.parent_run_id ? '分叉' : '原运行'} />
        {sections.map((s) => (
          <div key={s.bk || '_'} className="cw-compare-section">
            {s.bk ? <div className="cw-compare-branch">分支 {s.bk}</div> : null}
            {s.arts.map((a, i) => (
              <div key={i} className="cw-compare-section">
                <div className="cw-compare-branch">
                  {a.la?.title || a.ra?.title || '产物'}
                  {a.same ? <small className="cw-muted"> · 两边是同一份产物（上游复用）</small> : null}
                </div>
                {a.rows.map((r) => (
                  <Field key={r.key} row={r} />
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    </CwPage>
  );
}

export default function Page() {
  return (
    <Suspense>
      <ComparePage />
    </Suspense>
  );
}
