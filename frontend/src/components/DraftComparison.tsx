'use client';

import { useMemo } from 'react';
import { diffChars } from 'diff';
import type { StudioDraft } from '@/lib/api';

function draftFields(draft: StudioDraft) {
  const fields = [
    { key: 'title', label: '标题', text: draft.title },
    { key: 'logline', label: '梗概', text: draft.logline },
    { key: 'body', label: '正文 / 旁白 / 视觉方案', text: draft.body },
  ];
  draft.shots.forEach((shot, index) => {
    const prefix = `分镜 ${String(index + 1).padStart(2, '0')}`;
    [
      ['beat', '段落'], ['seconds', '时长'], ['visual', '画面'],
      ['camera', '构图与运动'], ['audio', '声音 / 旁白'],
      ['transition', '衔接'], ['caption', '字幕'], ['prompt', '制作提示词'],
    ].forEach(([key, label]) => {
      const value = shot[key as keyof typeof shot];
      fields.push({ key: `shot:${index}:${key}`, label: `${prefix} · ${label}`, text: String(value ?? '') });
    });
  });
  if (draft.cues.length) {
    fields.push({
      key: 'cues', label: '歌词时间轴',
      text: draft.cues.map((cue) => `${cue.time.toFixed(3)}s  ${cue.text}`).join('\n'),
    });
  }
  return fields;
}

export default function DraftComparison({
  before,
  after,
  beforeLabel = '修改前',
  afterLabel = '当前稿',
}: {
  before: StudioDraft;
  after: StudioDraft;
  beforeLabel?: string;
  afterLabel?: string;
}) {
  const changes = useMemo(() => {
    const oldFields = draftFields(before);
    const newFields = draftFields(after);
    const oldMap = new Map(oldFields.map((field) => [field.key, field]));
    const newMap = new Map(newFields.map((field) => [field.key, field]));
    return [...new Set([...oldMap.keys(), ...newMap.keys()])].flatMap((key) => {
      const oldText = oldMap.get(key)?.text ?? '';
      const newText = newMap.get(key)?.text ?? '';
      if (oldText === newText) return [];
      return [{
        key, label: newMap.get(key)?.label ?? oldMap.get(key)!.label,
        parts: diffChars(oldText, newText),
      }];
    });
  }, [before, after]);

  if (!changes.length) return <div className="py-8 text-center text-sm text-gray-500">内容相同</div>;
  return (
    <div className="max-h-[560px] overflow-y-auto border border-gray-200 bg-white" aria-label="稿件前后对照">
      <div className="sticky top-0 z-10 grid grid-cols-2 border-b border-gray-200 bg-white text-sm font-semibold">
        <div className="border-r border-gray-200 px-4 py-3 text-red-700">{beforeLabel}</div>
        <div className="px-4 py-3 text-green-700">{afterLabel}</div>
      </div>
      {changes.map((change) => (
        <section key={change.key} className="border-b border-gray-200 last:border-b-0">
          <h4 className="bg-gray-50 px-4 py-2 text-xs font-semibold text-gray-600">{change.label}</h4>
          <div className="grid grid-cols-2 text-sm leading-7">
            <div className="min-w-0 border-r border-gray-200 p-4 whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
              {change.parts.filter((part) => !part.added).map((part, index) => part.removed
                ? <del key={index} className="bg-red-100 text-red-800 decoration-red-400">{part.value}</del>
                : <span key={index}>{part.value}</span>)}
            </div>
            <div className="min-w-0 p-4 whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
              {change.parts.filter((part) => !part.removed).map((part, index) => part.added
                ? <ins key={index} className="bg-green-100 text-green-800 no-underline">{part.value}</ins>
                : <span key={index}>{part.value}</span>)}
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
