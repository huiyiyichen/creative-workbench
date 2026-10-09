'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AudioLines, BookOpen, ExternalLink, FileImage, Film, Pencil, Plus, Search, Sparkles, Trash2, X } from 'lucide-react';
import { Button, Card, ColorPicker, Empty, Form, Input, Modal, Select, Tag, Tooltip, Typography, message } from 'antd';
import type { FavoriteItem, FavoriteTargetType } from '@/types';
import { favoritesApi, studioApi } from '@/lib/api';
import type { StudioCatalog } from '@/lib/api';
import { CreativePresetCard, PresetArtwork, presetKind } from '@/components/CreativePresetCard';
import type { CreativePreset } from '@/components/CreativePresetCard';

const { Title, Text } = Typography;
const TYPES: Array<{ value: FavoriteTargetType | ''; label: string }> = [
  { value: '', label: '全部' }, { value: 'content', label: '文章' }, { value: 'video', label: '视频' },
  { value: 'audio', label: '音频' }, { value: 'image', label: '图片' }, { value: 'template', label: '模板' },
  { value: 'style', label: '风格' }, { value: 'creator', label: '创作者' }, { value: 'project', label: '工程' }, { value: 'work', label: '作品' },
];
const MODES = [{ value: 'animation_video', label: '动画讲解' }, { value: 'video_prompt', label: '普通视频' }, { value: 'music_video', label: '音乐 MV' }, { value: 'article', label: '文章' }];

type PresetForm = {
  target_type: FavoriteTargetType;
  title: string;
  target_key?: string;
  url?: string;
  cover_url?: string;
  source_name?: string;
  category?: string;
  description?: string;
  colors?: string[];
  modes?: string[];
  beats?: string;
  rules?: string;
  note?: string;
};

function buildSnapshot(values: PresetForm) {
  const isStyle = values.target_type === 'style';
  return {
    category: values.category || (isStyle ? '我的风格' : '我的模板'),
    description: values.description || '',
    image: values.cover_url || '',
    ...(isStyle
      ? { colors: values.colors || ['#F1F5F9', '#2563EB', '#0F172A'], rules: values.rules?.split(/\r?\n/).map((line) => line.trim()).filter(Boolean) || [] }
      : { modes: values.modes || ['animation_video', 'video_prompt', 'article', 'music_video'], beats: values.beats?.split(/\r?\n/).map((line) => line.trim()).filter(Boolean) || [] }),
  };
}

function PaletteEditor({ value, onChange }: { value?: string[]; onChange?: (next: string[]) => void }) {
  const colors = value?.length ? value : ['#F1F5F9', '#2563EB', '#0F172A'];
  return (
    <div className="flex flex-wrap items-center gap-2">
      {colors.map((color, index) => (
        <div key={index} className="flex items-center gap-1">
          <ColorPicker value={color} onChange={(_, hex) => onChange?.(colors.map((item, i) => i === index ? hex : item))} showText />
          {colors.length > 2 && <Tooltip title="移除颜色"><Button type="text" size="small" icon={<X size={12} />} onClick={() => onChange?.(colors.filter((_, i) => i !== index))} /></Tooltip>}
        </div>
      ))}
      {colors.length < 5 && <Tooltip title="添加颜色"><Button size="small" icon={<Plus size={14} />} onClick={() => onChange?.([...colors, '#FFFFFF'])} /></Tooltip>}
    </div>
  );
}

