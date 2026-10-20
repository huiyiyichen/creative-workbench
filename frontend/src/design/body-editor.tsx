'use client';

/**
 * 正文富文本编辑器（TipTap）。存储仍是纯文本正文（见 lib/md-lite）：每个顶层块一段，
 * 段落序号与后端段落 id 对应，AI 修改范围按选区覆盖到的段落换算。
 * Markdown 快捷输入：「## 」小标题、「- 」列表、「1. 」有序列表、「> 」引用、**加粗**、*斜体*。
 */

import { EditorContent, useEditor, type Editor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Placeholder } from '@tiptap/extension-placeholder';
import { Bold, Heading2, Heading3, Italic, List, ListOrdered, Quote } from 'lucide-react';
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { docToMd, mdToDoc, type PMNode } from '@/lib/md-lite';

export interface BodyEditorHandle {
  /** 在光标处插入：带空行的内容按段落插入，否则插入文字 */
  insert: (md: string) => void;
  /** 光标移到第 index 段开头 */
  focusParagraph: (index: number) => void;
}

/** 选区覆盖到的段落序号（只数非空的顶层块，和 splitParagraphs 一致）；光标在段落里也算。 */
export function selectedParagraphs(editor: Editor): number[] {
  const { from, to } = editor.state.selection;
  const out: number[] = [];
  let idx = -1;
  editor.state.doc.forEach((node, offset) => {
    if (!node.textContent.trim()) return;
    idx += 1;
    const start = offset;
    const end = offset + node.nodeSize;
    if (to >= start && from <= end) out.push(idx);
  });
  return out;
}

function paragraphPos(editor: Editor, index: number): number | null {
  let idx = -1;
  let pos: number | null = null;
  editor.state.doc.forEach((node, offset) => {
    if (pos !== null || !node.textContent.trim()) return;
    idx += 1;
    if (idx === index) pos = offset + 1;
  });
  return pos;
}

export const BodyEditor = forwardRef<
  BodyEditorHandle,
  {
    value: string;
    onChange: (body: string) => void;
    onSelectParagraphs?: (indexes: number[], hasRange: boolean) => void;
    readOnly?: boolean;
    placeholder?: string;
  }
>(function BodyEditor({ value, onChange, onSelectParagraphs, readOnly, placeholder }, ref) {
  const last = useRef(value);
  const cb = useRef({ onChange, onSelectParagraphs });
  useEffect(() => {
    cb.current = { onChange, onSelectParagraphs };
  });
  const editor = useEditor({
    immediatelyRender: false,
    editable: !readOnly,
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        codeBlock: false,
        horizontalRule: false,
        strike: false,
        underline: false,
        link: false,
      }),
      Placeholder.configure({ placeholder: placeholder || '' }),
    ],
    content: mdToDoc(value) as unknown as Record<string, unknown>,
    editorProps: { attributes: { class: 'cw-paper-body cw-rich', 'aria-label': '正文', role: 'textbox', 'aria-multiline': 'true' } },
    onUpdate: ({ editor: ed }) => {
      const md = docToMd(ed.getJSON() as PMNode);
      if (md === last.current) return;
      last.current = md;
      cb.current.onChange(md);
    },
    onSelectionUpdate: ({ editor: ed }) => {
      cb.current.onSelectParagraphs?.(selectedParagraphs(ed), !ed.state.selection.empty);
    },
  });

  // 外部改了正文（采纳建议、回滚版本、重新加载）：同步进编辑器
  useEffect(() => {
    if (!editor || value === last.current) return;
    last.current = value;
    editor.commands.setContent(mdToDoc(value) as unknown as Record<string, unknown>, { emitUpdate: false });
  }, [editor, value]);

  useEffect(() => {
    editor?.setEditable(!readOnly);
  }, [editor, readOnly]);

  useImperativeHandle(
    ref,
    () => ({
      insert(md: string) {
        if (!editor || readOnly) return;
        const text = md.trim();
        if (/\n\s*\n/.test(md)) {
          const nodes = mdToDoc(text).content || [];
          editor.chain().focus().insertContent(nodes as unknown as Record<string, unknown>[]).run();
        } else {
          editor.chain().focus().insertContent(text).run();
        }
      },
      focusParagraph(index: number) {
        if (!editor) return;
        const pos = paragraphPos(editor, index);
        if (pos === null) return;
        editor.chain().focus().setTextSelection(pos).scrollIntoView().run();
      },
    }),
    [editor, readOnly],
  );

  const btn = (label: string, active: boolean, run: () => void, icon: React.ReactNode) => (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      disabled={readOnly}
      onMouseDown={(e) => e.preventDefault()}
      onClick={run}
    >
      {icon}
    </button>
  );
  return (
    <div className="cw-rich-wrap">
      {editor && !readOnly ? (
        <div className="cw-rich-bar" role="toolbar" aria-label="正文格式">
          {btn('小标题', editor.isActive('heading', { level: 2 }), () => editor.chain().focus().toggleHeading({ level: 2 }).run(), <Heading2 size={14} />)}
          {btn('三级标题', editor.isActive('heading', { level: 3 }), () => editor.chain().focus().toggleHeading({ level: 3 }).run(), <Heading3 size={14} />)}
          {btn('加粗', editor.isActive('bold'), () => editor.chain().focus().toggleBold().run(), <Bold size={14} />)}
          {btn('斜体', editor.isActive('italic'), () => editor.chain().focus().toggleItalic().run(), <Italic size={14} />)}
          {btn('列表', editor.isActive('bulletList'), () => editor.chain().focus().toggleBulletList().run(), <List size={14} />)}
          {btn('有序列表', editor.isActive('orderedList'), () => editor.chain().focus().toggleOrderedList().run(), <ListOrdered size={14} />)}
          {btn('引用', editor.isActive('blockquote'), () => editor.chain().focus().toggleBlockquote().run(), <Quote size={14} />)}
        </div>
      ) : null}
      <EditorContent editor={editor} />
    </div>
  );
});
