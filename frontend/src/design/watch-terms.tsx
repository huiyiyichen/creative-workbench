'use client';

/**
 * 追踪词的增删（今日侧栏、热点「追踪词」页共用）：
 * - 添加：输入关键词回车，在全部可搜索平台建一个关键词信源（不立即同步，下一轮采集出数）。
 * - 删除：删掉对应的关键词信源，已采到的内容保留。
 */

import { useState } from 'react';
import { Plus, X } from 'lucide-react';
import { collectionApi } from '@/lib/api/_collection';
import { sourcesApi } from '@/lib/api/_sources';

export async function addWatchTerm(word: string): Promise<void> {
  const w = word.trim();
  if (!w) throw new Error('先输入关键词');
  const rec = await collectionApi.recognize(w);
  const created = await collectionApi.createSource({ ...rec, kind: 'keyword', query: w, name: w, sync_now: false });
  // 建好后立刻在后台搜一轮，不等下一个采集周期；不阻塞界面
  void collectionApi.syncSource(created.id).catch(() => undefined);
}

export async function removeWatchTerm(sourceId: number): Promise<void> {
  await sourcesApi.delete(sourceId);
}

export function WatchTermInput({ onAdded, compact }: { onAdded: (word: string) => void; compact?: boolean }) {
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => {
    if (!value.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await addWatchTerm(value);
      onAdded(value.trim());
      setValue('');
    } catch (e) {
      setErr(e instanceof Error ? e.message : '添加失败');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="cw-term-add" data-compact={compact ? 'true' : undefined}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <input
          className="cw-input"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="输入关键词，回车添加追踪"
          aria-label="新追踪词"
          maxLength={60}
          disabled={busy}
        />
        <button type="submit" className="cw-btn" data-icon="true" disabled={busy || !value.trim()} aria-label="添加追踪词" title="添加追踪词">
          <Plus size={15} aria-hidden />
        </button>
      </form>
      {err ? <small className="cw-term-err">{err}</small> : null}
    </div>
  );
}

export function RemoveTermButton({ sourceId, term, onRemoved }: { sourceId: number; term: string; onRemoved: () => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      className="cw-term-del"
      aria-label={`删除追踪词 ${term}`}
      title="删除追踪词（已采到的内容保留）"
      disabled={busy}
      onClick={async (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!window.confirm(`删除追踪词「${term}」？已采到的内容会保留。`)) return;
        setBusy(true);
        try {
          await removeWatchTerm(sourceId);
          onRemoved();
        } finally {
          setBusy(false);
        }
      }}
    >
      <X size={13} aria-hidden />
    </button>
  );
}
