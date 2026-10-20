'use client';

/**
 * 风格与模板（6.6）：内置与自定义并列；版本不可改，保存即新版本；编辑内置的会复制成自定义；
 * 自定义的可以归档。地址 ?style=key / ?template=key 直接打开某一项。
 */

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Input, message } from 'antd';
import { Copy, Plus } from 'lucide-react';
import { Suspense, useCallback, useEffect, useState } from 'react';
import { Button, Card, CwPage, Segmented, TopBar } from '@/design/components';
import { libraryApi, type StyleEntry, type StyleVersion, type TemplateVersion } from '@/lib/api/_library';

type Kind = 'style' | 'template';
type Entry = StyleEntry<StyleVersion> | StyleEntry<TemplateVersion>;

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

interface Draft {
  name: string;
  palette: string;
  layout_rules: string;
  motion_rules: string;
  purpose: string;
  audience: string;
  tone: string;
  structure: string;
  note: string;
}

const EMPTY: Draft = { name: '', palette: '', layout_rules: '', motion_rules: '', purpose: '', audience: '', tone: '', structure: '', note: '' };

function toDraft(kind: Kind, e: Entry): Draft {
  if (kind === 'style') {
    const v = (e as StyleEntry<StyleVersion>).current;
    return {
      ...EMPTY,
      name: e.name,
      palette: (v?.palette || []).map((p) => (p.name ? `${p.name} ${p.hex}` : p.hex)).join('\n'),
      layout_rules: v?.layout_rules || '',
      motion_rules: v?.motion_rules || '',
      note: v?.note || '',
    };
  }
  const v = (e as StyleEntry<TemplateVersion>).current;
  return {
    ...EMPTY,
    name: e.name,
    purpose: v?.purpose || '',
    audience: v?.audience || '',
    tone: v?.tone || '',
    structure: (v?.structure || []).map((s) => (s.points?.length ? `${s.title}：${s.points.join('；')}` : s.title)).join('\n'),
    note: v?.note || '',
  };
}

/** 草稿 → 接口载荷。配色每行「名称 #hex」或「#hex」；结构每行「段落：要点；要点」 */
function draftPayload(kind: Kind, d: Draft): Record<string, unknown> & { name: string } {
  const lines = (s: string) => s.split('\n').map((l) => l.trim()).filter(Boolean);
  if (kind === 'style') {
    const palette = lines(d.palette)
      .map((l) => {
        const m = l.match(/#[0-9a-fA-F]{3,8}/);
        if (!m) return null;
        const name = l.replace(m[0], '').trim();
        return name ? { name, hex: m[0].toLowerCase() } : { hex: m[0].toLowerCase() };
      })
      .filter(Boolean);
    return { name: d.name.trim(), palette, layout_rules: d.layout_rules || null, motion_rules: d.motion_rules || null, note: d.note || null };
  }
  const structure = lines(d.structure).map((l) => {
    const [title, rest] = l.split(/[:：]/, 2);
    return rest ? { title: title.trim(), points: rest.split(/[;；]/).map((p) => p.trim()).filter(Boolean) } : { title: title.trim() };
  });
  return { name: d.name.trim(), purpose: d.purpose || null, audience: d.audience || null, tone: d.tone || null, structure, note: d.note || null };
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'block', margin: '0 0 12px' }}>
      <div className="cw-muted" style={{ fontSize: 12, marginBottom: 4 }}>
        {label}
      </div>
      {children}
    </label>
  );
}

