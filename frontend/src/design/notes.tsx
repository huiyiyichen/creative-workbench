'use client';

/** 随笔组件：输入框（文字、粘贴图片、录音）、正文渲染（#标签、[[双链]]、链接）、任意页面的随手记（Alt+N）。 */

import Link from 'next/link';
import { Input, Modal, message } from 'antd';
import { Mic, PenLine, Square } from 'lucide-react';
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';
import { Button } from '@/design/components';
import { libraryApi, libraryFileUrl, type NoteRelated, type NoteView, type RelatedRef } from '@/lib/api/_library';
import { splitNoteBody } from '@/lib/notes';

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

export function NoteComposer({ onSaved, autoFocus }: { onSaved: (note: NoteView & { related?: NoteRelated }) => void; autoFocus?: boolean }) {
  const [body, setBody] = useState('');
  const [images, setImages] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  const save = async (audio?: Blob) => {
    if (!body.trim() && !images.length && !audio) return;
    setBusy(true);
    try {
      let note: NoteView & { related?: NoteRelated } = await libraryApi.createNote(body.trim() || (audio ? '（录音）' : ''), images);
      if (audio) {
        const withAudio = await libraryApi.noteAudio(note.id, audio);
        if (withAudio.transcript_error) message.warning(withAudio.transcript_error);
        note = { ...withAudio, related: note.related };
      }
      setBody('');
      setImages([]);
      onSaved(note);
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(false);
    }
  };

  const onPaste = async (e: React.ClipboardEvent) => {
    const files = Array.from(e.clipboardData.files || []).filter((f) => f.type.startsWith('image/'));
    if (!files.length) return;
    e.preventDefault();
    for (const f of files) {
      try {
        const it = await libraryApi.noteImage(f);
        setImages((x) => [...x, it.id]);
      } catch (err) {
        message.error(errText(err));
      }
    }
  };

  const toggleRecord = async () => {
    if (recording) {
      recorder.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const r = new MediaRecorder(stream);
      chunks.current = [];
      r.ondataavailable = (ev) => chunks.current.push(ev.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        void save(new Blob(chunks.current, { type: r.mimeType || 'audio/webm' }));
      };
      recorder.current = r;
      r.start();
      setRecording(true);
    } catch (err) {
      message.error(`无法录音：${errText(err)}`);
    }
  };

  return (
    <div className="cw-note-composer">
      <Input.TextArea
        autoFocus={autoFocus}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onPaste={onPaste}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void save();
        }}
        autoSize={{ minRows: 2, maxRows: 10 }}
        placeholder="写一句就存。#标签  [[关联收藏或专题]]  粘贴截图或链接；Ctrl+Enter 保存"
        disabled={busy}
      />
      {images.length ? (
        <div className="cw-note-images">
          {images.map((id) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={id} src={libraryFileUrl(id)} alt="" />
          ))}
        </div>
      ) : null}
      <div className="cw-filters" style={{ margin: '8px 0 0' }}>
        <Button icon={recording ? <Square size={14} /> : <Mic size={14} />} variant={recording ? 'primary' : 'ghost'} onClick={toggleRecord} disabled={busy}>
          {recording ? '停止并保存' : '录音'}
        </Button>
        <span className="cw-grow" />
        <Button variant="primary" onClick={() => save()} disabled={busy || (!body.trim() && !images.length)}>
          {busy ? '保存中…' : '存'}
        </Button>
      </div>
    </div>
  );
}


function refHref(ref: RelatedRef | undefined): string | null {
  if (!ref) return null;
  if (ref.type === 'item') return `/library?open=${ref.id}`;
  if (ref.type === 'dossier') return `/dossiers/${ref.id}`;
  if (ref.type === 'note') return `/notes?focus=${ref.id}`;
  if (ref.type === 'content') return `/items/${ref.id}`;
  return null;
}

/** 正文渲染：#标签可点（筛选），[[双链]] 指向解析到的对象，未解析的显示为虚线 */
export function renderNoteBody(body: string, links: RelatedRef[], onTag?: (tag: string) => void): ReactNode {
  const wikis = links.filter((l) => l.relation === 'wikilink');
  return (
    <p className="cw-note-text">
      {splitNoteBody(body).map((part, i) => {
        if (part.type === 'tag')
          return (
            <button key={i} type="button" className="cw-note-tag" onClick={() => onTag?.(part.value)}>
              #{part.value}
            </button>
          );
        if (part.type === 'wiki') {
          const target = part.value.split('|')[0].split('#')[0].trim();
          const ref = wikis.find((w) => w.title === target) || wikis.find((w) => target && w.title.includes(target));
          const href = refHref(ref);
          return href ? (
            <Link key={i} href={href} className="cw-note-wiki">
              {part.label}
            </Link>
          ) : (
            <span key={i} className="cw-note-wiki" data-missing="true" title="没有找到对应的条目">
              {part.label}
            </span>
          );
        }
        if (part.type === 'url')
          return (
            <a key={i} href={part.value} target="_blank" rel="noreferrer">
              {part.value}
            </a>
          );
        return <Fragment key={i}>{part.value}</Fragment>;
      })}
    </p>
  );
}

/** 任何页面按 Alt+N 或点右下角按钮弹出输入框，写一句就存，不打断当前操作（6.4） */
export function QuickNote() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && (e.key === 'n' || e.key === 'N')) {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  return (
    <>
      <button type="button" className="cw-quick-note" aria-label="记一笔（Alt+N）" title="记一笔（Alt+N）" onClick={() => setOpen(true)}>
        <PenLine size={18} />
      </button>
      <Modal open={open} onCancel={() => setOpen(false)} footer={null} title="记一笔" destroyOnHidden width={560}>
        <NoteComposer
          autoFocus
          onSaved={() => {
            setOpen(false);
            message.success('已存到随笔');
          }}
        />
      </Modal>
    </>
  );
}