export default function FavoritesPage() {
  const [items, setItems] = useState<FavoriteItem[]>([]);
  const [catalog, setCatalog] = useState<StudioCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [type, setType] = useState<FavoriteTargetType | ''>('');
  const [category, setCategory] = useState('全部');
  const [keyword, setKeyword] = useState('');
  const [editorOpen, setEditorOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<FavoriteItem | null>(null);
  const [detail, setDetail] = useState<CreativePreset>();
  const [localFile, setLocalFile] = useState<File | null>(null);
  const [localPreview, setLocalPreview] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const [form] = Form.useForm<PresetForm>();
  const formType = Form.useWatch('target_type', form);
  const isPreset = formType === 'template' || formType === 'style';

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [favoriteResponse, catalogResponse] = await Promise.all([
        favoritesApi.list({ page: 1, page_size: 200 }),
        studioApi.catalog(),
      ]);
      setItems(favoriteResponse.items.filter((item) => item.status !== 'archived'));
      setCatalog(catalogResponse);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '收藏加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!localFile || !localFile.type.startsWith('image/')) {
      setLocalPreview('');
      return;
    }
    const url = URL.createObjectURL(localFile);
    setLocalPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [localFile]);

  const presets = useMemo<CreativePreset[]>(() => {
    if (!catalog) return [];
    if (type === 'template') return catalog.templates;
    if (type === 'style') return catalog.styles;
    if (!type) return [...catalog.templates, ...catalog.styles];
    return [];
  }, [catalog, type]);
  const categories = useMemo(() => ['全部', ...Array.from(new Set(presets.map((item) => item.category).filter(Boolean) as string[]))], [presets]);
  const visiblePresets = useMemo(() => presets.filter((item) => (
    (category === '全部' || item.category === category)
    && `${item.name} ${item.category} ${item.description}`.toLowerCase().includes(keyword.toLowerCase())
  )), [category, keyword, presets]);
  const visibleItems = useMemo(() => items.filter((item) => (
    item.target_type !== 'style' && item.target_type !== 'template'
    &&
    (!type || item.target_type === type)
    && `${item.title} ${item.note || ''} ${item.source_name || ''}`.toLowerCase().includes(keyword.toLowerCase())
  )), [items, keyword, type]);
  const countFor = (kind: FavoriteTargetType | '') => kind === 'template' ? catalog?.templates.length ?? 0 : kind === 'style' ? catalog?.styles.length ?? 0 : kind ? items.filter((item) => item.target_type === kind).length : (catalog?.templates.length ?? 0) + (catalog?.styles.length ?? 0) + items.filter((item) => item.target_type !== 'template' && item.target_type !== 'style').length;

  const openAdd = (targetType: FavoriteTargetType = type === 'template' || type === 'style' ? type : 'video') => {
    setEditing(null);
    setLocalFile(null);
    form.resetFields();
    form.setFieldsValue({ target_type: targetType, modes: MODES.map((mode) => mode.value), colors: ['#F1F5F9', '#2563EB', '#0F172A'] });
    setEditorOpen(true);
  };

  const openEdit = (preset: CreativePreset) => {
    const favorite = items.find((item) => item.id === preset.favorite_id);
    setEditing(favorite || null);
    setLocalFile(null);
    form.resetFields();
    form.setFieldsValue({
      target_type: presetKind(preset),
      title: preset.name,
      category: preset.category,
      description: preset.description,
      cover_url: favorite?.cover_url ?? undefined,
      ...('rules' in preset ? { colors: preset.colors, rules: preset.rules.join('\n') } : { modes: preset.modes, beats: preset.beats.join('\n') }),
    });
    setDetail(undefined);
    setEditorOpen(true);
  };

  const save = async () => {
    let values: PresetForm;
    try { values = await form.validateFields(); } catch { return; }
    const preset = values.target_type === 'style' || values.target_type === 'template';
    if (!preset && !localFile && !values.target_key) {
      form.setFields([{ name: 'target_key', errors: ['填写链接或选择文件'] }]);
      return;
    }
    setSaving(true);
    try {
      if (localFile) {
        await favoritesApi.uploadFile(localFile, {
          target_type: values.target_type as 'style' | 'template' | 'image' | 'audio' | 'video',
          title: values.title,
          note: preset ? values.description : values.note,
          snapshot: preset ? buildSnapshot(values) : undefined,
          favorite_id: editing?.id,
        });
      } else if (editing) {
        await favoritesApi.update(editing.id, { title: values.title, cover_url: values.cover_url || null, note: values.description || null, snapshot: preset ? { ...editing.snapshot, ...buildSnapshot(values) } : null });
      } else {
        await favoritesApi.create({
          target_type: values.target_type,
          target_id: undefined,
          target_key: preset ? `custom:${Date.now()}` : values.target_key,
          title: values.title,
          url: values.url || null,
          cover_url: values.cover_url || null,
          source_name: values.source_name || null,
          note: preset ? values.description || null : values.note || null,
          snapshot: preset ? buildSnapshot(values) : null,
          status: 'saved',
        });
      }
      setEditorOpen(false);
      setEditing(null);
      setLocalFile(null);
      setType(values.target_type);
      setCategory('全部');
      await load();
      message.success('已保存');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: number) => {
    try { await favoritesApi.delete(id); setDetail(undefined); await load(); message.success('已删除'); }
    catch (error) { message.error(error instanceof Error ? error.message : '删除失败'); }
  };

  return (
    <div className="mx-auto max-w-[1560px] px-5 pb-12 pt-6 lg:px-8">
      <div className="mb-6 flex items-center justify-between gap-4"><Title level={2} className="!mb-0">收藏夹</Title><Button type="primary" icon={<Plus size={15} />} onClick={() => openAdd()}>{type === 'style' ? '添加风格' : type === 'template' ? '添加模板' : '添加收藏'}</Button></div>
      <div className="mb-5 flex flex-wrap items-center gap-2">
        {TYPES.map((item) => <Button key={item.value || 'all'} type={type === item.value ? 'primary' : 'default'} onClick={() => { setType(item.value); setCategory('全部'); }}>{item.label} {countFor(item.value)}</Button>)}
        <Input prefix={<Search size={14} />} value={keyword} placeholder="搜索收藏" allowClear className="!ml-auto !w-full sm:!w-[220px]" onChange={(event) => setKeyword(event.target.value)} />
      </div>
      {(type === 'template' || type === 'style') && <div className="mb-4 flex flex-wrap gap-2 border-b border-gray-200 pb-4">{categories.map((item) => <Button key={item} size="small" type={category === item ? 'primary' : 'text'} onClick={() => setCategory(item)}>{item}</Button>)}</div>}
      {loading ? <div className="py-20 text-center text-gray-400">加载中</div> : visiblePresets.length + visibleItems.length === 0 ? <Empty description="暂无收藏" /> : (
        <div className="grid gap-x-5 gap-y-7 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {visiblePresets.map((preset) => <CreativePresetCard key={preset.id} preset={preset} onClick={() => setDetail(preset)} />)}
          {visibleItems.map((item) => {
            const preview = item.cover_url || (item.target_type === 'image' ? item.media_url : '') || '';
            const video = item.target_type === 'video' || (item.target_type === 'work' && Boolean(item.media_url));
            const projectId = item.target_type === 'work' ? item.snapshot?.project_id : undefined;
            return <Card key={item.id} hoverable styles={{ body: { padding: 16 } }} cover={<div className="aspect-[1.52] overflow-hidden bg-gray-100">
              {video && item.media_url ? <video src={item.media_url} controls preload="metadata" className="h-full w-full object-contain" />
                : item.target_type === 'audio' && (item.media_url || item.url) ? <div className="flex h-full flex-col items-center justify-center gap-4 p-4"><AudioLines size={32} className="text-primary" /><audio src={item.media_url || item.url || ''} controls className="w-full" /></div>
                  : preview ? <img src={preview} alt="" className="h-full w-full object-cover" />
                    : <div className="flex h-full items-center justify-center">{item.target_type === 'video' ? <Film className="text-gray-300" /> : <BookOpen className="text-gray-300" />}</div>}
            </div>}>
              <Tag>{TYPES.find((option) => option.value === item.target_type)?.label}</Tag>
              <h3 className="mt-2 line-clamp-2 min-h-10 text-sm font-bold">{item.title}</h3>
              <div className="mt-3 flex items-center gap-2"><Button size="small" type="primary" href={projectId ? `/studio?project_id=${projectId}&stage=2` : `/studio?favorite_id=${item.id}`} icon={<Sparkles size={13} />}>{projectId ? '打开作品' : '进入创作'}</Button>{item.url && <Tooltip title="打开来源"><Button size="small" href={item.url} target="_blank" icon={<ExternalLink size={13} />} /></Tooltip>}<Tooltip title="删除收藏"><Button className="!ml-auto" size="small" danger icon={<Trash2 size={13} />} onClick={() => void remove(item.id)} /></Tooltip></div>
            </Card>;
          })}
        </div>
      )}
      <Modal title={editing ? '编辑收藏' : '添加收藏'} open={editorOpen} onCancel={() => setEditorOpen(false)} onOk={() => void save()} confirmLoading={saving} okText="保存" width={680}>
        <Form form={form} layout="vertical">
          <Form.Item name="target_type" label="类型" rules={[{ required: true }]}><Select disabled={Boolean(editing)} options={TYPES.filter((item) => item.value).map((item) => ({ value: item.value, label: item.label }))} /></Form.Item>
          <Form.Item name="title" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          {isPreset ? <>
            <Form.Item name="category" label="分类"><Input /></Form.Item>
            <Form.Item name="description" label="描述"><Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} /></Form.Item>
            {formType === 'style' ? <><Form.Item name="colors" label="色板"><PaletteEditor /></Form.Item><Form.Item name="rules" label="视觉规则"><Input.TextArea autoSize={{ minRows: 3, maxRows: 6 }} placeholder="每行一条视觉规则" /></Form.Item></> : <><Form.Item name="modes" label="适用形态"><Select mode="multiple" options={MODES} /></Form.Item><Form.Item name="beats" label="内容结构"><Input.TextArea autoSize={{ minRows: 3, maxRows: 6 }} placeholder="每行一个段落或节拍" /></Form.Item></>}
          </> : <><Form.Item name="target_key" label="链接或唯一标识"><Input /></Form.Item><Form.Item name="url" label="来源链接"><Input /></Form.Item><Form.Item name="note" label="备注"><Input.TextArea autoSize={{ minRows: 2, maxRows: 4 }} /></Form.Item></>}
          <Form.Item name="cover_url" label={isPreset ? '示意图地址' : '封面地址'}><Input /></Form.Item>
          {(isPreset || ['image', 'video', 'audio'].includes(formType || '')) && <div className="mb-2"><Button icon={<FileImage size={14} />} onClick={() => fileInput.current?.click()}>{isPreset ? '上传示意图' : '上传文件'}</Button><input ref={fileInput} type="file" accept={isPreset ? 'image/*' : 'image/*,video/*,audio/*'} className="hidden" onChange={(event) => { setLocalFile(event.target.files?.[0] || null); event.currentTarget.value = ''; }} />{localFile && <Text className="ml-2 text-xs">{localFile.name}</Text>}{localPreview && <img src={localPreview} alt="" className="mt-3 max-h-36 w-full rounded-sm object-contain" />}</div>}
        </Form>
      </Modal>
      <Modal open={Boolean(detail)} onCancel={() => setDetail(undefined)} width={800} title={detail?.name} footer={detail ? <div className="flex gap-2"><Button icon={<Pencil size={14} />} onClick={() => openEdit(detail)}>{detail.custom ? '编辑' : '以此新建'}</Button>{detail.favorite_id && <Button danger icon={<Trash2 size={14} />} onClick={() => void remove(detail.favorite_id!)}>删除</Button>}<Button className="!ml-auto" type="primary" href={`/studio?${presetKind(detail)}_id=${encodeURIComponent(detail.id)}`}>带入创作</Button></div> : null}>{detail && <div className="space-y-5"><div className="aspect-[1.8] overflow-hidden rounded-sm"><PresetArtwork preset={detail} /></div><p className="text-sm leading-6 text-gray-600">{detail.description}</p><div className="grid gap-3 sm:grid-cols-2">{('rules' in detail ? detail.rules : detail.beats).map((line, index) => <div key={index} className="flex gap-3 text-sm text-gray-600"><span className="font-mono text-gray-400">{String(index + 1).padStart(2, '0')}</span>{line}</div>)}</div></div>}</Modal>
    </div>
  );
}