function StylesPage() {
  const router = useRouter();
  const params = useSearchParams();
  const kind: Kind = params.get('template') || params.get('kind') === 'template' ? 'template' : 'style';
  const selectedKey = params.get(kind) || '';
  const [list, setList] = useState<Entry[] | null>(null);
  const [detail, setDetail] = useState<Entry | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = kind === 'style' ? await libraryApi.styles() : await libraryApi.templates();
      setList(r.items);
    } catch (err) {
      message.error(errText(err));
      setList([]);
    }
  }, [kind]);

  useEffect(() => {
    setList(null);
    void load();
  }, [load]);

  useEffect(() => {
    setDraft(null);
    if (!selectedKey) {
      setDetail(null);
      return;
    }
    (kind === 'style' ? libraryApi.style(selectedKey) : libraryApi.template(selectedKey)).then(setDetail).catch((err) => message.error(errText(err)));
  }, [kind, selectedKey]);

  const open = (k: Kind, key?: string) => router.replace(key ? `/library/styles?${k}=${encodeURIComponent(key)}` : `/library/styles?kind=${k}`);

  async function save() {
    if (!draft || !draft.name.trim()) return message.warning('请填写名称');
    setBusy(true);
    try {
      const payload = draftPayload(kind, draft);
      const r = detail ? await libraryApi.addVersion(kind, detail.key, payload) : await libraryApi.create(kind, payload);
      message.success(detail?.builtin ? '内置项已复制为自定义并保存' : detail ? `已保存为 v${r.current_version}` : '已创建');
      setDraft(null);
      await load();
      if (r.key === selectedKey) {
        setDetail(await (kind === 'style' ? libraryApi.style(r.key) : libraryApi.template(r.key)));
      } else open(kind, r.key);
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!detail) return;
    try {
      const r = await libraryApi.copy(kind, detail.key);
      await load();
      open(kind, r.key);
    } catch (err) {
      message.error(errText(err));
    }
  }

  async function archive() {
    if (!detail) return;
    try {
      await libraryApi.archive(kind, detail.key);
      message.success('已归档');
      await load();
      open(kind);
    } catch (err) {
      message.error(errText(err));
    }
  }

  const set = (k: keyof Draft) => (e: { target: { value: string } }) => setDraft((d) => (d ? { ...d, [k]: e.target.value } : d));
  const style = kind === 'style' ? (detail as StyleEntry<StyleVersion> | null) : null;
  const tpl = kind === 'template' ? (detail as StyleEntry<TemplateVersion> | null) : null;

  return (
    <CwPage>
      <TopBar title="风格与模板" sub={<Link href="/library">← 灵感库</Link>}>
        <Segmented<Kind>
          label="类别"
          value={kind}
          onChange={(v) => open(v)}
          options={[
            { value: 'style', label: '视觉风格' },
            { value: 'template', label: '内容模板' },
          ]}
        />
        <Button icon={<Plus size={14} />} onClick={() => { open(kind); setDraft({ ...EMPTY }); }}>
          新建
        </Button>
      </TopBar>
      <div className="cw-style-list">
        <nav aria-label={kind === 'style' ? '视觉风格' : '内容模板'}>
          {!list ? <div className="cw-muted">加载中…</div> : null}
          {list?.map((e) => (
            <button key={e.key} type="button" aria-current={e.key === selectedKey ? 'true' : undefined} onClick={() => open(kind, e.key)}>
              {kind === 'style' ? (
                <span className="cw-lib-swatches-inline">
                  {((e as StyleEntry<StyleVersion>).current?.palette || []).slice(0, 4).map((p, i) => (
                    <i key={i} style={{ background: p.hex }} />
                  ))}
                </span>
              ) : null}
              <span>{e.name}</span>
              <small>{e.builtin ? '内置' : `v${e.current_version}`}</small>
            </button>
          ))}
          {list && list.length === 0 ? <div className="cw-muted">还没有</div> : null}
        </nav>
        <section>
          {draft ? (
            <Card title={detail ? (detail.builtin ? `编辑「${detail.name}」（将复制为自定义）` : `编辑「${detail.name}」· 保存为 v${detail.current_version + 1}`) : '新建'}>
              <Field label="名称">
                <Input value={draft.name} onChange={set('name')} />
              </Field>
              {kind === 'style' ? (
                <>
                  <Field label="配色（每行一个：名称 #hex）">
                    <Input.TextArea value={draft.palette} onChange={set('palette')} autoSize={{ minRows: 3 }} />
                  </Field>
                  <Field label="排版规则">
                    <Input.TextArea value={draft.layout_rules} onChange={set('layout_rules')} autoSize={{ minRows: 3 }} />
                  </Field>
                  <Field label="动效规则">
                    <Input.TextArea value={draft.motion_rules} onChange={set('motion_rules')} autoSize={{ minRows: 2 }} />
                  </Field>
                </>
              ) : (
                <>
                  <Field label="用途">
                    <Input value={draft.purpose} onChange={set('purpose')} />
                  </Field>
                  <Field label="受众">
                    <Input value={draft.audience} onChange={set('audience')} />
                  </Field>
                  <Field label="语气">
                    <Input value={draft.tone} onChange={set('tone')} />
                  </Field>
                  <Field label="结构（每行一段：段落：要点；要点）">
                    <Input.TextArea value={draft.structure} onChange={set('structure')} autoSize={{ minRows: 4 }} />
                  </Field>
                </>
              )}
              <Field label="备注">
                <Input.TextArea value={draft.note} onChange={set('note')} autoSize={{ minRows: 2 }} />
              </Field>
              <div className="cw-row">
                <Button variant="primary" onClick={save} disabled={busy}>
                  {busy ? '保存中…' : '保存'}
                </Button>
                <Button variant="ghost" onClick={() => setDraft(null)}>
                  取消
                </Button>
              </div>
            </Card>
          ) : detail ? (
            <Card
              title={`${detail.name}${detail.builtin ? ' · 内置' : ` · v${detail.current_version}`}`}
              extra={
                <span className="cw-row">
                  <Button onClick={() => setDraft(toDraft(kind, detail))}>
                    编辑
                  </Button>
                  <Button icon={<Copy size={13} />} onClick={copy}>
                    复制
                  </Button>
                  {!detail.builtin ? (
                    <Button variant="ghost" onClick={archive}>
                      归档
                    </Button>
                  ) : null}
                </span>
              }
            >
              {style?.current ? (
                <>
                  <div className="cw-lib-swatches" style={{ display: 'flex', borderRadius: 6, overflow: 'hidden', margin: '0 0 12px' }}>
                    {style.current.palette.map((p, i) => (
                      <div key={i} style={{ background: p.hex, minHeight: 64, flex: 1 }} title={`${p.name || ''} ${p.hex}`} />
                    ))}
                  </div>
                  <p className="cw-muted cw-num">{style.current.palette.map((p) => `${p.name ? `${p.name} ` : ''}${p.hex}`).join(' · ')}</p>
                  {style.current.fonts.length ? <p>字体：{style.current.fonts.map((f) => `${f.role ? `${f.role} ` : ''}${f.family || ''}`).join('，')}</p> : null}
                  {style.current.layout_rules ? <p style={{ whiteSpace: 'pre-wrap' }}>排版：{style.current.layout_rules}</p> : null}
                  {style.current.motion_rules ? <p style={{ whiteSpace: 'pre-wrap' }}>动效：{style.current.motion_rules}</p> : null}
                  {style.current.reference_item_ids.length ? (
                    <p>
                      参考素材：
                      {style.current.reference_item_ids.map((id) => (
                        <Link key={id} href={`/library?open=${id}`} style={{ marginRight: 8 }}>
                          #{id}
                        </Link>
                      ))}
                    </p>
                  ) : null}
                </>
              ) : null}
              {tpl?.current ? (
                <>
                  {tpl.current.purpose ? <p>用途：{tpl.current.purpose}</p> : null}
                  {tpl.current.audience ? <p>受众：{tpl.current.audience}</p> : null}
                  {tpl.current.tone ? <p>语气：{tpl.current.tone}</p> : null}
                  <ol>
                    {tpl.current.structure.map((s, i) => (
                      <li key={i}>
                        {s.title}
                        {s.points?.length ? <span className="cw-muted">：{s.points.join('；')}</span> : null}
                      </li>
                    ))}
                  </ol>
                </>
              ) : null}
              {detail.current?.note ? <p className="cw-muted">{detail.current.note}</p> : null}
              {detail.copied_from ? <p className="cw-muted">复制自 {detail.copied_from}</p> : null}
              {detail.versions && detail.versions.length > 1 ? (
                <p className="cw-muted cw-num">
                  版本：
                  {detail.versions.map((v) => `v${v.version} ${v.created_at.slice(0, 10)}`).join(' · ')}
                </p>
              ) : null}
            </Card>
          ) : (
            <div className="cw-empty">选一项查看；或在灵感库选几张素材「提炼为风格 / 模板」</div>
          )}
        </section>
      </div>
    </CwPage>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <StylesPage />
    </Suspense>
  );
}
